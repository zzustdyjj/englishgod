@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv || goto :error
)

echo [2/3] 检查依赖...
.venv\Scripts\python -m pip install -q -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || goto :error

if not exist .env (
    copy .env.example .env >nul
    echo.
    echo 已创建 .env，请用记事本填写模型和密钥后重新运行本脚本。
    notepad .env
    pause
    exit /b
)

echo [3/3] 启动服务：电脑打开 http://127.0.0.1:8000 ，手机打开 http://本机IP:8000
echo 关闭此窗口即停止服务。
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
exit /b

:error
echo.
echo 出错了，请把上面的错误信息截图发给开发者。
pause
