"""本機網頁介面：在你的裝置上開一個小伺服器，用瀏覽器操作同步。

為什麼要有本機伺服器？NTU COOL（Canvas）的 API 不對其他網域送 CORS 標頭，
所以純前端網頁讀不到回應；而且權杖也不該放在網頁裡。這裡由本機伺服器去打 API，
網頁只跟 127.0.0.1 講話，同源、沒有 CORS 問題，權杖不離開裝置。
"""

from __future__ import annotations

import json
import mimetypes
import platform
import secrets
import shutil
import socket
import time
import zipfile
import threading
import urllib.parse
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .client import CanvasClient, bearer_header
from .config import Config, clear_saved_token, save_token_to_env
from .errors import AuthError, NtuCoolError
from .icon import icon_png, prewarm
from .manifest import Manifest
from .models import local_time, parse_iso
from .report import human_size
from .scraper import Scraper
from .pwa import SERVICE_WORKER, manifest
from .webui import PAGE

#: 只接受這些 Host，擋掉 DNS rebinding（別的網站把某個網域指到 127.0.0.1）
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")

#: 存取金鑰存在輸出資料夾裡，網址才不會每次啟動都變（可以加書籤）
KEY_FILENAME = ".ntucool-webkey"

#: 瀏覽器會自動索取這些，沒有就讓它安靜地拿到 204，不要變成 403 錯誤
QUIET_PATHS = ("/favicon.ico",)

#: PWA 的資產不含任何個人資料，也必須在還沒帶金鑰時就拿得到（Service Worker 會自己去抓）
ICON_PATHS = {
    "/icon-192.png": (192, False),
    "/icon-512.png": (512, False),
    "/icon-512-maskable.png": (512, True),
    "/apple-touch-icon.png": (180, True),
    "/apple-touch-icon-precomposed.png": (180, True),
}


def load_or_create_key(out_dir, *, rotate: bool = False) -> str:
    """讀取（或建立）這台機器上的存取金鑰。"""
    path = Path(out_dir) / KEY_FILENAME
    if not rotate:
        try:
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except OSError:
            pass
    key = secrets.token_urlsafe(12)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        pass  # 寫不進去就用這次執行的臨時金鑰
    return key


class SyncJob:
    """一次同步的狀態；同步在背景執行緒跑，網頁輪詢進度。"""

    def __init__(self):
        self.lines: list[str] = []
        self.status = "idle"  # idle / running / done / error
        self.cancelled = False
        self.courses: dict[str, dict] = {}   # 課程 → 進度
        self.order: list[str] = []           # 保持課程出現的順序
        self.lock = threading.Lock()

    def log(self, message=""):
        with self.lock:
            self.lines.append(str(message))

    def handle(self, event: dict) -> None:
        """把 Scraper 丟出來的事件變成畫面上的進度條。"""
        name = event.get("course") or ""
        if not name:
            return
        with self.lock:
            if name not in self.courses:
                self.courses[name] = {"course": name, "done": 0, "total": 0, "state": "waiting"}
                self.order.append(name)
            entry = self.courses[name]
            kind = event.get("type")
            if kind == "course_start":
                entry["state"] = "running"
            elif kind == "downloads_planned":
                entry["total"] = event.get("total") or 0
            elif kind == "file_done":
                entry["done"] = event.get("done") or entry["done"]
                entry["total"] = event.get("total") or entry["total"]
            elif kind == "course_done":
                entry["state"] = "done"
                entry["done"] = event.get("downloaded", entry["done"])
                entry["total"] = entry["total"] or entry["done"]
                entry["skipped"] = event.get("skipped", 0)
            elif kind == "course_failed":
                entry["state"] = "failed"
                entry["error"] = event.get("error", "")

    def snapshot(self, start: int) -> dict:
        with self.lock:
            courses = []
            for name in self.order:
                entry = dict(self.courses[name])
                total = entry.get("total") or 0
                done = entry.get("done") or 0
                if entry["state"] == "done":
                    entry["percent"] = 100
                else:
                    entry["percent"] = int(done * 100 / total) if total else (5 if entry["state"] == "running" else 0)
                courses.append(entry)
            return {"status": self.status, "lines": self.lines[start:],
                    "courses": courses, "cancelled": self.cancelled}

    @property
    def running(self) -> bool:
        return self.status == "running"

    def cancel(self) -> bool:
        if not self.running:
            return False
        self.cancelled = True
        self.log("正在取消……（等目前這個檔案結束）")
        return True


