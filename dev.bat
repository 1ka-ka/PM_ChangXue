@echo off
REM 本文件必须保持 ANSI(GBK) 编码（cmd 默认按代码页解析），切勿转为 UTF-8。
title 畅学社区 - 一键启动开发环境
color 0A

echo ============================================
echo   畅学社区 一键启动（前后端热更新）
echo   后端: http://127.0.0.1:8000  (uvicorn --reload)
echo   前端: http://localhost:5173  (vite 热更新)
echo ============================================
echo.

REM ---- 环境自检 ----
if not exist "backend\.venv\Scripts\python.exe" (
    color 0C
    echo [错误] 未找到后端虚拟环境 backend\.venv
    echo 请先执行: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install fastapi uvicorn sqlalchemy alembic pydantic-settings python-jose passlib bcrypt pillow python-multipart apscheduler httpx pytest
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    color 0C
    echo [错误] 未找到前端依赖 frontend\node_modules
    echo 请先执行: cd frontend ^&^& npm ci --legacy-peer-deps
    pause
    exit /b 1
)

echo [1/4] 清理旧进程（8000/5173 端口，防止旧版本残留占用）...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

echo [2/4] 启动后端（热更新，dev 环境自动建表+seed 标签/商品）...
start "畅学-后端8000" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo [3/4] 等待后端就绪...
timeout /t 3 /nobreak >nul

echo [4/4] 启动前端（Vite 热更新）...
start "畅学-前端5173" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 2 /nobreak >nul
start http://localhost:5173

echo.
echo 启动完成！浏览器已自动打开 http://localhost:5173
echo 停止服务：关闭对应的两个命令行窗口即可。
echo 本窗口现在可安全关闭（不影响服务）。
echo.
pause
