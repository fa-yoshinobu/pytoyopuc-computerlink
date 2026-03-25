@echo off
setlocal

if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

set "HOST=%~1"
set "PORT=%~2"
set "PROTOCOL=%~3"
set "COUNT=%~4"
set "TIMEOUT=%~5"
set "RETRIES=%~6"
set "LOCAL_PORT=%~7"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%COUNT%"=="" set "COUNT=4"
if "%TIMEOUT%"=="" set "TIMEOUT=3"
if "%RETRIES%"=="" set "RETRIES=0"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"

python -m tools.auto_rw_test ^
  --host %HOST% ^
  --port %PORT% ^
  --local-port %LOCAL_PORT% ^
  --protocol %PROTOCOL% ^
  --count %COUNT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES%

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_quick_test.bat ^<HOST^> ^<PORT^> [PROTOCOL] [COUNT] [TIMEOUT] [RETRIES] [LOCAL_PORT]
exit /b 2
