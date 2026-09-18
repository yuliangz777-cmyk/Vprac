"""擷取流程主體：列出課程 → 抓資訊 → 抓檔案 → 寫成資料夾。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .client import CanvasClient
from .config import Config
from .errors import ApiError, ForbiddenError, NotFoundError
from .htmlutil import extract_file_ids
from .manifest import Manifest
from .models import (
    normalize_announcement,
    normalize_assignment,
    normalize_course,
    normalize_event,
    normalize_file,
    normalize_module,
    normalize_page,
)
from .naming import course_dirname, safe_name, safe_relpath, unique_path
from .report import (
    announcements_markdown,
    assignments_markdown,
    course_markdown,
    index_markdown,
    page_markdown,
)

# Canvas 的根資料夾叫「course files」，路徑裡不需要它
_ROOT_FOLDER_NAMES = ("course files", "課程檔案", "files")


@dataclass
class CourseResult:
    course: dict
    dirname: str
    files_total: int = 0
    downloaded: int = 0
    skipped: int = 0
    bytes: int = 0
    assignments: int = 0
    announcements: int = 0
    events: int = 0
    pages: int = 0
    modules: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    results: list[CourseResult]
    out_dir: Path
    started_at: str
    requests: int = 0

    @property
    def downloaded(self) -> int:
        return sum(r.downloaded for r in self.results)

    @property
    def bytes(self) -> int:
        return sum(r.bytes for r in self.results)

    @property
    def failures(self) -> list[str]:
        return [f"{r.course.get('name')}：{msg}" for r in self.results for msg in r.failures]


def _clean_folder_path(full_name: str | None) -> str:
    parts = [p for p in str(full_name or "").split("/") if p]
    if parts and parts[0].lower() in _ROOT_FOLDER_NAMES:
        parts = parts[1:]
    return "/".join(parts)


class Scraper:
    def __init__(self, config: Config, client: CanvasClient, manifest: Manifest | None = None,
                 log=None, on_event=None):
        self.config = config
        self.client = client
        self.out_dir = Path(config.out_dir)
        self.manifest = manifest or Manifest.load(self.out_dir)
        self.log = log or (lambda *_: None)
        # 結構化進度事件；網頁介面用它畫每一門課的進度條
        self.on_event = on_event or (lambda _event: None)

    # ---- 課程清單 --------------------------------------------------------
    def list_courses(self) -> list[dict]:
        params = {
            "include": ["term", "teachers", "total_students", "concluded", "total_scores"],
            "state": ["available", "completed"] if self.config.enrollment_state == "all" else None,
        }
        if self.config.enrollment_state != "all":
            params["enrollment_state"] = self.config.enrollment_state
        courses = []
        for raw in self.client.paginate("courses", params):
            if raw.get("access_restricted_by_date") or not raw.get("id"):
                continue  # 尚未開放或已封存，讀不到內容
            course = normalize_course(raw)
            if self._matches(course):
                courses.append(course)
        courses.sort(key=lambda c: (c.get("term") or "", c.get("course_code") or "", c.get("id")))
        return courses

    def _matches(self, course: dict) -> bool:
        if self.config.terms:
            term = (course.get("term") or "").lower()
            if not any(t.lower() in term for t in self.config.terms):
                return False
        if self.config.course_filters:
            haystack = " ".join(
                str(course.get(k) or "") for k in ("id", "course_code", "name")
            ).lower()
            if not any(f.lower() in haystack for f in self.config.course_filters):
                return False
        return True

    # ---- 主流程 ----------------------------------------------------------
    def run(self, courses: list[dict] | None = None) -> RunResult:
        started_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        courses = courses if courses is not None else self.list_courses()
        self.log(f"找到 {len(courses)} 門符合條件的課程")
        results = []
        for index, course in enumerate(courses, 1):
            label = f"{course.get('course_code') or ''} {course.get('name')}".strip()
            self.log(f"[{index}/{len(courses)}] {label}")
            self.on_event({"type": "course_start", "index": index, "total": len(courses),
                           "course": label, "id": course.get("id")})
            try:
                result = self.sync_course(course)
                results.append(result)
                self.on_event({"type": "course_done", "course": label, "id": course.get("id"),
                               "downloaded": result.downloaded, "skipped": result.skipped,
                               "files": result.files_total})
            except ApiError as exc:
                self.log(f"  ! 課程擷取失敗：{exc}")
                results.append(CourseResult(course=course, dirname=course_dirname(course), failures=[str(exc)]))
                self.on_event({"type": "course_failed", "course": label, "id": course.get("id"),
                               "error": str(exc)})
        if not self.config.dry_run:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "README.md").write_text(
                index_markdown(results, started_at=started_at), encoding="utf-8"
            )
            for result in results:
                self.manifest.record_course(
                    result.course,
                    {"files": result.files_total, "downloaded": result.downloaded, "dir": result.dirname},
                )
            self.manifest.save()
        return RunResult(results=results, out_dir=self.out_dir, started_at=started_at, requests=self.client.request_count)

    # ---- 單一課程 --------------------------------------------------------
    def sync_course(self, course: dict) -> CourseResult:
        cfg = self.config
        cid = course["id"]
        dirname = course_dirname(course)
        course_dir = self.out_dir / dirname
        result = CourseResult(course=course, dirname=dirname)
        data: dict = {
            "course": course,
            "fetched_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if cfg.wants("syllabus"):
            data["syllabus_text"], data["syllabus_html"] = self._fetch_syllabus(cid)

        if cfg.wants("modules"):
            data["modules"] = [
                normalize_module(m)
                for m in self.client.paginate_safe(
                    f"courses/{cid}/modules", {"include": ["items"]}, label="課程單元"
                )
            ]
            result.modules = len(data["modules"])

        if cfg.wants("assignments"):
            data["assignments"] = [
                normalize_assignment(a)
                for a in self.client.paginate_safe(
                    f"courses/{cid}/assignments", {"include": ["submission"], "order_by": "due_at"}, label="作業"
                )
            ]
            result.assignments = len(data["assignments"])

        if cfg.wants("announcements"):
            raw_announcements = self.client.paginate_safe(
                f"courses/{cid}/discussion_topics", {"only_announcements": True}, label="公告"
            )
            data["announcements"] = [normalize_announcement(a) for a in raw_announcements]
            data["_announcement_attachments"] = [
                att for topic in raw_announcements for att in (topic.get("attachments") or [])
            ]
            result.announcements = len(data["announcements"])

        if cfg.wants("calendar"):
            data["events"] = self._fetch_events(cid)
            result.events = len(data["events"])

        if cfg.wants("pages"):
            data["pages"] = self._fetch_pages(cid)
            result.pages = len(data["pages"])

        files: list[dict] = []
        if cfg.wants("files"):
            files = self._collect_files(cid, data, result)
            data["files"] = files
            result.files_total = len(files)

        if not cfg.dry_run:
            self._write_course_docs(course_dir, data)
        if files:
            self._download_files(cid, files, course_dir / "files", result)
        self.log(
            f"  → 檔案 {result.files_total}（新增／更新 {result.downloaded}、沿用 {result.skipped}）"
            f"、作業 {result.assignments}、公告 {result.announcements}"
        )
        return result

    # ---- 各區塊 ----------------------------------------------------------
    def _fetch_syllabus(self, cid) -> tuple[str, str]:
        try:
            raw = self.client.get(f"courses/{cid}", {"include": ["syllabus_body"]}) or {}
        except (ForbiddenError, NotFoundError):
            return "", ""
        from .htmlutil import html_to_text

        body = raw.get("syllabus_body") or ""
        return html_to_text(body), body

    def _fetch_events(self, cid) -> list[dict]:
        """課程行事曆（考試、活動）。作業的截止日另有來源，這裡只取 type=event。"""
        raw_events = self.client.paginate_safe(
            "calendar_events",
            {"context_codes": [f"course_{cid}"], "type": "event", "all_events": True},
            label="行事曆",
        )
        events = [
            normalize_event(item)
            for item in raw_events
            if item.get("workflow_state") not in ("deleted",) and not item.get("hidden")
        ]
        return sorted(events, key=lambda e: e.get("start_at") or "")

    def _fetch_pages(self, cid) -> list[dict]:
        pages = []
        for raw in self.client.paginate_safe(f"courses/{cid}/pages", label="頁面"):
            slug = raw.get("url")
            body = None
            if slug:
                try:
                    body = (self.client.get(f"courses/{cid}/pages/{slug}") or {}).get("body")
                except (ForbiddenError, NotFoundError):
                    body = None
            pages.append(normalize_page(raw, body))
        return pages

    def _collect_files(self, cid, data: dict, result: CourseResult) -> list[dict]:
        """合併三個來源：檔案分頁、單元裡的檔案、內文／附件中引用的檔案。"""
        folders = {
            f.get("id"): _clean_folder_path(f.get("full_name"))
            for f in self.client.paginate_safe(f"courses/{cid}/folders", label="資料夾")
        }
        files: dict[int, dict] = {}
        for raw in self.client.paginate_safe(f"courses/{cid}/files", label="檔案清單"):
            if raw.get("id") is None:
                continue
            files[raw["id"]] = normalize_file(raw, folder_path=folders.get(raw.get("folder_id"), ""))

        wanted = self._referenced_file_ids(cid, data)
        missing = [fid for fid in wanted if fid not in files]
        if missing:
            self.log(f"  · 另外補抓 {len(missing)} 個內文／單元引用的檔案")
        for fid in missing:
            raw = self._fetch_file(cid, fid)
            if raw:
                files[fid] = normalize_file(raw, folder_path=folders.get(raw.get("folder_id"), "附件"))

        # 公告附件即使拿不到檔案物件，本身就帶著下載網址
        for att in data.get("_announcement_attachments") or []:
            if att.get("id") and att["id"] not in files and att.get("url"):
                files[att["id"]] = normalize_file(att, folder_path="附件")
        data.pop("_announcement_attachments", None)

        if not files:
            result.failures.append("沒有可下載的檔案（可能是課程關閉了檔案分頁）")
        return sorted(files.values(), key=lambda f: (f.get("folder_path") or "", f.get("name") or ""))

    def _referenced_file_ids(self, cid, data: dict) -> list[int]:
        ids: list[int] = []

        def add(values):
            for value in values:
                if value not in ids:
                    ids.append(value)

        for module in data.get("modules") or []:
            add(
                item["content_id"]
                for item in module.get("items") or []
                if item.get("type") == "File" and item.get("content_id")
            )
        for assignment in data.get("assignments") or []:
            add(extract_file_ids(assignment.get("description_html"), course_id=cid))
        for announcement in data.get("announcements") or []:
            add(extract_file_ids(announcement.get("message_html"), course_id=cid))
            add(announcement.get("attachment_ids") or [])
        for page in data.get("pages") or []:
            add(extract_file_ids(page.get("body_html"), course_id=cid))
        add(extract_file_ids(data.get("syllabus_html"), course_id=cid))
        return ids

    def _fetch_file(self, cid, file_id) -> dict | None:
        for path in (f"courses/{cid}/files/{file_id}", f"files/{file_id}"):
            try:
                return self.client.get(path)
            except (ForbiddenError, NotFoundError):
                continue
            except ApiError as exc:
                self.log(f"  · 檔案 {file_id} 取得失敗：{exc}")
                return None
        return None

    # ---- 輸出 ------------------------------------------------------------
    def _write_course_docs(self, course_dir: Path, data: dict) -> None:
        course_dir.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in data.items() if not k.startswith("_")}
        (course_dir / "course.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (course_dir / "course.md").write_text(course_markdown(data), encoding="utf-8")
        if data.get("assignments"):
            (course_dir / "assignments.md").write_text(
                assignments_markdown(data["assignments"]), encoding="utf-8"
            )
        if data.get("announcements"):
            (course_dir / "announcements.md").write_text(
                announcements_markdown(data["announcements"]), encoding="utf-8"
            )
        if data.get("pages"):
            pages_dir = course_dir / "pages"
            pages_dir.mkdir(exist_ok=True)
            taken: set[Path] = set()
            for page in data["pages"]:
                name = safe_name(f"{page.get('title') or page.get('url_slug') or 'page'}.md")
                dest = pages_dir / name
                if dest in taken:  # 同名頁面才需要編號，否則每次同步都覆寫同一個檔
                    dest = unique_path(dest, taken)
                taken.add(dest)
                dest.write_text(page_markdown(page), encoding="utf-8")

    # ---- 下載 ------------------------------------------------------------
    def _should_download(self, item: dict) -> str:
        """回傳跳過原因；空字串代表可以下載。"""
        cfg = self.config
        if item.get("locked") or not item.get("url"):
            return f"「{item.get('name')}」被鎖定或沒有下載網址"
        if cfg.max_file_bytes and (item.get("size") or 0) > cfg.max_file_bytes:
            return f"「{item.get('name')}」超過大小上限（{(item.get('size') or 0) / 1e6:.1f} MB）"
        return ""

    def _wanted_by_extension(self, item: dict) -> bool:
        if not self.config.extensions:
            return True
        parts = (item.get("name") or "").rsplit(".", 1)
        return len(parts) == 2 and parts[1].lower() in self.config.extensions

    def _resolve_dest(self, cid, item: dict, base: Path, taken: set[Path], owners: dict[Path, str]) -> Path:
        key = Manifest.key(cid, item.get("id"))
        entry = self.manifest.files.get(key)
        if entry and entry.get("path"):
            previous = Path(entry["path"])
            if previous not in taken:
                return previous  # 沿用上次的位置，避免每次同步都換檔名
        dest = base / safe_relpath(item.get("folder_path") or "") / safe_name(item.get("name") or "")
        if dest in taken or (dest.exists() and owners.get(dest, key) != key):
            dest = unique_path(dest, taken)
        return dest

    def _download_files(self, cid, files: list[dict], base: Path, result: CourseResult) -> None:
        cfg = self.config
        owners = {Path(v["path"]): k for k, v in self.manifest.files.items() if v.get("path")}
        taken: set[Path] = set()
        jobs: list[tuple[dict, Path]] = []

        for item in files:
            if not self._wanted_by_extension(item):
                continue
            reason = self._should_download(item)
            if reason:
                result.failures.append(reason)
                continue
            dest = self._resolve_dest(cid, item, base, taken, owners)
            taken.add(dest)
            if not cfg.force and self.manifest.is_current(cid, item, dest):
                result.skipped += 1
                continue
            jobs.append((item, dest))

        if not jobs:
            return
        if cfg.dry_run:
            for item, dest in jobs:
                self.log(f"  · [預演] 會下載 {dest}")
            result.downloaded = len(jobs)
            return

        label = f"{result.course.get('course_code') or ''} {result.course.get('name')}".strip()
        self.on_event({"type": "downloads_planned", "course": label, "id": cid, "total": len(jobs)})

        def worker(job):
            item, dest = job
            written = self.client.download(item["url"], dest, expected_size=item.get("size") or None)
            return item, dest, written

        with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as pool:
            for job, outcome in zip(jobs, pool.map(_safe(worker), jobs)):
                ok, value = outcome
                if not ok:
                    result.failures.append(f"「{job[0].get('name')}」下載失敗：{value}")
                    self.log(f"  ! 下載失敗：{job[0].get('name')}（{value}）")
                    continue
                item, dest, written = value
                self.manifest.record_file(cid, item, dest, written)
                result.downloaded += 1
                result.bytes += written
                self.log(f"  ↓ {dest.relative_to(self.out_dir)}")
                self.on_event({"type": "file_done", "course": label, "id": cid,
                               "done": result.downloaded, "total": len(jobs),
                               "name": item.get("name"), "bytes": written})


def _safe(fn):
    """讓執行緒池裡的例外變成回傳值，一個檔案失敗不會拖垮整批。"""

    def wrapper(job):
        try:
            return True, fn(job)
        except Exception as exc:  # noqa: BLE001
            return False, exc

    return wrapper
