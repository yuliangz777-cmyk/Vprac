"""用真的 Chromium 驗證 PWA：Service Worker 會註冊，斷網後仍打得開。

這些事情沒辦法用假的 HTTP client 驗證——要有真的瀏覽器才有 Service Worker。
"""

import contextlib
import os
import tempfile
import threading
import unittest
from pathlib import Path

import _support  # noqa: F401

from fake_canvas import TOKEN, FakeCanvas

from ntucool.config import load_config
from ntucool.web import create_server

CHROMIUM = os.environ.get("NTUCOOL_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return os.path.exists(CHROMIUM)


@unittest.skipUnless(_playwright_available(), "需要 Playwright 與 Chromium")
class TestInstallableAndOffline(unittest.TestCase):
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
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    @contextlib.contextmanager
    def browser(self):
        """瀏覽器必須在 sync_playwright 區塊內關閉，不能丟給 addCleanup。"""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as driver:
            instance = driver.chromium.launch(executable_path=CHROMIUM)
            try:
                yield instance
            finally:
                instance.close()

    def test_service_worker_registers_and_the_page_still_opens_offline(self):
        with self.browser() as browser:
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            page.goto(self.url, wait_until="networkidle")
            page.wait_for_function(
                "navigator.serviceWorker && navigator.serviceWorker.ready.then(() => true)", timeout=20000
            )

            page.click("#go")
            page.wait_for_selector("#statusLine.done", timeout=60000)

            page.reload(wait_until="networkidle")
            self.assertTrue(page.evaluate("navigator.serviceWorker.controller !== null"),
                            "Service Worker 應該已經接管頁面")
            page.wait_for_selector("#upcoming .row", timeout=10000)
            online_rows = page.locator("#upcoming .row").count()
            self.assertGreater(online_rows, 0)

            # 拔掉網路：介面與上次的資料都該還在
            context.set_offline(True)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#upcoming .row", timeout=10000)
            self.assertEqual(page.locator("#upcoming .row").count(), online_rows)
            self.assertTrue(page.is_visible("#offline"), "離線時要看得到提示")
            self.assertEqual(errors, [])

    def test_tabs_and_course_detail_work(self):
        with self.browser() as browser:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(self.url, wait_until="networkidle")

            page.click("#go")                       # 首頁的「同步新文件」
            page.wait_for_selector("#statusLine.done", timeout=60000)
            self.assertEqual(page.locator(".download-item").count(), 2)

            page.click("[data-target=courses]")
            page.wait_for_selector(".course-card", timeout=10000)
            self.assertEqual(page.locator(".course-card").count(), 2)

            page.click(".course-card")
            page.wait_for_selector(".file-row", timeout=10000)
            self.assertGreater(page.locator(".file-row").count(), 3)
            self.assertIn("資料結構與演算法", page.inner_text("#courseDetail"))

            page.click("[data-target=settings]")
            self.assertIn("已連結", page.inner_text("#settingsState"))
            self.assertEqual(errors, [])

    def test_one_click_and_multi_select_downloads(self):
        """把檔案打包送到裝置上：課程卡一鍵、內頁一鍵、勾選多個、打包全部。"""
        import tempfile
        import zipfile

        with self.browser() as browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(self.url, wait_until="networkidle")
            page.click("#go")
            page.wait_for_selector("#statusLine.done", timeout=60000)

            def saved(download):
                target = Path(tempfile.mkdtemp()) / download.suggested_filename
                download.save_as(target)
                return zipfile.ZipFile(target)

            page.click("[data-target=courses]")
            page.wait_for_selector(".course-card")
            with page.expect_download() as info:
                page.click(".course-card .iconbtn")          # 課程卡上的一鍵下載
            whole = saved(info.value)
            self.assertIsNone(whole.testzip())
            self.assertGreater(len(whole.namelist()), 3)
            self.assertIn("CSIE1212", info.value.suggested_filename)

            page.click(".course-card")
            page.wait_for_selector(".file-row")
            boxes = page.locator(".file-row input[type=checkbox]")
            boxes.nth(0).check()
            boxes.nth(2).check()
            page.wait_for_selector("#actionbar:not(.hide)")
            self.assertIn("已選 2 個", page.inner_text("#pickedLabel"))

            with page.expect_download() as info:
                page.click("#pickedGo")                       # 只下載勾選的
            picked = saved(info.value)
            self.assertEqual(len(picked.namelist()), 2)

            page.click("text=全選／取消")
            self.assertIn("已選", page.inner_text("#pickedLabel"))
            page.click("[data-target=downloads]")
            self.assertFalse(page.is_visible("#actionbar"), "換分頁時動作列要收起來")

            with page.expect_download() as info:
                page.click("#zipAll")                         # 打包全部課程
            everything = saved(info.value)
            self.assertGreater(len(everything.namelist()), len(whole.namelist()))
            self.assertEqual(errors, [])

    def test_semester_selector_and_calendar(self):
        with self.browser() as browser:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(self.url, wait_until="networkidle")
            page.click("#go")
            page.wait_for_selector("#statusLine.done", timeout=60000)

            page.click("[data-target=home]")
            page.wait_for_selector("#eventsHead:not(.hide)", timeout=10000)
            calendar = page.inner_text("#events")
            self.assertIn("期中考", calendar)
            self.assertIn("資訊館 104", calendar)

            page.click("[data-target=courses]")
            page.wait_for_selector(".course-card")
            self.assertIn("113-2（2 門）", page.locator("#termSelect").inner_text())
            page.select_option("#termSelect", "113-2")
            page.wait_for_timeout(600)
            self.assertEqual(page.locator(".course-card").count(), 2)

            page.reload(wait_until="networkidle")      # 選好的學期要記得
            page.wait_for_timeout(800)
            self.assertEqual(page.input_value("#termSelect"), "113-2")
            self.assertEqual(errors, [])

    def test_search_diagnostics_and_delete(self):
        with self.browser() as browser:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto(self.url, wait_until="networkidle")
            page.click("#go")
            page.wait_for_selector("#statusLine.done", timeout=60000)

            # 搜尋
            page.click("[data-target=courses]")
            page.wait_for_selector(".course-card")
            page.fill("#searchBox", "投影片")
            page.wait_for_selector("#searchResults .row", timeout=10000)
            self.assertIn("week1-投影片.pdf", page.inner_text("#searchResults"))
            self.assertFalse(page.is_visible("#courseGrid"))
            page.fill("#searchBox", "找不到的東西zzz")
            page.wait_for_selector("#searchResults .empty", timeout=10000)
            page.fill("#searchBox", "")                     # 清空要回到課程牆
            page.wait_for_selector(".course-card", timeout=10000)

            # 診斷
            page.click("[data-target=settings]")
            page.click("text=診斷資訊")
            page.wait_for_function("document.getElementById('diag').textContent.includes('模式')", timeout=10000)
            diagnostics = page.inner_text("#diag")
            self.assertIn("本機伺服器", diagnostics)
            self.assertIn("API 呼叫", diagnostics)
            self.assertNotIn(TOKEN, diagnostics)

            # 刪除
            page.click("[data-target=courses]")
            page.wait_for_selector(".course-card")
            before = page.locator(".course-card").count()
            page.click(".course-card")
            page.wait_for_selector(".file-row")
            page.click("text=刪除已下載的檔案")
            page.wait_for_function(
                f"document.querySelectorAll('.course-card').length === {before - 1}", timeout=15000)
            self.assertEqual(errors, [])

    def test_manifest_link_carries_the_key_so_the_installed_app_can_get_in(self):
        with self.browser() as browser:
            page = browser.new_page()
            page.goto(self.url, wait_until="domcontentloaded")
            href = page.evaluate("document.querySelector('link[rel=manifest]').href")
            self.assertIn(f"k={self.httpd.app.key}", href)

            manifest = page.evaluate(
                "fetch(document.querySelector('link[rel=manifest]').href).then(r => r.json())"
            )
            self.assertEqual(manifest["start_url"], f"/?k={self.httpd.app.key}")
            self.assertEqual(manifest["display"], "standalone")


if __name__ == "__main__":
    unittest.main()
