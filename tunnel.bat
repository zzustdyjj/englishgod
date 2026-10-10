@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .env (
    echo 还没有 .env，请先复制 .env.example 为 .env 并填写。
    pause
    exit /b
)
findstr /r "^ACCESS_PASSWORD=..*" .env >nul || (
    echo 必须先在 .env 里设置 ACCESS_PASSWORD，否则任何拿到网址的人都能用你的 API 密钥。
    notepad .env
    pause
    exit /b
)

echo 正在启动服务（新窗口，关闭它即停止服务）...
start "English GAP 服务" .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo 正在生成公网地址，稍等几秒，下面出现的 https://....trycloudflare.com 就是手机要打开的网址。
echo 关闭此窗口即停止公网访问；每次启动网址都会变化。
echo.
cloudflared tunnel --url http://127.0.0.1:8000
pause
