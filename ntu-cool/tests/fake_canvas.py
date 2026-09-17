"""測試用的假 Canvas 站台：在本機起一個真的 HTTP server。

比起 mock，這能真正驗證分頁（Link 標頭）、授權標頭、重試與檔案下載。
"""

from __future__ import annotations

import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "test-token"

PDF_BYTES = b"%PDF-1.4 fake lecture slides\n" * 4
ZIP_BYTES = b"PK\x03\x04 fake homework bundle\n" * 3

COURSES = [
    {
        "id": 101,
        "name": "資料結構與演算法",
        "course_code": "CSIE1212",
        "html_url": "http://example/courses/101",
        "term": {"id": 9, "name": "113-2"},
        "teachers": [{"display_name": "王教授"}],
        "enrollments": [{"enrollment_state": "active"}],
    },
    {
        "id": 202,
        "name": "普通物理學",
        "course_code": "PHYS1001",
        "html_url": "http://example/courses/202",
        "term": {"id": 9, "name": "113-2"},
        "teachers": [{"display_name": "李教授"}],
        "enrollments": [{"enrollment_state": "active"}],
    },
    {
        "id": 303,
        "name": "已封存的課",
        "access_restricted_by_date": True,
    },
]

FOLDERS = {
    101: [
        {"id": 1, "full_name": "course files"},
        {"id": 2, "full_name": "course files/講義"},
        {"id": 3, "full_name": "course files/講義/第一週"},
    ],
    202: [],
}

FILES = {
    101: [
        {
            "id": 5001,
            "folder_id": 3,
            "display_name": "week1-投影片.pdf",
            "filename": "week1.pdf",
            "size": len(PDF_BYTES),
            "content-type": "application/pdf",
            "updated_at": "2026-02-20T03:00:00Z",
            "url": "/files/download/5001",
        },
        {
            "id": 5002,
            "folder_id": 2,
            "display_name": "課程大綱.pdf",
            "size": len(PDF_BYTES),
            "content-type": "application/pdf",
            "updated_at": "2026-02-18T03:00:00Z",
            "url": "/files/download/5002",
        },
        {
            "id": 5003,
            "folder_id": 1,
            "display_name": "鎖住的期末考卷.pdf",
            "size": 10,
            "updated_at": "2026-06-01T03:00:00Z",
            "url": "",
            "locked_for_user": True,
        },
    ],
    202: [],  # 這門課關閉了檔案分頁 → /files 回 403
}

# 只存在於「單元」與公告內文裡、不在檔案分頁清單中的檔案
EXTRA_FILES = {
    5100: {
        "id": 5100,
        "folder_id": 2,
        "display_name": "補充教材.zip",
        "size": len(ZIP_BYTES),
        "content-type": "application/zip",
        "updated_at": "2026-03-02T03:00:00Z",
        "url": "/files/download/5100",
    },
    5200: {
        "id": 5200,
        "display_name": "公告附件.pdf",
        "size": len(PDF_BYTES),
        "updated_at": "2026-03-05T03:00:00Z",
        "url": "/files/download/5200",
    },
}

FILE_BODIES = {5001: PDF_BYTES, 5002: PDF_BYTES, 5100: ZIP_BYTES, 5200: PDF_BYTES}

MODULES = {
    101: [
        {
            "id": 11,
            "name": "第一週：複雜度分析",
            "position": 1,
            "workflow_state": "active",
            "items": [
                {"id": 1, "title": "投影片", "type": "File", "content_id": 5001, "indent": 0},
                {"id": 2, "title": "補充教材", "type": "File", "content_id": 5100, "indent": 1},
                {"id": 3, "title": "課程公告", "type": "Page", "page_url": "welcome", "indent": 0},
            ],
        }
    ],
    202: [],
}

ASSIGNMENTS = {
    101: [
        {
            "id": 701,
            "name": "HW1 複雜度證明",
            "due_at": "2026-03-10T15:59:00Z",
            "points_possible": 10,
            "submission_types": ["online_upload"],
            "html_url": "http://example/courses/101/assignments/701",
            "description": '<p>請參考 <a href="/courses/101/files/5100">補充教材</a></p>',
            "submission": {"submitted_at": "2026-03-09T10:00:00Z", "score": 9.5, "workflow_state": "graded"},
        }
    ],
    202: [],
}

ANNOUNCEMENTS = {
    101: [
        {
            "id": 801,
            "title": "第一次上課須知",
            "posted_at": "2026-02-19T01:00:00Z",
            "author": {"display_name": "王教授"},
            "message": "<p>請先閱讀大綱</p>",
            "attachments": [EXTRA_FILES[5200]],
        }
    ],
    202: [],
}

