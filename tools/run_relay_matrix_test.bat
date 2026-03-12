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
set "LOG="
if %ARGCOUNT% GEQ 1 (
  set "LAST=!ARG%ARGCOUNT%!"
  for %%F in ("!LAST!") do set "LAST_EXT=%%~xF"
  if /I "!LAST_EXT!"==".log" (
    set "LOG=!LAST!"
    set /a ARGCOUNT-=1
  ) else if /I "!LAST_EXT!"==".txt" (
    set "LOG=!LAST!"
    set /a ARGCOUNT-=1
  )
)

set "HOPS="
if %ARGCOUNT% GEQ 1 (
  for /L %%I in (1,1,%ARGCOUNT%) do (
    if defined HOPS (
      set "HOPS=!HOPS!,!ARG%%I!"
    ) else (
      set "HOPS=!ARG%%I!"
    )
  )
)
if not defined HOPS set "HOPS=P1-L2:N2"

if defined LOG (
  python -m tools.relay_matrix_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "%HOPS%" ^
    --targets P1-D0000,P1-R0000,P1-S0000,U08000 ^
    --counts 8,16,32 ^
    --loops 3 ^
    --value 0x1000 ^
    --step 1 ^
    --loop-step 0x0100 ^
    --log %LOG%
) else (
  python -m tools.relay_matrix_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "%HOPS%" ^
    --targets P1-D0000,P1-R0000,P1-S0000,U08000 ^
    --counts 8,16,32 ^
    --loops 3 ^
    --value 0x1000 ^
    --step 1 ^
    --loop-step 0x0100
)
exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_relay_matrix_test.bat HOST PORT [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [HOPS] [LOG]
echo.
echo Example:
echo   tools\run_relay_matrix_test.bat 192.168.250.101 1027 udp 12000 10 1 P1-L2:N4,P1-L2:N6,P1-L2:N2 relay_matrix.log
exit /b 1
