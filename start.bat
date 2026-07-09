@echo off
cd /d %~dp0
call .venv\Scripts\python.exe web_app.py
pause