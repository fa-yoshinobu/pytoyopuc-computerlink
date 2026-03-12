@echo off
setlocal

if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

set "HOST=%~1"
set "PORT=%~2"
set "PROTOCOL=%~3"
set "TIMEOUT=%~4"
set "RETRIES=%~5"
set "PC10_BLOCK_WORDS=%~6"
set "LOCAL_PORT=%~7"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%TIMEOUT%"=="" set "TIMEOUT=3"
if "%RETRIES%"=="" set "RETRIES=0"
if "%PC10_BLOCK_WORDS%"=="" set "PC10_BLOCK_WORDS=0x200"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"

python -m tools.auto_rw_test ^
  --host %HOST% ^
  --port %PORT% ^
  --local-port %LOCAL_PORT% ^
  --protocol %PROTOCOL% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --max-block-test ^
  --pc10-block-words %PC10_BLOCK_WORDS% ^
  --skip-errors

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_block_test.bat ^<HOST^> ^<PORT^> [PROTOCOL] [TIMEOUT] [RETRIES] [PC10_BLOCK_WORDS] [LOCAL_PORT]
exit /b 2
