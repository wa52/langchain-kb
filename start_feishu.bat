@echo off
setlocal
set HF_HUB_OFFLINE=1
set HF_ENDPOINT=https://huggingface.co
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================
echo   Personal Knowledge Base - Feishu Bot
echo ============================================

REM ---- 1) 确保知识库 API 服务在运行 ----
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/v1/health 2>nul > "%TEMP%\kb_health.txt"
set /p API_CODE=<"%TEMP%\kb_health.txt"
if "%API_CODE%"=="200" (
    echo [OK]   知识库 API 已在运行 (127.0.0.1:8000)
) else (
    echo [....] 启动知识库 API 服务（约 40 秒）...
    start "Knowledge-Base-API" cmd /c "serve.bat"
    :wait_api
    timeout /t 5 /nobreak > nul
    curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/v1/health 2>nul > "%TEMP%\kb_health2.txt"
    set /p API_CODE2=<"%TEMP%\kb_health2.txt"
    if not "%API_CODE2%"=="200" goto wait_api
    echo [OK]   知识库 API 已就绪
)

REM ---- 2) 启动飞书机器人（长连接） ----
echo [....] 启动飞书机器人（长连接模式）...
echo        在飞书中给机器人发消息即可对话，发 /new 重置会话。
echo        按 Ctrl+C 停止。
echo.
kb_env\Scripts\python.exe -m src.feishu.bot
pause
