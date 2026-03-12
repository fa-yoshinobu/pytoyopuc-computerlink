@echo off
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv\Scripts\python.exe not found
  exit /b 1
)

set "PYTHON=.venv\Scripts\python.exe"
set "APP_NAME=toyopuc-device-monitor"

%PYTHON% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "%APP_NAME%" ^
  examples\device_monitor_gui.py

if errorlevel 1 exit /b 1

echo.
echo Built:
echo   dist\%APP_NAME%\%APP_NAME%.exe