PAGES = {
    101: [{"page_id": 1, "url": "welcome", "title": "課程公告", "updated_at": "2026-02-19T01:00:00Z"}],
    202: [],
}
PAGE_BODIES = {"welcome": "<h1>歡迎</h1><p>本課程使用 C++。</p>"}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 測試輸出保持乾淨
        pass

    # ---- 工具 ----
    def _send(self, status: int, payload=None, *, raw: bytes | None = None, headers: dict | None = None):
        if raw is not None:
            body = raw
        else:
            # 真實 Canvas 回傳絕對下載網址；測試站台的埠號要到執行時才知道，所以在這裡補上。
            text = json.dumps(payload, ensure_ascii=False)
            body = text.replace('"/files/download/', f'"{self.server.base_url}/files/download/').encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if raw is not None else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Rate-Limit-Remaining", "700")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _page(self, items: list, path: str, query: dict):
        """一頁兩筆，藉此逼出 Link: rel="next" 的分頁流程。"""
        per_page = int(query.get("per_page", ["100"])[0])
        page = int(query.get("page", ["1"])[0])
        size = min(per_page, 2)
        start = (page - 1) * size
        chunk = items[start : start + size]
        headers = {}
        if start + size < len(items):
            headers["Link"] = f'<{self.server.base_url}{path}?page={page + 1}&per_page={per_page}>; rel="next"'
        self._send(200, chunk, headers=headers)

    # ---- 路由 ----
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        auth = self.headers.get("Authorization")

        if path.startswith("/files/download/"):
            file_id = int(path.rsplit("/", 1)[1])
            body = FILE_BODIES.get(file_id)
            if body is None:
                return self._send(404, {"errors": [{"message": "not found"}]})
            if self.server.truncate_once.get(file_id):
                self.server.truncate_once[file_id] = False
                return self._send(200, raw=body[: len(body) // 2])
            return self._send(200, raw=body)

        if auth != f"Bearer {TOKEN}":
            return self._send(401, {"errors": [{"message": "Invalid access token."}]})

        if path == "/api/v1/flaky":
            self.server.flaky_hits += 1
            if self.server.flaky_hits <= self.server.flaky_failures:
                return self._send(500, {"errors": [{"message": "boom"}]})
            return self._send(200, {"ok": True, "hits": self.server.flaky_hits})

        if path == "/api/v1/ratelimited":
            return self._send(403, {"message": "403 Forbidden (Rate Limit Exceeded)"})

        if path == "/api/v1/users/self/profile":
            return self._send(200, {"id": 1, "name": "測試同學", "primary_email": "student@ntu.edu.tw"})

        if path == "/api/v1/courses":
            state = (query.get("enrollment_state") or [None])[0]
            courses = COURSES if state in (None, "active", "all") else []
            return self._page(courses, path, query)

        match = re.match(r"^/api/v1/courses/(\d+)(/.*)?$", path)
        if match:
            cid, rest = int(match.group(1)), match.group(2) or ""
            course = next((c for c in COURSES if c["id"] == cid), None)
            if course is None:
                return self._send(404, {"errors": [{"message": "not found"}]})
            if rest == "":
                payload = dict(course)
                if "syllabus_body" in query.get("include[]", []):
                    payload["syllabus_body"] = "<p>評分方式：作業 40%、期末 60%</p>"
                return self._send(200, payload)
            if rest == "/folders":
                return self._page(FOLDERS.get(cid, []), path, query)
            if rest == "/files":
                if cid == 202:
                    return self._send(403, {"status": "unauthorized"})
                return self._page(FILES.get(cid, []), path, query)
            file_match = re.match(r"^/files/(\d+)$", rest)
            if file_match:
                fid = int(file_match.group(1))
                found = next((f for f in FILES.get(cid, []) if f["id"] == fid), None) or EXTRA_FILES.get(fid)
                return self._send(200, found) if found else self._send(404, {"errors": []})
            if rest == "/modules":
                return self._page(MODULES.get(cid, []), path, query)
            if rest == "/assignments":
                return self._page(ASSIGNMENTS.get(cid, []), path, query)
            if rest == "/discussion_topics":
                return self._page(ANNOUNCEMENTS.get(cid, []), path, query)
            if rest == "/pages":
                return self._page(PAGES.get(cid, []), path, query)
            page_match = re.match(r"^/pages/([\w-]+)$", rest)
            if page_match:
                slug = page_match.group(1)
                meta = next((p for p in PAGES.get(cid, []) if p["url"] == slug), None)
                if not meta:
                    return self._send(404, {"errors": []})
                return self._send(200, {**meta, "body": PAGE_BODIES.get(slug, "")})
        return self._send(404, {"errors": [{"message": f"no route for {path}"}]})


class FakeCanvas:
    """`with FakeCanvas() as server:` 會起一個本機 Canvas 假站台。"""

    def __init__(self, *, flaky_failures: int = 0):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.flaky_failures = flaky_failures
        self.httpd.flaky_hits = 0
        self.httpd.truncate_once = {}
        self.port = self.httpd.server_address[1]
        self.httpd.base_url = self.base_url
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def api_root(self) -> str:
        return f"{self.base_url}/api/v1"

    def truncate_next_download(self, file_id: int):
        """讓下一次下載這個檔案時被截斷，用來測試「大小不符」的處理。"""
        self.httpd.truncate_once[file_id] = True

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
