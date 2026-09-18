#!/usr/bin/env sh
# 啟動 NTU Course Hub 的本機介面（macOS / Linux：雙擊或 sh start.sh）
cd "$(dirname "$0")" || exit 1
exec python3 -m ntucool web --open
