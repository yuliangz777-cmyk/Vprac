"""用真的 Chromium 對假 NTU COOL 跑一次「用學校帳號登入」流程。"""

import os
import unittest

import _support  # noqa: F401

from fake_canvas import BROWSER_TOKEN, LOGIN_PASSWORD, LOGIN_USER, FakeCanvas

from ntucool import browser_login
from ntucool.errors import NtuCoolError

CHROMIUM = os.environ.get("NTUCOOL_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


@unittest.skipUnless(browser_login.is_available() and os.path.exists(CHROMIUM), "需要 Playwright 與 Chromium")
class TestBrowserLogin(unittest.TestCase):
    def setUp(self):
        self.server = FakeCanvas()
        self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.messages = []

    def run_login(self, *, fill, **kwargs):
        return browser_login.login_and_create_token(
            self.server.base_url,
            headless=True,
            executable_path=CHROMIUM,
            on_status=self.messages.append,
            fill_login=fill,
            **kwargs,
        )

    @staticmethod
    def _type_credentials(user, password):
        def fill(page):
            page.fill("#username", user)
            page.fill("#password", password)
            page.click("#submit")

        return fill

    def test_login_then_token_is_created_the_same_way_the_settings_page_does(self):
        token = self.run_login(fill=self._type_credentials(LOGIN_USER, LOGIN_PASSWORD))
        self.assertEqual(token, BROWSER_TOKEN)
        self.assertTrue(any("登入成功" in m for m in self.messages))

    def test_the_new_token_actually_works_against_the_api(self):
        from ntucool.client import CanvasClient

        token = self.run_login(fill=self._type_credentials(LOGIN_USER, LOGIN_PASSWORD))
        profile = CanvasClient(self.server.api_root, token).whoami()
        self.assertEqual(profile["name"], "測試同學")

    def test_wrong_password_times_out_instead_of_hanging_forever(self):
        with self.assertRaises(NtuCoolError) as caught:
            self.run_login(fill=self._type_credentials(LOGIN_USER, "wrong"), timeout=3)
        self.assertIn("等待登入超過", str(caught.exception))

    def test_purpose_is_passed_through_so_the_token_is_identifiable(self):
        """權杖在 NTU COOL 的設定頁上要看得出是這個工具建立的，才好撤銷。"""
        self.run_login(fill=self._type_credentials(LOGIN_USER, LOGIN_PASSWORD), purpose="ntucool-測試")
        self.assertEqual(self.server.last_token_purpose, "ntucool-測試")


class TestAvailability(unittest.TestCase):
    def test_missing_playwright_explains_how_to_install(self):
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.startswith("playwright"):
                raise ImportError("no playwright")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = blocked
        try:
            with self.assertRaises(NtuCoolError) as caught:
                browser_login.login_and_create_token("https://example.invalid")
            self.assertIn("pip install playwright", str(caught.exception))
        finally:
            builtins.__import__ = real_import


if __name__ == "__main__":
    unittest.main()
