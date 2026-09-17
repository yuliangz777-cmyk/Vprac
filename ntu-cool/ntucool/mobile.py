"""手機（iPhone / a-Shell）用的入口。

捷徑（Shortcuts）只會丟一行指令過來，所以這裡負責把「該放哪、權杖在哪、
出錯了要講什麼人話」都先決定好，剩下的交給一般的 CLI。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: 存放權杖的檔名（放在安裝資料夾裡，權限設成只有自己讀得到）
TOKEN_FILENAME = ".ntucool-token"

#: 預設輸出資料夾名稱；放在 ~/Documents 底下，iPhone 的「檔案」App 才看得到
DATA_DIR_NAME = "NTUCool"


def install_root() -> Path:
    """套件被放在哪裡（`~/Documents/ntucool`），權杖也存在這裡。"""
    return Path(__file__).resolve().parent.parent


def documents_dir() -> Path:
    """iPhone 上 a-Shell 的 `~/Documents` 會直接出現在「檔案」App 裡。"""
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def data_dir() -> Path:
    """課程資料放的地方。可用 NTU_COOL_OUT 覆寫。"""
    override = os.environ.get("NTU_COOL_OUT")
    if override:
        return Path(override).expanduser()
    return documents_dir() / DATA_DIR_NAME


def token_path() -> Path:
    """權杖檔位置；NTU_COOL_TOKEN_FILE 可以指到別的地方。"""
    override = os.environ.get("NTU_COOL_TOKEN_FILE")
    return Path(override).expanduser() if override else install_root() / TOKEN_FILENAME


def save_token(token: str, path: Path | None = None) -> Path:
    """把權杖寫進檔案，並收緊權限（不是加密，但至少不會被順手看到）。"""
    path = path or token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token.strip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # 某些檔案系統不支援權限設定，不值得為此失敗
    return path


def read_token(path: Path | None = None) -> str:
    path = path or token_path()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def use_saved_token() -> bool:
    """把手機上存的權杖接上設定；回傳「到底有沒有權杖可用」。

    權杖可能來自兩個地方：ios_setup.py 存的權杖檔，或在網頁介面上登入時寫的 .env。
    """
    from .config import load_config
    from .errors import ConfigError

    token_file = token_path()
    if read_token(token_file):
        os.environ.setdefault("NTU_COOL_TOKEN_FILE", str(token_file))
    try:
        return bool(load_config().token)
    except ConfigError:
        return False  # 例如權杖檔被刪掉了：當作還沒登入，而不是整個爆掉


def _no_token_message() -> None:
    print("還沒設定存取權杖，兩種方式擇一：")
    print(f"  · 網頁登入：python3 {install_root() / 'ios_web.py'}")
    print(f"  · 終端機設定：python3 {install_root() / 'ios_setup.py'}")


def web_main(argv=None) -> int:
    """在手機上開網頁介面：`python3 ~/Documents/ntucool/ios_web.py`

    用 127.0.0.1 是刻意的——Safari 把它當成安全來源，所以 Service Worker
    會啟用，可以「加入主畫面」並離線瀏覽。
    """
    from .config import load_config
    from .web import create_server

    argv = list(sys.argv[1:] if argv is None else argv)
    port = int(argv[0]) if argv and argv[0].isdigit() else 8765
    use_saved_token()
    config = load_config(overrides={"out_dir": data_dir()})
    httpd, url = create_server(config, host="127.0.0.1", port=port)
    print("網頁介面已啟動。請保持 a-Shell 在前景，切到 Safari 打開：")
    print(f"\n  {url}\n")
    if not config.token:
        print("第一次會先請你在網頁上登入。")
    print("在 Safari 按「分享 → 加入主畫面」就能像 App 一樣開啟（可離線看上次的資料）。")
    print("按 Ctrl+C 結束。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已關閉")
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


def main(argv=None) -> int:
    """捷徑呼叫的進入點：`python3 ~/Documents/ntucool/ios_sync.py`"""
    from .cli import main as cli_main

    argv = list(sys.argv[1:] if argv is None else argv)
    if not use_saved_token():
        _no_token_message()
        return 2

    out_dir = data_dir()
    print(f"同步到：{out_dir}")
    code = cli_main(["sync", "-o", str(out_dir), *argv])
    if code == 0:
        print("\n在「檔案」App →「我的 iPhone」→ a-Shell →")
        print(f"{out_dir.name} 就能看到所有課程資料夾。")
    elif code == 3:
        print("\n權杖可能已失效，請重新執行一次 ios_setup.py 設定新的權杖。")
    return code
