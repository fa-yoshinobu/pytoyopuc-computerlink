@echo off
setlocal

if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

set "HOST=%~1"
set "PORT=%~2"
set "PROTOCOL=%~3"
set "LOCAL_PORT=%~4"
set "COARSE_STEP=%~5"
set "STOP_AFTER_NG=%~6"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%COARSE_STEP%"=="" set "COARSE_STEP=16"
if "%STOP_AFTER_NG%"=="" set "STOP_AFTER_NG=32"

call tools\run_device_range_scan.bat %HOST% %PORT% %PROTOCOL% %LOCAL_PORT% %COARSE_STEP% %STOP_AFTER_NG% FR
exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_fr_range_scan.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [COARSE_STEP] [STOP_AFTER_NG]
echo.
echo Example ^(TCP^):
echo   tools\run_fr_range_scan.bat 192.168.250.101 1025 tcp 0 16 32
echo.
echo Example ^(UDP^):
echo   tools\run_fr_range_scan.bat 192.168.250.101 1027 udp 12000 16 32
exit /b 2
