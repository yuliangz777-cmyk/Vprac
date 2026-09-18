"""本機網頁介面測試：真的起伺服器、真的用 HTTP 打它。"""

import io
import json
import tempfile
import zipfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
        self.assertIn("NTU Course Hub", body.decode("utf-8"))

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
        status, body, _ = self.get("/favicon.ico", key=False)
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")


class TestPwaAssets(WebTestCase):
    """要能「加到主畫面」：manifest、icon、Service Worker 都得拿得到。"""

    def test_icons_are_real_pngs_and_need_no_key(self):
        for path, expected in (("/icon-192.png", 192), ("/icon-512.png", 512),
                               ("/apple-touch-icon.png", 180), ("/icon-512-maskable.png", 512)):
            status, body, headers = self.get(path, key=False)
            self.assertEqual(status, 200, path)
            self.assertEqual(headers["Content-Type"], "image/png", path)
            self.assertTrue(body.startswith(b"\x89PNG\r\n\x1a\n"), path)
            width = int.from_bytes(body[16:20], "big")   # IHDR 的寬度
            self.assertEqual(width, expected, path)

    def test_service_worker_is_served_from_the_root_with_a_js_type(self):
        status, body, headers = self.get("/sw.js", key=False)
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(headers.get("Service-Worker-Allowed"), "/")
        self.assertIn("addEventListener('fetch'", body.decode("utf-8"))

    def test_manifest_needs_the_key_because_start_url_carries_it(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/manifest.webmanifest", key=False)
        self.assertEqual(caught.exception.code, 403)

        status, body, headers = self.get("/manifest.webmanifest")
        self.assertEqual(status, 200)
        self.assertIn("manifest+json", headers["Content-Type"])
        data = json.loads(body)
        self.assertEqual(data["start_url"], f"/?k={self.key}")
        self.assertEqual(data["display"], "standalone")
        self.assertIn("maskable", [icon["purpose"] for icon in data["icons"]])

    def test_page_carries_the_key_into_the_manifest_link(self):
        _, body, _ = self.get("/")
        page = body.decode("utf-8")
        self.assertIn(f'href="/manifest.webmanifest?k={self.key}"', page)
        self.assertIn('rel="apple-touch-icon"', page)
        self.assertIn("navigator.serviceWorker.register('/sw.js')", page)
        self.assertNotIn("__KEY__", page)

    def test_downloads_and_progress_are_never_cached_by_the_worker(self):
        _, body, _ = self.get("/sw.js", key=False)
        worker = body.decode("utf-8")
        for path in ("/files/", "/api/progress", "/api/sync"):
            self.assertIn(f"'{path}'", worker)


class TestDashboard(WebTestCase):
    """跨課程的「近期作業 + 成績」，資料直接讀抓下來的 course.json。"""

    def write_course(self, name, assignments, *, score=None, grade=None):
        course_dir = self.out / name
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / "course.json").write_text(
            json.dumps(
                {
                    "course": {"name": name, "course_code": name.split("-")[0], "score": score, "grade": grade},
                    "assignments": assignments,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def assignment(name, days, *, submitted=False):
        due = datetime.now(timezone.utc) + timedelta(days=days)
        return {"name": name, "due_at": due.strftime("%Y-%m-%dT%H:%M:%SZ"), "submitted": submitted}

    def test_orders_by_due_date_and_marks_overdue(self):
        self.write_course("CSIE1212-x", [
            self.assignment("下週的", 6),
            self.assignment("明天的", 1),
            self.assignment("逾期沒交的", -2),
        ], score=92.5, grade="A")
        _, body, _ = self.get("/api/dashboard")
        data = json.loads(body)
        self.assertEqual([i["name"] for i in data["upcoming"]], ["逾期沒交的", "明天的", "下週的"])
        self.assertTrue(data["upcoming"][0]["overdue"])
        self.assertFalse(data["upcoming"][1]["overdue"])
        self.assertEqual(data["grades"], [{"course": "CSIE1212", "name": "CSIE1212-x", "score": 92.5, "grade": "A"}])

    def test_hides_what_you_do_not_need_to_act_on(self):
        self.write_course("C1", [
            self.assignment("早就交了的", -3, submitted=True),   # 過期但已繳交
            self.assignment("太久以前的", -40),                  # 超過 7 天前
            self.assignment("太遙遠的", 60),                     # 超過 30 天後
            self.assignment("沒有截止日的", 2),
        ])
        self.write_course("C2", [{"name": "沒設截止日", "due_at": None, "submitted": False}])
        _, body, _ = self.get("/api/dashboard")
        self.assertEqual([i["name"] for i in json.loads(body)["upcoming"]], ["沒有截止日的"])

    def test_merges_every_course_and_labels_each_row(self):
        self.write_course("CSIE1212-資料結構", [self.assignment("HW1", 2)])
        self.write_course("PHYS1001-普通物理", [self.assignment("實驗報告", 1)])
        _, body, _ = self.get("/api/dashboard")
        rows = json.loads(body)["upcoming"]
        self.assertEqual([(r["course"], r["name"]) for r in rows],
                         [("PHYS1001", "實驗報告"), ("CSIE1212", "HW1")])

    def test_survives_a_broken_course_json(self):
        self.write_course("good", [self.assignment("HW", 1)])
        broken = self.out / "broken"
        broken.mkdir(parents=True, exist_ok=True)
        (broken / "course.json").write_text("{壞掉", encoding="utf-8")
        _, body, _ = self.get("/api/dashboard")
        self.assertEqual(len(json.loads(body)["upcoming"]), 1)

    def test_empty_before_the_first_sync(self):
        _, body, _ = self.get("/api/dashboard")
        data = json.loads(body)
        self.assertEqual(data["upcoming"], [])
        self.assertEqual(data["grades"], [])

    def test_real_sync_populates_the_dashboard(self):
        self.sync_and_wait()
        _, body, _ = self.get("/api/dashboard")
        data = json.loads(body)
        names = [i["name"] for i in data["upcoming"]]
        self.assertIn("HW0 環境設定", names)      # 逾期未交
        self.assertIn("HW1 複雜度證明", names)    # 三天後到期、已繳交
        self.assertTrue(next(i for i in data["upcoming"] if i["name"] == "HW0 環境設定")["overdue"])
        self.assertEqual(next(g for g in data["grades"] if g["course"] == "CSIE1212")["score"], 92.5)


class TestCourseEndpoints(WebTestCase):
    """課程分頁與課程內頁的資料。"""

    def test_courses_list_after_a_sync(self):
        self.sync_and_wait()
        _, body, _ = self.get("/api/courses")
        courses = json.loads(body)["courses"]
        self.assertEqual({c["code"] for c in courses}, {"CSIE1212", "PHYS1001"})
        csie = next(c for c in courses if c["code"] == "CSIE1212")
        self.assertEqual(csie["teacher"], "王教授")
        self.assertEqual(csie["term"], "113-2")
        self.assertEqual(csie["score"], 92.5)
        self.assertEqual(csie["files"], 4)          # 只算 files/ 底下真正下載的
        self.assertTrue(csie["size"].endswith("B"))
        self.assertEqual(csie["assignments"], 2)

    def test_course_detail_lists_files_and_assignments(self):
        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        _, body, _ = self.get(f"/api/course?dir={urllib.request.quote(dirname)}")
        detail = json.loads(body)
        self.assertEqual(detail["name"], "資料結構與演算法")
        names = [f["name"] for f in detail["files"]]
        self.assertIn("week1-投影片.pdf", names)
        self.assertIn("course.md", names)
        pdf = next(f for f in detail["files"] if f["name"] == "week1-投影片.pdf")
        self.assertEqual(pdf["ext"], "PDF")
        self.assertTrue(pdf["path"].startswith(dirname))
        self.assertEqual([a["name"] for a in detail["assignments"]][0], "HW1 複雜度證明")

    def test_course_detail_cannot_escape_the_output_folder(self):
        for attempt in ("..", "../..", "/etc"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(f"/api/course?dir={urllib.request.quote(attempt)}")
            self.assertEqual(caught.exception.code, 404, attempt)

    def test_course_detail_unknown_name(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/course?dir=nope")
        self.assertEqual(caught.exception.code, 404)

    def test_status_reports_storage(self):
        self.sync_and_wait()
        data = json.loads(self.get("/api/status")[1])
        self.assertGreater(data["files"], 0)
        self.assertGreater(data["bytes"], 0)
        self.assertEqual(data["term"], "113-2")
        self.assertFalse(data["syncing"])


class TestZipDownload(WebTestCase):
    """一鍵下載與多選下載：把檔案打包成 zip 送到使用者的裝置上。"""

    def zip_from(self, path):
        status, body, headers = self.get(path)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        return zipfile.ZipFile(io.BytesIO(body)), headers

    def test_one_click_downloads_a_whole_course(self):
        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        archive, headers = self.zip_from(f"/api/zip?dir={urllib.request.quote(dirname)}")
        names = archive.namelist()
        self.assertIn(f"{dirname}/files/講義/第一週/week1-投影片.pdf", names)
        self.assertIn(f"{dirname}/course.md", names)
        self.assertIsNone(archive.testzip())          # 每個項目都讀得出來
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn(urllib.request.quote(f"{dirname}.zip"), headers["Content-Disposition"])

    def test_zip_contents_match_the_originals(self):
        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        archive, _ = self.zip_from(f"/api/zip?dir={urllib.request.quote(dirname)}")
        inside = archive.read(f"{dirname}/files/講義/第一週/week1-投影片.pdf")
        self.assertEqual(inside, (self.out / dirname / "files/講義/第一週/week1-投影片.pdf").read_bytes())

    def test_download_everything(self):
        self.sync_and_wait()
        archive, headers = self.zip_from("/api/zip?all=1")
        self.assertGreater(len(archive.namelist()), 5)
        self.assertIn("NTU-Course-Hub.zip", urllib.request.unquote(headers["Content-Disposition"]))
        self.assertFalse([n for n in archive.namelist() if "/." in n or n.startswith(".")])

    def test_multi_select_goes_through_a_ticket(self):
        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        detail = json.loads(self.get(f"/api/course?dir={urllib.request.quote(dirname)}")[1])
        chosen = [f["path"] for f in detail["files"] if f["name"].endswith((".pdf", ".zip"))][:3]

        status, result = self.post("/api/zip-ticket", {"paths": chosen, "name": "我選的講義"})
        self.assertEqual(status, 200)
        self.assertEqual(result["files"], len(chosen))
        self.assertGreater(result["bytes"], 0)

        archive, headers = self.zip_from(f"/api/zip?ticket={result['ticket']}")
        self.assertEqual(sorted(archive.namelist()), sorted(chosen))
        self.assertIn("我選的講義", urllib.request.unquote(headers["Content-Disposition"]))

    def test_ticket_ignores_paths_outside_the_output_folder(self):
        self.sync_and_wait()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/zip-ticket", {"paths": ["../../etc/passwd", "nope.pdf"], "name": "x"})
        self.assertEqual(caught.exception.code, 404)   # 全部無效 → 沒有東西可打包

    def test_ticket_keeps_only_the_valid_paths(self):
        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        good = f"{dirname}/course.md"
        _, result = self.post("/api/zip-ticket", {"paths": [good, "../../etc/passwd"], "name": "mix"})
        self.assertEqual(result["files"], 1)
        archive, _ = self.zip_from(f"/api/zip?ticket={result['ticket']}")
        self.assertEqual(archive.namelist(), [good])

    def test_expired_or_unknown_ticket(self):
        from ntucool import web as web_module

        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        _, result = self.post("/api/zip-ticket", {"paths": [f"{dirname}/course.md"], "name": "x"})
        self.httpd.app.tickets[result["ticket"]]["created"] -= web_module.TICKET_TTL + 1
        for query in (f"?ticket={result['ticket']}", "?ticket=nonsense", "?dir=nope", ""):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get("/api/zip" + query)
            self.assertEqual(caught.exception.code, 404, query)

    def test_tickets_do_not_pile_up(self):
        self.sync_and_wait()
        dirname = next(c["dir"] for c in json.loads(self.get("/api/courses")[1])["courses"]
                       if c["code"] == "CSIE1212")
        for _ in range(40):
            self.post("/api/zip-ticket", {"paths": [f"{dirname}/course.md"], "name": "x"})
        self.assertLessEqual(len(self.httpd.app.tickets), 32)

    def test_empty_selection_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/zip-ticket", {"paths": []})
        self.assertEqual(caught.exception.code, 400)

    def test_zip_needs_the_key(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/zip?all=1", key=False)
        self.assertEqual(caught.exception.code, 403)


class TestProgressAggregation(WebTestCase):
    """每門課的進度條：由 Scraper 丟出的事件累積而成。"""

    def job(self):
        from ntucool.web import SyncJob

        return SyncJob()

    def test_percent_tracks_downloaded_files(self):
        job = self.job()
        job.handle({"type": "course_start", "course": "A"})
        self.assertEqual(job.snapshot(0)["courses"][0]["state"], "running")
        job.handle({"type": "downloads_planned", "course": "A", "total": 4})
        job.handle({"type": "file_done", "course": "A", "done": 1, "total": 4})
        self.assertEqual(job.snapshot(0)["courses"][0]["percent"], 25)
        job.handle({"type": "course_done", "course": "A", "downloaded": 4, "skipped": 1})
        done = job.snapshot(0)["courses"][0]
        self.assertEqual((done["percent"], done["state"], done["skipped"]), (100, "done", 1))

    def test_course_with_nothing_to_download_still_completes(self):
        job = self.job()
        job.handle({"type": "course_start", "course": "B"})
        job.handle({"type": "course_done", "course": "B", "downloaded": 0})
        self.assertEqual(job.snapshot(0)["courses"][0]["percent"], 100)

    def test_failures_are_visible(self):
        job = self.job()
        job.handle({"type": "course_start", "course": "C"})
        job.handle({"type": "course_failed", "course": "C", "error": "403"})
        entry = job.snapshot(0)["courses"][0]
        self.assertEqual(entry["state"], "failed")
        self.assertEqual(entry["error"], "403")

    def test_order_is_preserved(self):
        job = self.job()
        for name in ("第一門", "第二門", "第三門"):
            job.handle({"type": "course_start", "course": name})
        self.assertEqual([c["course"] for c in job.snapshot(0)["courses"]], ["第一門", "第二門", "第三門"])

    def test_real_sync_reports_every_course(self):
        self.sync_and_wait()
        _, body, _ = self.get("/api/progress?from=0")
        courses = json.loads(body)["courses"]
        self.assertEqual(len(courses), 2)
        self.assertTrue(all(c["state"] == "done" and c["percent"] == 100 for c in courses))


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
