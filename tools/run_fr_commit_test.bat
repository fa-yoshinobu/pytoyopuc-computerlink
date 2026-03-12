@echo off
setlocal

if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

set "HOST=%~1"
set "PORT=%~2"
set "PROTOCOL=%~3"
set "LOCAL_PORT=%~4"
set "TIMEOUT=%~5"
set "RETRIES=%~6"
set "MODE=%~7"
set "TARGET=%~8"
set "VALUE=%~9"
shift
shift
shift
shift
shift
shift
shift
shift
shift
set "COMMIT_TIMEOUT=%~1"
set "POLL_INTERVAL=%~2"
set "TRY_A0=%~3"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"
if "%MODE%"=="" set "MODE=read"
if "%TARGET%"=="" set "TARGET=FR000000"
if "%VALUE%"=="" set "VALUE=0x1234"
if "%COMMIT_TIMEOUT%"=="" set "COMMIT_TIMEOUT=30"
if "%POLL_INTERVAL%"=="" set "POLL_INTERVAL=0.2"
if "%TRY_A0%"=="" set "TRY_A0=0"

set "TRY_A0_ARG="
if /I "%TRY_A0%"=="1" set "TRY_A0_ARG=--try-a0"
if /I "%TRY_A0%"=="true" set "TRY_A0_ARG=--try-a0"
if /I "%TRY_A0%"=="yes" set "TRY_A0_ARG=--try-a0"

python -m tools.fr_commit_test ^
  --host %HOST% ^
  --port %PORT% ^
  --protocol %PROTOCOL% ^
  --local-port %LOCAL_PORT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --mode %MODE% ^
  --target %TARGET% ^
  --value %VALUE% ^
  --commit-timeout %COMMIT_TIMEOUT% ^
  --poll-interval %POLL_INTERVAL% ^
  %TRY_A0_ARG%

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_fr_commit_test.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [MODE] [TARGET] [VALUE] [COMMIT_TIMEOUT] [POLL_INTERVAL] [TRY_A0]
echo.
echo Read example ^(UDP^):
echo   tools\run_fr_commit_test.bat 192.168.250.101 1027 udp 12000 5 2 read FR000000
echo.
echo Write+commit example ^(UDP^):
echo   tools\run_fr_commit_test.bat 192.168.250.101 1027 udp 12000 5 2 write FR000000 0x1234 30 0.2
echo.
echo Restore example ^(UDP^):
echo   tools\run_fr_commit_test.bat 192.168.250.101 1027 udp 12000 5 2 write FR000000 0xFFFF 30 0.2
echo.
echo Optional A0 try:
echo   tools\run_fr_commit_test.bat 192.168.250.101 1027 udp 12000 5 2 read FR000000 0x1234 30 0.2 1
exit /b 2
