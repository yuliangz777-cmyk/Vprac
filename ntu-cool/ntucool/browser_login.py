"""用學校帳號登入：開一個真正的瀏覽器，在真正的 NTU COOL 登入頁完成登入。

**為什麼不直接複製官方 App 的做法？**
官方 Canvas App 走的是 Canvas 的 OAuth2，用 Instructure 註冊在各校的 developer key
（client_id / client_secret 內建在 App 裡）。把那組金鑰挖出來冒用，等於偽裝成別人
註冊的應用程式，違反服務條款，我們不做。

**這裡的做法**：開一個真的瀏覽器視窗連到真正的 `cool.ntu.edu.tw` 登入頁，
你的帳號密碼（和二階段驗證）只輸入在官方頁面上；登入完成後，工具用**跟你手動點
「帳戶 → 設定 → 新增存取權杖」完全相同的方式**產生一支個人存取權杖，存到本機。
之後的擷取就跟官方 App 一樣走 `/api/v1`。

權杖隨時可以在 NTU COOL 的設定頁自行撤銷。
"""

from __future__ import annotations

import time
import urllib.parse

from .errors import NtuCoolError

INSTALL_HINT = (
    "這個功能需要 Playwright：\n"
    "    pip install playwright\n"
    "    playwright install chromium"
)

#: 登入完成的判斷：這個端點回 200 就代表瀏覽器已經有有效的 session
PROBE_PATH = "/api/v1/users/self/profile"

#: Canvas 設定頁建立權杖時打的端點（跟畫面上按按鈕是同一條路）
TOKEN_PATH = "/profile/tokens"

#: 找得到這個就代表已經在設定頁，可以拿到新鮮的 CSRF cookie
SETTINGS_PATH = "/profile/settings"


def is_available() -> bool:
    """有沒有裝 Playwright。"""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _csrf_from(context) -> str:
    """Canvas 把 CSRF token 放在 `_csrf_token` cookie，用時要 URL 解碼。"""
    for cookie in context.cookies():
        if cookie.get("name") == "_csrf_token":
            return urllib.parse.unquote(cookie.get("value") or "")
    return ""


def login_and_create_token(
    base_url: str,
    *,
    purpose: str = "ntucool",
    timeout: float = 300.0,
    headless: bool = False,
    executable_path: str | None = None,
    on_status=lambda _message: None,
    fill_login=None,
) -> str:
    """開瀏覽器讓使用者登入，然後建立一支存取權杖並回傳。

    `fill_login` 只給測試用：模擬使用者在登入頁輸入帳密。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise NtuCoolError(INSTALL_HINT) from exc

    base_url = base_url.rstrip("/")
    with sync_playwright() as driver:
        try:
            browser = driver.chromium.launch(headless=headless, executable_path=executable_path)
        except Exception as exc:  # noqa: BLE001 — 多半是還沒下載瀏覽器
            raise NtuCoolError(f"無法啟動瀏覽器：{exc}\n\n{INSTALL_HINT}") from exc

        context = browser.new_context()
        page = context.new_page()
        try:
            on_status("已開啟瀏覽器視窗，請在裡面用學校帳號登入 NTU COOL……")
            page.goto(f"{base_url}/login", wait_until="domcontentloaded")
            if fill_login is not None:
                fill_login(page)

            deadline = time.time() + timeout
            while True:
                if page.is_closed():
                    raise NtuCoolError("瀏覽器視窗被關閉了，登入沒有完成")
                try:
                    if page.request.get(f"{base_url}{PROBE_PATH}").status == 200:
                        break
                except Exception:  # noqa: BLE001 — 導頁過程中的暫時性錯誤
                    pass
                if time.time() > deadline:
                    raise NtuCoolError(f"等待登入超過 {timeout:.0f} 秒，請再試一次")
                time.sleep(1.0)

            on_status("登入成功，正在建立存取權杖……")
            page.goto(f"{base_url}{SETTINGS_PATH}", wait_until="domcontentloaded")
            csrf = _csrf_from(context)
            if not csrf:
                raise NtuCoolError("找不到 CSRF token，無法自動建立權杖")

            response = page.request.post(
                f"{base_url}{TOKEN_PATH}",
                headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
                form={"access_token[purpose]": purpose, "access_token[expires_at]": ""},
            )
            if response.status >= 400:
                raise NtuCoolError(
                    f"建立權杖失敗（HTTP {response.status}）。"
                    f"請改用手動方式：在 NTU COOL 的「帳戶 → 設定 → 新增存取權杖」自行產生。"
                )
            token = (response.json() or {}).get("visible_token") or ""
            if not token:
                raise NtuCoolError("Canvas 沒有回傳權杖內容，請改用手動方式產生")
            on_status("權杖已建立。")
            return token
        finally:
            context.close()
            browser.close()
