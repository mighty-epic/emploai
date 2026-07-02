@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\desktop\start.ps1" %*
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo EmploAI failed to start. Review the messages above.
  pause
)
exit /b %EXIT_CODE%
