@echo off
setlocal
set "HF_HUB_OFFLINE=1"
set "PYTHONIOENCODING=utf-8"
rem Prevent all experience sync while production index repair is pending.
rem An empty EXPERIENCE_DIRS value is reloaded from .env on Windows.
set "KNOWLEDGE_DISABLE_EXPERIENCE_SYNC=1"
cd /d "%~dp0"
"%~dp0kb_env\Scripts\python.exe" -m src.cli.knowledge web %*
if errorlevel 1 pause