#: 打包下載的「取件單」保留多久（選好檔案到真的按下下載之間）
TICKET_TTL = 600.0
MAX_TICKETS = 32


class ZipStream:
    """讓 zipfile 直接寫進 HTTP 連線，不先在記憶體或磁碟上做出整包 zip。"""

    def __init__(self, wfile):
        self.wfile = wfile
        self.position = 0

    def write(self, data) -> int:
        self.wfile.write(data)
        self.position += len(data)
        return len(data)

    def tell(self) -> int:
        return self.position

    def flush(self) -> None:
        self.wfile.flush()

    @staticmethod
    def seekable() -> bool:
        return False  # 逼 zipfile 用串流模式（data descriptor）


class WebApp:
    """把設定、目前的同步狀態和輸出資料夾綁在一起。"""

    def __init__(self, config: Config, key: str):
        self.config = config
        self.key = key
        self.job = SyncJob()
        self.tickets: dict[str, dict] = {}
        self.last_run: dict = {}          # 給診斷畫面看的上一次同步摘要

    # ---- 資料 ----------------------------------------------------------
    def status(self) -> dict:
        manifest = Manifest.load(self.config.out_dir)
        user, token_ok = "", False
        if self.config.token:
            try:
                user = (self._client().whoami() or {}).get("name") or ""
                token_ok = bool(user)
            except AuthError:
                token_ok = False  # 權杖過期 → 回到登入畫面
            except NtuCoolError:
                token_ok = True  # 只是連不上，不必要求重新登入
        stored = self.storage()
        return {
            "authenticated": token_ok,
            "user": user,
            "base_url": self.config.base_url,
            "out_dir": str(Path(self.config.out_dir).resolve()),
            "last_sync": local_time(manifest.last_sync),
            "files": stored["files"],
            "bytes": stored["bytes"],
            "size": human_size(stored["bytes"]),
            "term": stored["term"],
            "syncing": self.job.running,
        }

    def storage(self) -> dict:
        """已經抓下來的東西佔多少空間。"""
        out = Path(self.config.out_dir)
        files = total = 0
        term = ""
        if out.is_dir():
            for item in out.rglob("*"):
                if item.is_file() and not item.name.startswith("."):
                    files += 1
                    total += item.stat().st_size
            for course in self.courses():
                if course.get("term"):
                    term = course["term"]
                    break
        return {"files": files, "bytes": total, "term": term}

    def courses(self, term: str = "") -> list[dict]:
        """課程清單：名稱、課號、教師、檔案數與容量，全部來自已抓下來的資料。"""
        out = Path(self.config.out_dir)
        result = []
        if not out.is_dir():
            return result
        for course_dir in sorted(p for p in out.iterdir() if p.is_dir()):
            source = course_dir / "course.json"
            if not source.is_file():
                continue
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            course = data.get("course") or {}
            if term and (course.get("term") or "未分類") != term:
                continue
            files_dir = course_dir / "files"
            downloaded = [f for f in files_dir.rglob("*") if f.is_file()] if files_dir.is_dir() else []
            result.append(
                {
                    "dir": course_dir.name,
                    "id": course.get("id"),
                    "name": course.get("name") or course_dir.name,
                    "code": course.get("course_code") or "",
                    "teacher": "、".join(course.get("teachers") or []),
                    "term": course.get("term") or "",
                    "score": course.get("score"),
                    "grade": course.get("grade"),
                    "files": len(downloaded),
                    "bytes": sum(f.stat().st_size for f in downloaded),
                    "size": human_size(sum(f.stat().st_size for f in downloaded)),
                    "assignments": len(data.get("assignments") or []),
                    "announcements": len(data.get("announcements") or []),
                }
            )
        return result

    def course_detail(self, dirname: str) -> dict | None:
        """單一課程：檔案清單與作業，給課程內頁用。"""
        out = Path(self.config.out_dir).resolve()
        course_dir = (out / dirname).resolve()
        if course_dir.parent != out or not course_dir.is_dir():
            return None
        try:
            data = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        files = []
        for item in sorted(course_dir.rglob("*")):
            if item.is_file() and not item.name.startswith("."):
                files.append(
                    {
                        "name": item.name,
                        "folder": str(item.parent.relative_to(course_dir)),
                        "path": str(item.relative_to(out)),
                        "ext": (item.suffix.lstrip(".") or "file").upper()[:4],
                        "bytes": item.stat().st_size,
                        "size": human_size(item.stat().st_size),
                    }
                )
        course = data.get("course") or {}
        return {
            "dir": dirname,
            "name": course.get("name"),
            "code": course.get("course_code") or "",
            "teacher": "、".join(course.get("teachers") or []),
            "term": course.get("term") or "",
            "url": course.get("url") or "",
            "files": files,
            "assignments": data.get("assignments") or [],
        }

    def files(self) -> dict:
        """列出已經抓下來的東西，讓網頁可以直接點開。"""
        out = Path(self.config.out_dir)
        courses = []
        if out.is_dir():
            for course_dir in sorted(p for p in out.iterdir() if p.is_dir()):
                entries = []
                for item in sorted(course_dir.rglob("*")):
                    if item.is_file() and not item.name.startswith("."):
                        entries.append(
                            {
                                "name": str(item.relative_to(course_dir)),
                                "path": str(item.relative_to(out)),
                                "size": human_size(item.stat().st_size),
                            }
                        )
                if entries:
                    courses.append({"name": course_dir.name, "files": entries})
        return {"courses": courses}

    def terms(self) -> list[dict]:
        """已經抓下來的資料涵蓋哪些學期。"""
        counts: dict[str, int] = {}
        for course in self.courses():
            counts[course.get("term") or "未分類"] = counts.get(course.get("term") or "未分類", 0) + 1
        return [{"term": term, "courses": count} for term, count in sorted(counts.items(), reverse=True)]

    def dashboard(self, *, now: datetime | None = None, term: str = "") -> dict:
        """跨課程的一眼看完：近期作業截止 + 各課成績。

        資料直接讀已經抓下來的 course.json，所以離線也看得到，也不會多打 API。
        """
        now = now or datetime.now(timezone.utc)
        upcoming, grades, events = [], [], []
        out = Path(self.config.out_dir)
        if not out.is_dir():
            return {"upcoming": [], "events": [], "grades": [], "term": term,
                    "generated_at": local_time(now.isoformat())}

        for course_dir in sorted(p for p in out.iterdir() if p.is_dir()):
            source = course_dir / "course.json"
            if not source.is_file():
                continue
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            course = data.get("course") or {}
            if term and (course.get("term") or "未分類") != term:
                continue
            label = course.get("course_code") or course.get("name") or course_dir.name
            for event in data.get("events") or []:
                start = parse_iso(event.get("start_at"))
                if start is None:
                    continue
                days = (start - now).total_seconds() / 86400
                if -1 < days <= 30:
                    events.append(
                        {
                            "course": label,
                            "title": event.get("title"),
                            "start_at": local_time(event.get("start_at")),
                            "days": round(days, 2),
                            "location": event.get("location") or "",
                            "url": event.get("url") or "",
                        }
                    )
            grades.append(
                {
                    "course": label,
                    "name": course.get("name") or "",
                    "score": course.get("score"),
                    "grade": course.get("grade"),
                }
            )
            for assignment in data.get("assignments") or []:
                due = parse_iso(assignment.get("due_at"))
                if due is None:
                    continue
                days = (due - now).total_seconds() / 86400
                submitted = bool(assignment.get("submitted"))
                # 未來 30 天內要交的，加上過去 7 天內逾期又沒交的
                if days > 30 or days < -7 or (days < 0 and submitted):
                    continue
                upcoming.append(
                    {
                        "course": label,
                        "name": assignment.get("name"),
                        "due_at": local_time(assignment.get("due_at")),
                        "days": round(days, 2),
                        "submitted": submitted,
                        "overdue": days < 0,
                        "url": assignment.get("url") or "",
                        "score": assignment.get("score"),
                    }
                )
        upcoming.sort(key=lambda item: item["days"])
        events.sort(key=lambda item: item["days"])
        return {"upcoming": upcoming, "events": events, "grades": grades,
                "term": term, "generated_at": local_time(now.isoformat())}

    # ---- 打包下載 ------------------------------------------------------
    def create_ticket(self, paths: list[str], name: str) -> dict:
        """把選好的檔案記成一張取件單；瀏覽器接著用一般的下載網址來取。

        走這一步是因為選了幾十個檔案時，路徑塞不進網址。
        """
        now = time.time()
        for key in [k for k, v in self.tickets.items() if now - v["created"] > TICKET_TTL]:
            self.tickets.pop(key, None)
        while len(self.tickets) >= MAX_TICKETS:
            oldest = min(self.tickets, key=lambda k: self.tickets[k]["created"])
            self.tickets.pop(oldest, None)

        resolved = []
        total = 0
        for relative in paths:
            target = self.resolve_download(relative)
            if target is not None:
                resolved.append(target)
                total += target.stat().st_size
        ticket = secrets.token_urlsafe(9)
        self.tickets[ticket] = {"files": resolved, "name": name or "ntucool", "created": now}
        return {"ticket": ticket, "files": len(resolved), "bytes": total, "size": human_size(total)}

    def files_for(self, *, ticket: str = "", course: str = "", everything: bool = False):
        """回傳 (要打包的檔案清單, zip 檔名)；找不到就回 (None, "")。"""
        out = Path(self.config.out_dir).resolve()
        if ticket:
            entry = self.tickets.get(ticket)
            if not entry or time.time() - entry["created"] > TICKET_TTL:
                return None, ""
            return entry["files"], entry["name"]
        if course:
            detail_dir = (out / course).resolve()
            if detail_dir.parent != out or not detail_dir.is_dir():
                return None, ""
            files = [f for f in sorted(detail_dir.rglob("*")) if f.is_file() and not f.name.startswith(".")]
            return files, course
        if everything:
            files = [f for f in sorted(out.rglob("*")) if f.is_file() and not f.name.startswith(".")]
            return files, "NTU-Course-Hub"
        return None, ""

    def arcname(self, path: Path) -> str:
        """zip 裡的相對路徑：保留課程資料夾結構。"""
        out = Path(self.config.out_dir).resolve()
        try:
            return str(path.resolve().relative_to(out))
        except ValueError:
            return path.name

    def search(self, query: str, *, term: str = "", limit: int = 60) -> dict:
        """跨課程搜尋：檔名、課程、作業、公告、行事曆。只讀本機資料，離線可用。"""
        needle = str(query or "").strip().lower()
        if not needle:
            return {"query": "", "results": [], "total": 0}
        out = Path(self.config.out_dir)
        results: list[dict] = []
        if not out.is_dir():
            return {"query": query, "results": [], "total": 0}

        def add(kind, label, sub, course, **extra):
            results.append({"kind": kind, "label": label, "sub": sub, "course": course, **extra})

        for course_dir in sorted(p for p in out.iterdir() if p.is_dir()):
            source = course_dir / "course.json"
            if not source.is_file():
                continue
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            course = data.get("course") or {}
            if term and (course.get("term") or "未分類") != term:
                continue
            label = course.get("course_code") or course.get("name") or course_dir.name

            haystack = " ".join(str(course.get(k) or "") for k in ("name", "course_code"))
            haystack += " " + "、".join(course.get("teachers") or [])
            if needle in haystack.lower():
                add("course", course.get("name") or label, f"{label} · 課程", label, dir=course_dir.name)

            for item in sorted(course_dir.rglob("*")):
                if not item.is_file() or item.name.startswith("."):
                    continue
                if needle in item.name.lower():
                    folder = str(item.parent.relative_to(course_dir)).replace("files", "", 1).strip("/.")
                    add("file", item.name, f"{label}{' · ' + folder if folder else ''}", label,
                        path=str(item.relative_to(out)), size=human_size(item.stat().st_size))

            for item in data.get("assignments") or []:
                if needle in str(item.get("name") or "").lower():
                    add("assignment", item.get("name"), f"{label} · 作業", label, url=item.get("url") or "")
            for item in data.get("announcements") or []:
                if needle in str(item.get("title") or "").lower():
                    add("announcement", item.get("title"), f"{label} · 公告", label, url=item.get("url") or "")
            for item in data.get("events") or []:
                if needle in str(item.get("title") or "").lower():
                    add("event", item.get("title"), f"{label} · 行事曆", label, url=item.get("url") or "")

        order = {"file": 0, "assignment": 1, "event": 2, "announcement": 3, "course": 4}
        results.sort(key=lambda r: (order.get(r["kind"], 9), r["label"]))
        return {"query": query, "results": results[:limit], "total": len(results)}

    # ---- Phase 05：清理 ------------------------------------------------
    def delete_course(self, dirname: str) -> dict | None:
        """刪掉一門課已經下載的內容，同步紀錄裡的對應項目也要清掉。"""
        out = Path(self.config.out_dir).resolve()
        course_dir = (out / dirname).resolve()
        if course_dir.parent != out or not course_dir.is_dir():
            return None
        files = [f for f in course_dir.rglob("*") if f.is_file()]
        freed = sum(f.stat().st_size for f in files)
        shutil.rmtree(course_dir)

        manifest = Manifest.load(self.config.out_dir)
        prefix = str(course_dir)
        manifest.files = {k: v for k, v in manifest.files.items()
                          if not str(v.get("path") or "").startswith(prefix)}
        manifest.courses = {k: v for k, v in manifest.courses.items() if v.get("dir") != dirname}
        manifest.save()
        return {"deleted": dirname, "files": len(files), "bytes": freed, "size": human_size(freed)}

    # ---- Phase 07：診斷 ------------------------------------------------
    def diagnostics(self) -> dict:
        stored = self.storage()
        return {
            "mode": "本機伺服器（直接呼叫 NTU COOL API）",
            "base_url": self.config.base_url,
            "authenticated": bool(self.config.token),
            "token_source": "已設定" if self.config.token else "未設定",
            "out_dir": str(Path(self.config.out_dir).resolve()),
            "sections": list(self.config.sections),
            "concurrency": self.config.concurrency,
            "files": stored["files"],
            "size": human_size(stored["bytes"]),
            "courses": len(self.courses()),
            "last_sync": local_time(Manifest.load(self.config.out_dir).last_sync),
            "job_status": self.job.status,
            "last_run": self.last_run,
            "python": platform.python_version(),
        }

    def resolve_download(self, relative: str) -> Path | None:
        """把網址對應回輸出資料夾裡的檔案，擋掉跳出資料夾的路徑。"""
        out = Path(self.config.out_dir).resolve()
        target = (out / urllib.parse.unquote(relative)).resolve()
        if target != out and out not in target.parents:
            return None
        return target if target.is_file() else None

    # ---- 同步 ----------------------------------------------------------
    def _client(self) -> CanvasClient:
        return CanvasClient(
            self.config.api_root,
            self.config.token,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            per_page=self.config.per_page,
        )

    def config_for(self, options: dict) -> Config:
        config = self.config
        if options.get("pdf_only"):
            config = replace(config, extensions=("pdf", "pptx", "ppt", "doc", "docx"))
        if options.get("skip_big"):
            config = replace(config, max_file_mb=50.0)
        term = str(options.get("term") or "").strip()
        if term and term != "未分類":
            config = replace(config, terms=(term,))
        courses = str(options.get("courses") or "").strip()
        if courses:
            config = replace(
                config,
                course_filters=tuple(c.strip() for c in courses.replace(",", " ").split() if c.strip()),
            )
        return config

    def login(self, token: str) -> tuple[bool, str]:
        """驗證權杖後存起來。權杖只往這裡走，不會出現在日誌或回應裡。"""
        token = (token or "").strip()
        if not token:
            return False, "請貼上存取權杖"
        try:
            bearer_header(token)  # 格式問題要講得比「權杖無效」更具體
        except AuthError as exc:
            return False, str(exc)
        try:
            probe = CanvasClient(self.config.api_root, token, timeout=self.config.timeout, max_retries=1)
            profile = probe.whoami() or {}
        except AuthError:
            return False, "這個權杖無效或已過期，請回 NTU COOL 重新產生一個"
        except NtuCoolError as exc:
            return False, f"無法連上 {self.config.base_url}：{exc}"
        save_token_to_env(token)
        self.config = replace(self.config, token=token)
        return True, profile.get("name") or ""

    def logout(self) -> None:
        clear_saved_token()
        self.config = replace(self.config, token="")

    def start_sync(self, options: dict) -> bool:
        if not self.config.token:
            return False
        if self.job.running:
            return False
        self.job = SyncJob()
        job, config = self.job, self.config_for(options)
        job.status = "running"

        def run():
            client = CanvasClient(config.api_root, config.token, timeout=config.timeout,
                                  max_retries=config.max_retries, per_page=config.per_page)
            try:
                scraper = Scraper(
                    config,
                    client,
                    Manifest.load(config.out_dir),
                    log=job.log,
                    on_event=job.handle,
                    should_stop=lambda: job.cancelled,
                )
                result = scraper.run()
                self.last_run = {
                    "finished_at": local_time(datetime.now(timezone.utc).isoformat()),
                    "courses": len(result.results),
                    "downloaded": result.downloaded,
                    "bytes": result.bytes,
                    "size": human_size(result.bytes),
                    "requests": client.request_count,
                    "retries": client.retry_count,
                    "rate_limit_remaining": client.rate_limit_remaining,
                    "last_status": client.last_status,
                    "cancelled": result.cancelled,
                    "failures": result.failures[:20],
                }
                job.log("")
                job.log(
                    f"完成：{len(result.results)} 門課程，新增／更新 {result.downloaded} 個檔案"
                    f"（{human_size(result.bytes)}）"
                )
                job.status = "cancelled" if result.cancelled else "done"
            except NtuCoolError as exc:
                job.log(f"錯誤：{exc}")
                self.last_run = {"finished_at": local_time(datetime.now(timezone.utc).isoformat()),
                                 "error": str(exc), "requests": client.request_count,
                                 "last_status": client.last_status}
                job.status = "error"
            except Exception as exc:  # noqa: BLE001 — 背景執行緒不能讓例外消失
                job.log(f"未預期的錯誤：{exc!r}")
                job.status = "error"

        threading.Thread(target=run, daemon=True).start()
        return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ntucool"

    def log_message(self, *args):
        pass  # 伺服器自己的日誌不要蓋掉同步進度

    # ---- 共用 ----------------------------------------------------------
    @property
    def app(self) -> WebApp:
        return self.server.app

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # 這是本機工具，不開放任何跨網域讀取
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_zip(self, files, name: str):
        """邊打包邊送出。內容多半已經是壓縮過的 PDF，所以不再壓一次。"""
        filename = f"{safe_zip_name(name)}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")  # 長度未知，靠關閉連線標示結束
        self.end_headers()
        if self.command == "HEAD":
            return
        stream = ZipStream(self.wfile)
        try:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                for item in files:
                    archive.write(item, arcname=self.app.arcname(item))
        except (BrokenPipeError, ConnectionResetError):
            pass  # 使用者取消下載

    def _json(self, payload, status: int = 200):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _text(self, status: int, message: str):
        self._send(status, message.encode("utf-8"), "text/plain; charset=utf-8")

    def _authorized(self, query: dict) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            return False
        supplied = (query.get("k") or [""])[0] or self.headers.get("X-Ntucool-Key", "")
        return secrets.compare_digest(supplied, self.app.key)

    # ---- 路由 ----------------------------------------------------------
    def handle_one_request(self):
        """任何未預期的例外都轉成 500，不要讓連線直接斷掉。"""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            try:
                self._text(500, f"伺服器發生錯誤：{exc}")
            except Exception:  # noqa: BLE001 — 連回應都送不出去就放棄
                pass

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        if path in QUIET_PATHS:
            return self._send(204, b"", "text/plain")
        if path in ICON_PATHS:
            size, square = ICON_PATHS[path]
            return self._send(200, icon_png(size, square=square), "image/png",
                              {"Cache-Control": "public, max-age=86400"})
        if path == "/sw.js":
            # Service Worker 必須從根路徑提供，scope 才涵蓋整個站
            return self._send(200, SERVICE_WORKER.encode("utf-8"),
                              "text/javascript; charset=utf-8", {"Service-Worker-Allowed": "/"})
        if not self._authorized(query):
            return self._text(403, "請用終端機印出的完整網址開啟（含 ?k=... 的存取金鑰）。")

        if path == "/manifest.webmanifest":
            # start_url 裡有金鑰，所以這份要帶金鑰才拿得到
            return self._send(200, manifest(self.app.key).encode("utf-8"),
                              "application/manifest+json; charset=utf-8")
        if path == "/":
            page = PAGE.replace("__KEY__", urllib.parse.quote(self.app.key))
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._json(self.app.status())
        if path == "/api/search":
            return self._json(self.app.search((query.get("q") or [""])[0],
                                              term=(query.get("term") or [""])[0]))
        if path == "/api/diagnostics":
            return self._json(self.app.diagnostics())
        if path == "/api/terms":
            return self._json({"terms": self.app.terms()})
        if path == "/api/courses":
            return self._json({"courses": self.app.courses((query.get("term") or [""])[0])})
        if path == "/api/course":
            name = (query.get("dir") or [""])[0]
            detail = self.app.course_detail(name)
            return self._json(detail) if detail else self._text(404, "找不到這門課程")
        if path == "/api/dashboard":
            return self._json(self.app.dashboard(term=(query.get("term") or [""])[0]))
        if path == "/api/files":
            return self._json(self.app.files())
        if path == "/api/progress":
            start = int((query.get("from") or ["0"])[0] or 0)
            return self._json(self.app.job.snapshot(start))
        if path == "/api/zip":
            files, name = self.app.files_for(
                ticket=(query.get("ticket") or [""])[0],
                course=(query.get("dir") or [""])[0],
                everything=(query.get("all") or [""])[0] == "1",
            )
            if not files:
                return self._text(404, "沒有可以打包的檔案（或取件連結已過期）")
            return self._send_zip(files, name)
        if path.startswith("/files/"):
            target = self.app.resolve_download(path[len("/files/") :])
            if target is None:
                return self._text(404, "找不到這個檔案")
            guessed = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), guessed)
        return self._text(404, "沒有這個頁面")

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not self._authorized(query):
            return self._text(403, "存取金鑰不正確")
        if parsed.path not in ("/api/sync", "/api/login", "/api/logout", "/api/zip-ticket",
                               "/api/cancel", "/api/delete"):
            return self._text(404, "沒有這個端點")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        if parsed.path == "/api/login":
            ok, message = self.app.login(str(payload.get("token") or ""))
            return self._json({"ok": ok, "user" if ok else "error": message}, 200 if ok else 401)
        if parsed.path == "/api/logout":
            self.app.logout()
            return self._json({"ok": True})
        if parsed.path == "/api/cancel":
            return self._json({"cancelled": self.app.job.cancel()})
        if parsed.path == "/api/delete":
            result = self.app.delete_course(str(payload.get("dir") or ""))
            return self._json(result) if result else self._text(404, "找不到這門課程")
        if parsed.path == "/api/zip-ticket":
            paths = payload.get("paths") or []
            if not isinstance(paths, list) or not paths:
                return self._text(400, "沒有選擇任何檔案")
            result = self.app.create_ticket([str(p) for p in paths[:2000]], str(payload.get("name") or ""))
            if not result["files"]:
                return self._text(404, "選到的檔案都不存在")
            return self._json(result)
        if not self.app.config.token:
            return self._text(401, "尚未登入")
        if not self.app.start_sync(payload):
            return self._text(409, "已經有一個同步在進行中")
        return self._json({"started": True})


def safe_zip_name(name: str) -> str:
    """zip 檔名：拿掉路徑符號，長度也收斂一下。"""
    cleaned = "".join(ch for ch in str(name or "ntucool") if ch not in '\\/:*?"<>|' and ch.isprintable())
    return (cleaned.strip() or "ntucool")[:80]


def lan_ip() -> str:
    """找出這台機器在區網裡的位址（給同網段的手機連）。不會真的送出封包。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))  # TEST-NET-1，保證沒人在用
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def create_server(config: Config, host: str = "127.0.0.1", port: int = 8765,
                  key: str | None = None, rotate_key: bool = False):
    """建立伺服器；回傳 (httpd, 要在瀏覽器打開的完整網址)。"""
    key = key or load_or_create_key(config.out_dir, rotate=rotate_key)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.app = WebApp(config, key)
    # 512px 的 icon 要畫幾秒鐘，先在背景畫好，別讓第一個請求等
    threading.Thread(target=prewarm, daemon=True).start()
    shown_host = lan_ip() if host in ("0.0.0.0", "::", "") else host
    url = f"http://{shown_host}:{httpd.server_address[1]}/?k={key}"
    return httpd, url
