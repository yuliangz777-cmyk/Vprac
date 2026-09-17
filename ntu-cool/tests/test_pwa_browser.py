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
            page.wait_for_selector(".status.done", timeout=60000)

            page.reload(wait_until="networkidle")
            self.assertTrue(page.evaluate("navigator.serviceWorker.controller !== null"),
                            "Service Worker 應該已經接管頁面")
            page.wait_for_selector("#upcoming .rows li", timeout=10000)
            online_rows = page.locator("#upcoming .rows li").count()
            self.assertGreater(online_rows, 0)

            # 拔掉網路：介面與上次的資料都該還在
            context.set_offline(True)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#upcoming .rows li", timeout=10000)
            self.assertEqual(page.locator("#upcoming .rows li").count(), online_rows)
            self.assertTrue(page.is_visible("#offline"), "離線時要看得到提示")
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
