"""本機網頁介面測試：真的起伺服器、真的用 HTTP 打它。"""

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from dataclasses import replace
from unittest import mock

import _support  # noqa: F401

from fake_canvas import TOKEN, FakeCanvas

from ntucool.config import load_config
from ntucool.web import create_server


class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.canvas = FakeCanvas()
        self.canvas.__enter__()
        self.addCleanup(self.canvas.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "data"

        config = load_config(
            environ={"NTU_COOL_TOKEN": TOKEN},
            overrides={"base_url": self.canvas.base_url, "out_dir": self.out},
            config_candidates=(), env_candidates=(),
        ).validate()
        self.httpd, self.url = create_server(config, port=0)
        self.key = self.httpd.app.key
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def get(self, path, *, key=True, headers=None):
        sep = "&" if "?" in path else "?"
        url = self.base + path + (f"{sep}k={self.key}" if key else "")
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers.items())

    def post(self, path, payload):
        url = f"{self.base}{path}?k={self.key}"
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, json.loads(resp.read())

    def sync_and_wait(self, options=None, timeout=30):
        self.post("/api/sync", options or {})
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, body, _ = self.get("/api/progress?from=0")
            state = json.loads(body)
            if state["status"] != "running":
                return state
            time.sleep(0.05)
        self.fail("同步逾時")


