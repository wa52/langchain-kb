@echo off
set HF_ENDPOINT=https://hf-mirror.com
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if "%1"=="" (
    python main.py
) else (
    python main.py %*
)
