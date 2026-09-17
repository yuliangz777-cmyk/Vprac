"""本機網頁介面測試：真的起伺服器、真的用 HTTP 打它。"""

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

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