class TestLogin(WebTestCase):
    """網頁上的登入流程：用存取權杖，不碰學校帳號密碼。"""

    def setUp(self):
        super().setUp()
        # 讓「登入」寫到暫存目錄，不要碰到真的 ~/.config
        self.env_file = Path(self.tmp.name) / "user.env"
        patcher = mock.patch("ntucool.web.save_token_to_env", lambda token: _write_env(self.env_file, token))
        patcher.start()
        self.addCleanup(patcher.stop)
        cleaner = mock.patch("ntucool.web.clear_saved_token", lambda: self.env_file.unlink(missing_ok=True))
        cleaner.start()
        self.addCleanup(cleaner.stop)
        self.httpd.app.config = replace(self.httpd.app.config, token="")  # 從未登入狀態開始

    def test_status_reports_not_authenticated(self):
        _, body, _ = self.get("/api/status")
        data = json.loads(body)
        self.assertFalse(data["authenticated"])
        self.assertEqual(data["user"], "")

    def test_sync_is_refused_before_login(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/sync", {})
        self.assertEqual(caught.exception.code, 401)

    def test_bad_token_is_rejected_and_not_saved(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/login", {"token": "wrong"})
        self.assertEqual(caught.exception.code, 401)
        self.assertIn("無效或已過期", json.loads(caught.exception.read())["error"])
        self.assertFalse(self.env_file.exists())

    def test_token_with_non_ascii_characters_is_rejected_cleanly(self):
        """貼到中文或全形字元時要回錯誤訊息，而不是把連線弄斷。"""
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/login", {"token": "這是錯的權杖"})
        self.assertEqual(caught.exception.code, 401)
        self.assertIn("不合法的字元", json.loads(caught.exception.read())["error"])
        self.assertFalse(self.env_file.exists())

    def test_empty_token_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/login", {"token": "   "})
        self.assertEqual(caught.exception.code, 401)

    def test_login_verifies_saves_and_enables_sync(self):
        status, data = self.post("/api/login", {"token": TOKEN})
        self.assertEqual(status, 200)
        self.assertEqual(data["user"], "測試同學")
        self.assertIn(f"NTU_COOL_TOKEN={TOKEN}", self.env_file.read_text(encoding="utf-8"))

        _, body, _ = self.get("/api/status")
        self.assertTrue(json.loads(body)["authenticated"])
        self.assertEqual(self.sync_and_wait()["status"], "done")
        self.assertTrue(any(self.out.rglob("week1-投影片.pdf")))

    def test_token_never_comes_back_in_responses(self):
        self.post("/api/login", {"token": TOKEN})
        for path in ("/api/status", "/api/files", "/api/progress?from=0"):
            _, body, _ = self.get(path)
            self.assertNotIn(TOKEN, body.decode("utf-8"), path)

    def test_logout_clears_the_saved_token(self):
        self.post("/api/login", {"token": TOKEN})
        status, _ = self.post("/api/logout", {})
        self.assertEqual(status, 200)
        self.assertFalse(self.env_file.exists())
        _, body, _ = self.get("/api/status")
        self.assertFalse(json.loads(body)["authenticated"])

    def test_expired_token_sends_you_back_to_the_login_screen(self):
        self.httpd.app.config = replace(self.httpd.app.config, token="no-longer-valid")
        _, body, _ = self.get("/api/status")
        self.assertFalse(json.loads(body)["authenticated"])


def _write_env(path: Path, token: str) -> Path:
    path.write_text(f"NTU_COOL_TOKEN={token}\n", encoding="utf-8")
    return path


class TestAccessControl(WebTestCase):
    def test_page_requires_the_key(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/", key=False)
        self.assertEqual(caught.exception.code, 403)

    def test_page_served_with_the_key(self):
        status, body, headers = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("NTU COOL 同步", body.decode("utf-8"))

    def test_wrong_key_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/status&k=nope", key=False)
        self.assertEqual(caught.exception.code, 403)

    def test_foreign_host_header_is_rejected(self):
        """擋 DNS rebinding：別的網域把自己指到 127.0.0.1 也進不來。"""
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/status", headers={"Host": "evil.example.com"})
        self.assertEqual(caught.exception.code, 403)

    def test_no_cors_headers_are_exposed(self):
        _, _, headers = self.get("/api/status")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_lan_url_is_shown_when_bound_to_all_interfaces(self):
        from ntucool.web import create_server, lan_ip

        httpd, url = create_server(self.httpd.app.config, host="0.0.0.0", port=0)
        httpd.server_close()
        self.assertNotIn("0.0.0.0", url)
        self.assertIn(lan_ip(), url)

    def test_url_contains_the_key(self):
        self.assertIn(f"k={self.key}", self.url)
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))


class TestEndpoints(WebTestCase):
    def test_status(self):
        self.sync_and_wait()
        _, body, _ = self.get("/api/status")
        data = json.loads(body)
        # 時間要是看得懂的本地時間，不是 2026-09-17T02:33:46+00:00
        self.assertRegex(data["last_sync"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertEqual(data["user"], "測試同學")
        self.assertEqual(data["base_url"], self.canvas.base_url)
        self.assertEqual(data["out_dir"], str(self.out.resolve()))

    def test_sync_runs_and_reports_progress(self):
        state = self.sync_and_wait()
        self.assertEqual(state["status"], "done")
        log = "\n".join(state["lines"])
        self.assertIn("資料結構與演算法", log)
        self.assertIn("完成：2 門課程", log)
        self.assertTrue(any(self.out.rglob("week1-投影片.pdf")))

    def test_sync_options_are_applied(self):
        state = self.sync_and_wait({"pdf_only": True, "courses": "CSIE1212"})
        self.assertEqual(state["status"], "done")
        self.assertFalse(any(self.out.rglob("*.zip")))
        self.assertFalse((self.out / "PHYS1001-普通物理學-202").exists())

    def test_second_sync_while_running_is_refused(self):
        self.httpd.app.job.status = "running"  # 假裝正在跑
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/sync", {})
        self.assertEqual(caught.exception.code, 409)

    def test_files_listing_and_download(self):
        self.sync_and_wait()
        _, body, _ = self.get("/api/files")
        courses = json.loads(body)["courses"]
        self.assertEqual(len(courses), 2)
        pdf = next(f for c in courses for f in c["files"] if f["name"].endswith("week1-投影片.pdf"))

        status, content, headers = self.get(f"/files/{urllib.request.quote(pdf['path'])}")
        self.assertEqual(status, 200)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertEqual(headers["Content-Type"], "application/pdf")

    def test_download_cannot_escape_the_output_folder(self):
        for attempt in ("/files/../../../etc/passwd", "/files/..%2f..%2fetc%2fpasswd"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(attempt)
            self.assertEqual(caught.exception.code, 404, attempt)

    def test_unexpected_errors_become_500_not_a_dropped_connection(self):
        with mock.patch.object(type(self.httpd.app), "files", side_effect=RuntimeError("boom")):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get("/api/files")
        self.assertEqual(caught.exception.code, 500)

    def test_unknown_path(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/nope")
        self.assertEqual(caught.exception.code, 404)


class TestAccessKey(WebTestCase):
    def test_key_is_reused_across_restarts_so_the_url_can_be_bookmarked(self):
        from ntucool.web import load_or_create_key

        first = load_or_create_key(self.out)
        self.assertEqual(load_or_create_key(self.out), first)
        self.assertNotEqual(load_or_create_key(self.out, rotate=True), first)

    def test_key_file_is_private(self):
        import stat as stat_module

        from ntucool.web import KEY_FILENAME, load_or_create_key

        load_or_create_key(self.out)
        mode = stat_module.S_IMODE((self.out / KEY_FILENAME).stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_browser_auto_requests_do_not_error(self):
        """瀏覽器自動索取 favicon 時不該噴 403，否則 console 一片紅。"""
        for path in ("/favicon.ico", "/apple-touch-icon.png"):
            status, body, _ = self.get(path, key=False)
            self.assertEqual(status, 204, path)
            self.assertEqual(body, b"")


class TestOptionMapping(WebTestCase):
    def test_config_for(self):
        app = self.httpd.app
        self.assertEqual(app.config_for({}).extensions, ())
        self.assertIn("pdf", app.config_for({"pdf_only": True}).extensions)
        self.assertEqual(app.config_for({"skip_big": True}).max_file_mb, 50.0)
        self.assertEqual(
            app.config_for({"courses": "CSIE1212, 演算法"}).course_filters, ("CSIE1212", "演算法")
        )


if __name__ == "__main__":
    unittest.main()
