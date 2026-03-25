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
set "CASES="
set "LOG="

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"

shift
shift
shift
shift
shift
shift

:parse_args
if "%~1"=="" goto :args_done
if /I "%~x1"==".log" goto :treat_as_log
if defined CASES (
  set "CASES=%CASES%,%~1"
) else (
  set "CASES=%~1"
)
shift
goto :parse_args

:treat_as_log
set "LOG=%~1"
shift
goto :parse_args

:args_done
if "%CASES%"=="" set "CASES=l1000,m1000,u00000,u08000,eb00000"

set "LOG_ARG="
if not "%LOG%"=="" set "LOG_ARG=--log ""%LOG%"""

python -m tools.c4c5_range_probe ^
  --host %HOST% ^
  --port %PORT% ^
  --protocol %PROTOCOL% ^
  --local-port %LOCAL_PORT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --cases "%CASES%" ^
  %LOG_ARG%

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_c4c5_range_probe.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [CASES] [LOG]
echo.
echo Default probe:
echo   tools\run_c4c5_range_probe.bat 192.168.250.101 1027 udp 12000 5 2
echo.
echo Wider probe:
echo   tools\run_c4c5_range_probe.bat 192.168.250.101 1027 udp 12000 5 2 l1000,l2fff,m1000,m17ff,u00000,u07fff,u08000,u1ffff,eb00000,eb3ffff c4c5_range_probe.log
echo.
echo PowerShell note:
echo   comma lists may be passed either quoted or unquoted; unquoted lists are re-joined by this batch file
exit /b 2
