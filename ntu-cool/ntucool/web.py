"""本機網頁介面：在你的裝置上開一個小伺服器，用瀏覽器操作同步。

為什麼要有本機伺服器？NTU COOL（Canvas）的 API 不對其他網域送 CORS 標頭，
所以純前端網頁讀不到回應；而且權杖也不該放在網頁裡。這裡由本機伺服器去打 API，
網頁只跟 127.0.0.1 講話，同源、沒有 CORS 問題，權杖不離開裝置。
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import socket
import threading
import urllib.parse
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .client import CanvasClient, bearer_header
from .config import Config, clear_saved_token, save_token_to_env
from .errors import AuthError, NtuCoolError
from .manifest import Manifest
from .models import local_time, parse_iso
from .report import human_size
from .scraper import Scraper
from .webui import PAGE

#: 只接受這些 Host，擋掉 DNS rebinding（別的網站把某個網域指到 127.0.0.1）
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")

#: 存取金鑰存在輸出資料夾裡，網址才不會每次啟動都變（可以加書籤）
KEY_FILENAME = ".ntucool-webkey"

#: 瀏覽器會自動索取這些，沒有就讓它安靜地拿到 204，不要變成 403 錯誤
QUIET_PATHS = ("/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png")


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
        self.lock = threading.Lock()

    def log(self, message=""):
        with self.lock:
            self.lines.append(str(message))

    def snapshot(self, start: int) -> dict:
        with self.lock:
            return {"status": self.status, "lines": self.lines[start:]}

    @property
    def running(self) -> bool:
        return self.status == "running"


class WebApp:
    """把設定、目前的同步狀態和輸出資料夾綁在一起。"""

    def __init__(self, config: Config, key: str):
        self.config = config
        self.key = key
        self.job = SyncJob()

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
        return {
            "authenticated": token_ok,
            "user": user,
            "base_url": self.config.base_url,
            "out_dir": str(Path(self.config.out_dir).resolve()),
            "last_sync": local_time(manifest.last_sync),
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

    def dashboard(self, *, now: datetime | None = None) -> dict:
        """跨課程的一眼看完：近期作業截止 + 各課成績。

        資料直接讀已經抓下來的 course.json，所以離線也看得到，也不會多打 API。
        """
        now = now or datetime.now(timezone.utc)
        upcoming, grades = [], []
        out = Path(self.config.out_dir)
        if not out.is_dir():
            return {"upcoming": [], "grades": [], "generated_at": local_time(now.isoformat())}

        for course_dir in sorted(p for p in out.iterdir() if p.is_dir()):
            source = course_dir / "course.json"
            if not source.is_file():
                continue
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            course = data.get("course") or {}
            label = course.get("course_code") or course.get("name") or course_dir.name
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
        return {"upcoming": upcoming, "grades": grades, "generated_at": local_time(now.isoformat())}

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
            try:
                scraper = Scraper(
                    config,
                    CanvasClient(config.api_root, config.token, timeout=config.timeout,
                                 max_retries=config.max_retries, per_page=config.per_page),
                    Manifest.load(config.out_dir),
                    log=job.log,
                )
                result = scraper.run()
                job.log("")
                job.log(
                    f"完成：{len(result.results)} 門課程，新增／更新 {result.downloaded} 個檔案"
                    f"（{human_size(result.bytes)}）"
                )
                job.status = "done"
            except NtuCoolError as exc:
                job.log(f"錯誤：{exc}")
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
        if not self._authorized(query):
            return self._text(403, "請用終端機印出的完整網址開啟（含 ?k=... 的存取金鑰）。")

        if path == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._json(self.app.status())
        if path == "/api/dashboard":
            return self._json(self.app.dashboard())
        if path == "/api/files":
            return self._json(self.app.files())
        if path == "/api/progress":
            start = int((query.get("from") or ["0"])[0] or 0)
            return self._json(self.app.job.snapshot(start))
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
        if parsed.path not in ("/api/sync", "/api/login", "/api/logout"):
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
        if not self.app.config.token:
            return self._text(401, "尚未登入")
        if not self.app.start_sync(payload):
            return self._text(409, "已經有一個同步在進行中")
        return self._json({"started": True})


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
    shown_host = lan_ip() if host in ("0.0.0.0", "::", "") else host
    url = f"http://{shown_host}:{httpd.server_address[1]}/?k={key}"
    return httpd, url
