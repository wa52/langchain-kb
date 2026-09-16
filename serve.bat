@echo off
set HF_HUB_OFFLINE=1
set HF_ENDPOINT=https://huggingface.co
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting Knowledge Base API server on http://127.0.0.1:8000 ...
echo Readiness check: http://127.0.0.1:8000/api/v1/health
kb_env\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000
