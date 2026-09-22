#!/usr/bin/env python3
"""在 iPhone 上開啟網頁介面。

在 a-Shell 執行：
    python3 ~/Documents/ntucool/ios_web.py
然後切到 Safari 打開它印出來的網址（127.0.0.1），
在 Safari 按「分享 → 加入主畫面」就能當成 App 使用。

要換連接埠的話：python3 ios_web.py 8790
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ntucool.mobile import web_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(web_main())
