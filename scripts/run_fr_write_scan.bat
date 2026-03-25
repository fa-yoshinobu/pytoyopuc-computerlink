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
set "SEED=%~2"
set "LOG=%~3"
set "SKIP_COMMIT=%~4"
set "SKIP_VERIFY=%~5"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"
if "%CHUNK_WORDS%"=="" set "CHUNK_WORDS=0x200"
if "%PROGRESS_EVERY%"=="" set "PROGRESS_EVERY=64"
if "%START%"=="" set "START=0x000000"
if "%END%"=="" set "END=0x0000FF"
if "%SEED%"=="" set "SEED=0xA500"
if "%SKIP_COMMIT%"=="" set "SKIP_COMMIT=0"
if "%SKIP_VERIFY%"=="" set "SKIP_VERIFY=0"

set "SKIP_COMMIT_ARG="
if /I "%SKIP_COMMIT%"=="1" set "SKIP_COMMIT_ARG=--skip-commit"
if /I "%SKIP_COMMIT%"=="true" set "SKIP_COMMIT_ARG=--skip-commit"
if /I "%SKIP_COMMIT%"=="yes" set "SKIP_COMMIT_ARG=--skip-commit"

set "SKIP_VERIFY_ARG="
if /I "%SKIP_VERIFY%"=="1" set "SKIP_VERIFY_ARG=--skip-verify"
if /I "%SKIP_VERIFY%"=="true" set "SKIP_VERIFY_ARG=--skip-verify"
if /I "%SKIP_VERIFY%"=="yes" set "SKIP_VERIFY_ARG=--skip-verify"

if "%LOG%"=="" (
  python -m tools.fr_write_scan ^
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
    --seed %SEED% ^
    %SKIP_COMMIT_ARG% ^
    %SKIP_VERIFY_ARG%
) else (
  python -m tools.fr_write_scan ^
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
    --seed %SEED% ^
    --log "%LOG%" ^
    %SKIP_COMMIT_ARG% ^
    %SKIP_VERIFY_ARG%
)

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_fr_write_scan.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [CHUNK_WORDS] [PROGRESS_EVERY] [START] [END] [SEED] [LOG] [SKIP_COMMIT] [SKIP_VERIFY]
echo.
echo Small-range example ^(UDP^):
echo   tools\run_fr_write_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 8 0x000000 0x0000FF 0xA500 fr_write_small.log
echo.
echo One-block example ^(UDP^):
echo   tools\run_fr_write_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 16 0x000000 0x007FFF 0xA500 fr_write_block0.log
echo.
echo Full-range example ^(destructive^):
echo   tools\run_fr_write_scan.bat 192.168.250.101 1027 udp 12000 5 2 0x200 64 0x000000 0x1FFFFF 0xA500 fr_write_full.log
exit /b 2
