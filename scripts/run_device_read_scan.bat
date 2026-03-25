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
set "TARGETS="
set "CHUNK="
set "LOG="

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=3"
if "%RETRIES%"=="" set "RETRIES=0"
shift
shift
shift
shift
shift
shift

:collect_targets
if "%~1"=="" goto :defaults
call :is_number "%~1"
if errorlevel 1 goto :chunk_found
if defined TARGETS (
  set "TARGETS=%TARGETS%,%~1"
) else (
  set "TARGETS=%~1"
)
shift
goto :collect_targets

:chunk_found
set "CHUNK=%~1"
shift
set "LOG=%~1"
goto :defaults

:defaults
if "%TARGETS%"=="" set "TARGETS=S,N,R,D,U,EB"
if "%CHUNK%"=="" set "CHUNK=64"

set "LOG_ARG="
if not "%LOG%"=="" set "LOG_ARG=--log ""%LOG%"""

python -m tools.device_read_scan ^
  --host %HOST% ^
  --port %PORT% ^
  --protocol %PROTOCOL% ^
  --local-port %LOCAL_PORT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --targets %TARGETS% ^
  --chunk %CHUNK% ^
  %LOG_ARG%

exit /b %errorlevel%

:is_number
set "TOKEN=%~1"
for /f "delims=0123456789" %%i in ("%TOKEN%") do exit /b 0
if "%TOKEN%"=="" exit /b 0
exit /b 1

:usage
echo Usage:
echo   tools\run_device_read_scan.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [TARGETS] [CHUNK] [LOG]
echo.
echo Example:
echo   tools\run_device_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 S,N,R,D,U,EB 128 read_scan.log
exit /b 2
