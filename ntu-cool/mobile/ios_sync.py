#!/usr/bin/env python3
"""iPhone 捷徑呼叫的入口。

在 a-Shell 裡執行：
    python3 ~/Documents/ntucool/ios_sync.py
後面可以加上一般的 sync 參數，例如：
    python3 ~/Documents/ntucool/ios_sync.py --ext pdf,pptx
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ntucool.mobile import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
