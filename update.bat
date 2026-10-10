@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在从 GitHub 获取最新代码...
git pull --ff-only || (
    echo.
    echo 更新失败：可能是网络问题，或者本机改过代码。请把上面的信息截图发给开发者。
    pause
    exit /b
)

call start.bat
