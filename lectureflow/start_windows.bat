@echo off
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python app.py
pause
