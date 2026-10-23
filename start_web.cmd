@echo off
setlocal
set "HF_HUB_OFFLINE=1"
set "PYTHONIOENCODING=utf-8"
rem Keep the scheduled source sync off while the production index repair is pending.
set "EXPERIENCE_DIRS="
cd /d "%~dp0"
"%~dp0kb_env\Scripts\python.exe" -m src.cli.knowledge web
if errorlevel 1 pause
