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
set "CHUNK_WORDS=%~7"
set "PROGRESS_EVERY=%~8"
set "START=%~9"
shift
shift
shift
shift
shift
shift
shift
shift
shift
set "END=%~1"
set "STOP_AFTER_NG=%~2"
set "LOG=%~3"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"
if "%CHUNK_WORDS%"=="" set "CHUNK_WORDS=0x200"
if "%PROGRESS_EVERY%"=="" set "PROGRESS_EVERY=64"
if "%START%"=="" set "START=0x000000"
if "%END%"=="" set "END=0x1FFFFF"
if "%STOP_AFTER_NG%"=="" set "STOP_AFTER_NG=0"
if "%LOG%"=="" (
  python -m tools.fr_read_scan ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --chunk-words %CHUNK_WORDS% ^
    --progress-every %PROGRESS_EVERY% ^
    --start %START% ^
    --end %END% ^
    --stop-after-ng %STOP_AFTER_NG%
) else (
  python -m tools.fr_read_scan ^
    --host %HOST% ^
    --port %PORT% ^
    --protocol %PROTOCOL% ^
    --local-port %LOCAL_PORT% ^
    --timeout %TIMEOUT% ^
    --retries %RETRIES% ^
    --chunk-words %CHUNK_WORDS% ^
    --progress-every %PROGRESS_EVERY% ^
    --start %START% ^
    --end %END% ^
    --stop-after-ng %STOP_AFTER_NG% ^
    --log "%LOG%"
)

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_fr_read_scan.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [CHUNK_WORDS] [PROGRESS_EVERY] [START] [END] [STOP_AFTER_NG] [LOG]
echo.
echo Full-range example ^(UDP^):
echo   tools\run_fr_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0 fr_read_full.log
echo.
echo Small-range example ^(UDP^):
echo   tools\run_fr_read_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 8 0x000000 0x00FFFF 0
exit /b 2
