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


def main(argv=None) -> int:
    """捷徑呼叫的進入點：`python3 ~/Documents/ntucool/ios_sync.py`"""
    from .cli import main as cli_main

    argv = list(sys.argv[1:] if argv is None else argv)
    token_file = token_path()
    if not read_token(token_file) and not os.environ.get("NTU_COOL_TOKEN"):
        print("還沒設定存取權杖。")
        print(f"請在 a-Shell 執行一次：python3 {install_root() / 'ios_setup.py'}")
        return 2
    os.environ.setdefault("NTU_COOL_TOKEN_FILE", str(token_file))

    out_dir = data_dir()
    print(f"同步到：{out_dir}")
    code = cli_main(["sync", "-o", str(out_dir), *argv])
    if code == 0:
        print("\n在「檔案」App →「我的 iPhone」→ a-Shell →")
        print(f"{out_dir.name} 就能看到所有課程資料夾。")
    elif code == 3:
        print("\n權杖可能已失效，請重新執行一次 ios_setup.py 設定新的權杖。")
    return code
