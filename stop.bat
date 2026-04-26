@echo off
chcp 65001 >nul 2>&1
title What Am I Doing - 停止

echo 正在停止所有 WAID 进程...

::: 查找并关闭 server 和 client
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr /i "client.py\|main.py" 2^>nul') do (
    taskkill /pid %%i /f >nul 2>&1
)

::: 更可靠的方式：按窗口标题关闭
taskkill /fi "WINDOWTITLE eq WAID-Server*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq WAID-Admin*" /f >nul 2>&1

echo ✓ 已停止
timeout /t 2 /nobreak >nul
