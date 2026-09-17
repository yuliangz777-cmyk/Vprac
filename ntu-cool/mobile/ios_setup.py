#!/usr/bin/env python3
"""iPhone 一次性安裝腳本（在 a-Shell 裡執行）。

    curl -sL <raw 網址> -o ios_setup.py
    python3 ios_setup.py

它會：下載程式碼 → 問你的存取權杖 → 驗證權杖 → 告訴你捷徑要怎麼設。
重跑一次就是更新程式碼（權杖會保留）。

這個檔案刻意不依賴 ntucool 套件本身——執行它的時候套件還沒下載。
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

DEFAULT_REPO = "yuliangz777-cmyk/Vprac"
DEFAULT_REF = "main"
DEFAULT_DIR = Path.home() / "Documents" / "ntucool"
TOKEN_FILENAME = ".ntucool-token"

#: 只取這些檔案，其他（測試、README、workflow）手機上用不到
WANTED_TOP_LEVEL = {"ios_sync.py", "ios_web.py", "ios_setup.py"}


def archive_url(repo: str, ref: str) -> str:
    return f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{ref}"


def target_for(member_name: str) -> str | None:
    """把壓縮檔裡的路徑對應到手機上的安裝位置；不需要的檔案回傳 None。

    壓縮檔長這樣：`Vprac-<branch>/ntu-cool/ntucool/cli.py`
    安裝之後長這樣：`ntucool/cli.py`
    """
    parts = [p for p in member_name.split("/") if p and p != "."]
    if ".." in parts or "ntu-cool" not in parts:
        return None
    rest = parts[parts.index("ntu-cool") + 1 :]
    if len(rest) >= 2 and rest[0] == "ntucool" and rest[-1].endswith(".py"):
        return "/".join(rest)
    if len(rest) == 2 and rest[0] == "mobile" and rest[1] in WANTED_TOP_LEVEL:
        return rest[1]
    return None


def fetch(repo: str, ref: str, archive: Path | None) -> bytes:
    if archive:
        return archive.read_bytes()
    url = archive_url(repo, ref)
    print(f"下載程式碼：{url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def install(dest: Path, data: bytes) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    installed = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            relative = target_for(member.name)
            if relative is None:
                continue
            target = (dest / relative).resolve()
            if root not in target.parents:  # 擋掉壓縮檔裡的路徑穿越
                raise ValueError(f"壓縮檔內容不合法：{member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
            installed += 1
    if installed == 0:
        raise ValueError("壓縮檔裡找不到 ntucool 程式碼，請確認 --ref 是否正確")
    return installed


def ask_token() -> str:
    print()
    print("請貼上 NTU COOL 存取權杖。")
    print("取得方式：NTU COOL → 帳戶 → 設定 → 核准的整合 → + 新增存取權杖")
    try:
        import getpass

        token = getpass.getpass("權杖（輸入時不會顯示）：")
    except Exception:  # noqa: BLE001 — 某些終端機不支援隱藏輸入
        token = input("權杖：")
    return token.strip()


def verify(dest: Path) -> bool:
    """用剛裝好的套件實際打一次 API，確認權杖真的能用。"""
    sys.path.insert(0, str(dest))
    from ntucool.client import CanvasClient  # noqa: PLC0415
    from ntucool.config import DEFAULT_BASE_URL  # noqa: PLC0415
    from ntucool.errors import NtuCoolError  # noqa: PLC0415
    from ntucool.mobile import data_dir, read_token, token_path  # noqa: PLC0415

    base_url = os.environ.get("NTU_COOL_BASE_URL", DEFAULT_BASE_URL)
    try:
        profile = CanvasClient(f"{base_url}/api/v1", read_token(token_path())).whoami()
    except NtuCoolError as exc:
        print(f"\n權杖驗證失敗：{exc}")
        print("請確認複製完整、且權杖沒有被刪除或過期，然後重新執行這個腳本。")
        return False
    print(f"\n權杖有效，你好，{profile.get('name')}！")
    print(f"課程資料會放在：{data_dir()}")
    return True


def print_shortcut_instructions(dest: Path) -> None:
    command = f"python3 {dest / 'ios_sync.py'}"
    print("\n" + "=" * 46)
    print("設定「一鍵同步」捷徑：")
    print("  1. 打開「捷徑」App → 右上角 + → 新增動作")
    print("  2. 搜尋 a-Shell，選「Execute Command」")
    print("  3. 指令欄位貼上這一行：")
    print(f"\n     {command}\n")
    print("  4. 捷徑命名為「同步 NTU COOL」→ 完成")
    print("  5. 長按捷徑 →「加入主畫面」，就能像 App 一樣點開")
    print()
    print("想每天自動跑：捷徑 App →「自動化」→ 新增 →")
    print("「特定時間」→ 選時間 → 執行這個捷徑（記得關掉「執行前先詢問」）")
    print("=" * 46)
    print("\n也可以直接在 a-Shell 手動執行同一行指令。")
    print()
    print("想要圖形介面（看作業截止日、成績、直接開檔案）：")
    print(f"    python3 {dest / 'ios_web.py'}")
    print("再切到 Safari 打開它印出來的網址，按「分享 → 加入主畫面」。")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="在 iPhone（a-Shell）上安裝 ntucool")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="安裝位置")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--ref", default=DEFAULT_REF, help="分支或標籤，預設 main")
    parser.add_argument("--archive", type=Path, help="改用本機的 .tar.gz 安裝（離線或測試用）")
    parser.add_argument("--token", help="直接指定權杖，不互動詢問")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args(argv)

    dest: Path = args.dir.expanduser()
    try:
        count = install(dest, fetch(args.repo, args.ref, args.archive))
    except Exception as exc:  # noqa: BLE001 — 這裡的任何失敗都要講人話
        print(f"安裝失敗：{exc}")
        return 1
    print(f"已安裝 {count} 個檔案到 {dest}")

    sys.path.insert(0, str(dest))
    from ntucool.mobile import read_token, save_token, token_path  # noqa: PLC0415

    token = (args.token or "").strip()
    if not token and not read_token(token_path()):
        token = ask_token()
    if token:
        saved = save_token(token)
        print(f"權杖已存到 {saved}（只有你讀得到）")
    elif read_token(token_path()):
        print("沿用已存在的權杖")
    else:
        print("沒有輸入權杖，之後可以重新執行這個腳本再設定。")
        return 2

    if not args.skip_verify and not verify(dest):
        return 3
    print_shortcut_instructions(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
