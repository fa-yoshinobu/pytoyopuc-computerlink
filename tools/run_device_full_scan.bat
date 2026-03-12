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
set "CHUNK=%~7"
set "LOG_BASE=%~8"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=3"
if "%RETRIES%"=="" set "RETRIES=0"
if "%CHUNK%"=="" set "CHUNK=512"

set "SCAN_TARGETS=S,N,R,D,P,K,V,T,C,L,X,Y,M,EP,EX,GX,GY,GM,U,EB,FR"
set "PROBE_CASES=ext00,gx07,p1,p2,p3"
set "PROBE_CANDIDATE_NOS=0x00,0x01,0x02,0x03,0x07"

set "SCAN_LOG="
set "PROBE_LOG="
if not "%LOG_BASE%"=="" (
  set "SCAN_LOG=%LOG_BASE%_read.log"
  set "PROBE_LOG=%LOG_BASE%_program.log"
)

echo === Word/bulk device scan ===
if defined SCAN_LOG (
  call tools\run_device_read_scan.bat %HOST% %PORT% %PROTOCOL% %LOCAL_PORT% %TIMEOUT% %RETRIES% %SCAN_TARGETS% %CHUNK% %SCAN_LOG%
) else (
  call tools\run_device_read_scan.bat %HOST% %PORT% %PROTOCOL% %LOCAL_PORT% %TIMEOUT% %RETRIES% %SCAN_TARGETS% %CHUNK%
)
if errorlevel 1 goto :fail

echo(
echo === Prefixed/device-no probe ===
if defined PROBE_LOG (
  call tools\run_program_no_probe.bat %HOST% %PORT% %PROTOCOL% %LOCAL_PORT% %TIMEOUT% %RETRIES% %PROBE_CASES% %PROBE_CANDIDATE_NOS% %PROBE_LOG%
) else (
  call tools\run_program_no_probe.bat %HOST% %PORT% %PROTOCOL% %LOCAL_PORT% %TIMEOUT% %RETRIES% %PROBE_CASES% %PROBE_CANDIDATE_NOS%
)
if errorlevel 1 goto :fail

echo(
echo Full scan completed.
exit /b 0

:fail
echo(
echo Full scan aborted due to error.
exit /b 1

:usage
echo Usage:
echo   tools\run_device_full_scan.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [CHUNK] [LOG_BASE]
echo.
echo Example:
echo   tools\run_device_full_scan.bat 192.168.250.101 1027 udp 12000 5 2 512 device_full
exit /b 2
