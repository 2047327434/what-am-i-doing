@echo off
chcp 65001 >nul 2>&1

set PYTHONW=C:\Users\yuhang.liang\.workbuddy\binaries\python\envs\waid\Scripts\pythonw.exe
set PYTHON=C:\Users\yuhang.liang\.workbuddy\binaries\python\envs\waid\Scripts\python.exe
set SERVER=c:\Users\yuhang.liang\WorkBuddy\20260426131404\what-am-i-doing\server\main.py
set CLIENT=c:\Users\yuhang.liang\WorkBuddy\20260426131404\what-am-i-doing\admin\client.py

echo [1/2] 启动 Server (端口 8900)...
start "WAID-Server" /min %PYTHON% %SERVER%

echo [2/2] 启动 Admin 客户端 (无窗口, 托盘运行)...
timeout /t 2 /nobreak >nul
start "" %PYTHONW% %CLIENT%

echo.
echo ✓ 全部启动完成！
echo   Server 在后台运行 (最小化窗口)
echo   Admin 托盘图标已启动 (无控制台窗口)
echo.
echo   用户前端:   http://localhost:8900
echo   管理面板:   http://localhost:8900/admin
echo   点击托盘图标 → 打开管理面板
echo.
timeout /t 3 /nobreak >nul
start http://localhost:8900/admin
