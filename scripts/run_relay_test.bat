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
shift
shift
shift
shift
shift
shift

set "HOPS="
set "INNER="
set "DEVICE="
set "COUNT="
set "EXTRA="

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"

:collect_hops
if "%~1"=="" goto after_hops
if /I "%~1"=="cpu-status" goto inner_found
if /I "%~1"=="cpu-status-a0" goto inner_found
if /I "%~1"=="clock-read" goto inner_found
if /I "%~1"=="clock-write" goto inner_found
if /I "%~1"=="word-read" goto inner_found
if /I "%~1"=="word-write" goto inner_found
if /I "%~1"=="raw" goto inner_found
if defined HOPS (
  set "HOPS=%HOPS%,%~1"
) else (
  set "HOPS=%~1"
)
shift
goto collect_hops

:inner_found
set "INNER=%~1"
shift
set "DEVICE=%~1"
shift
set "COUNT=%~1"
shift
set "EXTRA=%~1"

:after_hops
if "%HOPS%"=="" set "HOPS=P1-L1:N1"
if "%INNER%"=="" set "INNER=cpu-status"
if "%DEVICE%"=="" set "DEVICE=D0000"
if "%COUNT%"=="" set "COUNT=1"

if /I "%INNER%"=="raw" (
  python -m tools.relay_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "%HOPS%" ^
    --inner %INNER% ^
    --raw-inner "%EXTRA%"
) else if /I "%INNER%"=="word-write" (
  python -m tools.relay_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "%HOPS%" ^
    --inner %INNER% ^
    --device %DEVICE% ^
    --count %COUNT% ^
    --value %EXTRA%
) else if /I "%INNER%"=="clock-write" (
  python -m tools.relay_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "%HOPS%" ^
    --inner %INNER% ^
    --clock-value "%DEVICE%"
) else (
  python -m tools.relay_test ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --hops "%HOPS%" ^
    --inner %INNER% ^
    --device %DEVICE% ^
    --count %COUNT%
)

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_relay_test.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [HOPS] [INNER] [DEVICE] [COUNT] [EXTRA]
echo.
echo CPU status example ^(UDP^):
echo   tools\run_relay_test.bat 192.168.250.101 1027 udp 12000 5 2 P1-L2:N2 cpu-status
echo.
echo CPU status A0 example ^(UDP^):
echo   tools\run_relay_test.bat 192.168.250.101 1027 udp 12000 5 2 P1-L2:N2 cpu-status-a0
echo.
echo Clock write example ^(UDP^):
echo   tools\run_relay_test.bat 192.168.250.101 1027 udp 12000 5 2 P1-L2:N2 clock-write 2026-03-10T15:00:00
echo.
echo Word read example ^(UDP^):
echo   tools\run_relay_test.bat 192.168.250.101 1027 udp 12000 5 2 P1-L2:N2 word-read D0000 1
echo.
echo Word write example ^(UDP^):
echo   tools\run_relay_test.bat 192.168.250.101 1027 udp 12000 5 2 P1-L2:N2 word-write D0000 1 0x1234
echo.
echo Raw inner example ^(UDP^):
echo   tools\run_relay_test.bat 192.168.250.101 1027 udp 12000 5 2 P1-L2:N2 raw D0000 1 "00 00 03 00 32 11 00"
exit /b 2
