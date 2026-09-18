@echo off
REM 啟動 NTU Course Hub 的本機介面（Windows：雙擊這個檔案）
cd /d "%~dp0"
python -m ntucool web --open
pause
