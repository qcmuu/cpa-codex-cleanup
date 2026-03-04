@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  echo Please install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)

echo [INFO] Starting CPA Cleanup Web UI...
echo [INFO] URL: http://127.0.0.1:8123
start "" "http://127.0.0.1:8123"

python cpa_cleanup_web.py --host 127.0.0.1 --port 8123
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] Web UI exited with code %EXIT_CODE%.
  pause
)

endlocal
