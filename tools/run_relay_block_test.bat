@echo off
setlocal EnableDelayedExpansion

if "%~1"=="" goto usage
if "%~2"=="" goto usage

set "HOST=%~1"
set "PORT=%~2"
set "PROTOCOL=%~3"
set "LOCAL_PORT=%~4"
set "TIMEOUT=%~5"
set "RETRIES=%~6"

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

set /a ARGCOUNT=0
:collect_args
if "%~1"=="" goto after_collect
set /a ARGCOUNT+=1
set "ARG!ARGCOUNT!=%~1"
shift
goto collect_args

:after_collect
if %ARGCOUNT% LSS 6 goto usage

set "LOG="
set "LAST=!ARG%ARGCOUNT%!"
for %%F in ("!LAST!") do set "LAST_EXT=%%~xF"
if /I "!LAST_EXT!"==".log" (
  set "LOG=!LAST!"
  set /a ARGCOUNT-=1
) else if /I "!LAST_EXT!"==".txt" (
  set "LOG=!LAST!"
  set /a ARGCOUNT-=1
)

if %ARGCOUNT% LSS 6 goto usage

set /a DEVICE_INDEX=ARGCOUNT-5
set /a COUNT_INDEX=ARGCOUNT-4
set /a LOOPS_INDEX=ARGCOUNT-3
set /a VALUE_INDEX=ARGCOUNT-2
set /a STEP_INDEX=ARGCOUNT-1
set /a LOOP_STEP_INDEX=ARGCOUNT
set /a HOPS_END=DEVICE_INDEX-1

set "DEVICE=!ARG%DEVICE_INDEX%!"
set "COUNT=!ARG%COUNT_INDEX%!"
set "LOOPS=!ARG%LOOPS_INDEX%!"
set "VALUE=!ARG%VALUE_INDEX%!"
set "STEP=!ARG%STEP_INDEX%!"
set "LOOP_STEP=!ARG%LOOP_STEP_INDEX%!"

set "HOPS="
for /L %%I in (1,1,%HOPS_END%) do (
  if defined HOPS (
    set "HOPS=!HOPS!,!ARG%%I!"
  ) else (
    set "HOPS=!ARG%%I!"
  )
)

if not defined HOPS goto usage

if defined LOG (
  python -m tools.relay_block_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "!HOPS!" ^
    --device %DEVICE% ^
    --count %COUNT% ^
    --loops %LOOPS% ^
    --value %VALUE% ^
    --step %STEP% ^
    --loop-step %LOOP_STEP% ^
    --log %LOG%
) else (
  python -m tools.relay_block_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "!HOPS!" ^
    --device %DEVICE% ^
    --count %COUNT% ^
    --loops %LOOPS% ^
    --value %VALUE% ^
    --step %STEP% ^
    --loop-step %LOOP_STEP%
)
exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_relay_block_test.bat HOST PORT [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] HOPS DEVICE COUNT LOOPS VALUE STEP LOOP_STEP [LOG]
echo.
echo Example:
echo   tools\run_relay_block_test.bat 192.168.250.101 1027 udp 12000 10 1 P1-L2:N2,P1-L2:N4,P1-L2:N6 P1-D0000 8 3 0x1000 1 0x0100 relay_block.log
exit /b 1
