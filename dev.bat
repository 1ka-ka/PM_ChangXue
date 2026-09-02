@echo off
chcp 65001 >nul
title 畅学社区 - 一键开发环境
color 0A

echo ============================================
echo   畅学社区 一键开发启动（支持热更新）
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

echo [1/3] 启动后端（热更新，dev 环境自动建表+seed 标签）...
start "畅学-后端8000" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo [2/3] 等待后端就绪...
timeout /t 3 /nobreak >nul

echo [3/3] 启动前端（Vite 热更新）...
start "畅学-前端5173" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 2 /nobreak >nul
start http://localhost:5173

echo.
echo 已启动！浏览器将自动打开 http://localhost:5173
echo 停止服务：关闭弹出的两个黑色窗口即可
echo 本窗口可安全关闭（不影响服务）
echo.
pause
