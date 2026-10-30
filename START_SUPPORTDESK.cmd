@echo off
echo Starting the English SupportDesk demo...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_stage1.ps1" -Detached
if errorlevel 1 (
    echo Startup failed. See the message above.
    pause
    exit /b 1
)
echo Open http://127.0.0.1:8767/ in your browser.
pause
