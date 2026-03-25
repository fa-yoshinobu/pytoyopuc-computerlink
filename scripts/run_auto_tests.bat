@echo off
setlocal

if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

set "HOST=%~1"
set "PORT=%~2"
set "PROTOCOL=%~3"
set "COUNT=%~4"
set "TIMEOUT=%~5"
set "RETRIES=%~6"
set "PC10_BLOCK_WORDS=%~7"
set "LOCAL_PORT=%~8"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%COUNT%"=="" set "COUNT=4"
if "%TIMEOUT%"=="" set "TIMEOUT=3"
if "%RETRIES%"=="" set "RETRIES=0"
if "%PC10_BLOCK_WORDS%"=="" set "PC10_BLOCK_WORDS=0x200"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""`) do set "START_AT=%%i"
set "LOGDIR=logs\auto_%STAMP%"
set "SUMMARY=%LOGDIR%\summary.txt"

if not exist logs mkdir logs
mkdir "%LOGDIR%"

echo.
echo Host             : %HOST%
echo Port             : %PORT%
echo Protocol         : %PROTOCOL%
echo Count            : %COUNT%
echo Timeout          : %TIMEOUT%
echo Retries          : %RETRIES%
echo PC10 Block Words : %PC10_BLOCK_WORDS%
echo Local UDP Port   : %LOCAL_PORT%
echo Log Dir          : %LOGDIR%
echo Start            : %START_AT%
echo.

(
echo Test Summary
echo ============
echo.
    echo Host             : %HOST%
    echo Port             : %PORT%
    echo Protocol         : %PROTOCOL%
    echo Count            : %COUNT%
    echo Timeout          : %TIMEOUT%
    echo Retries          : %RETRIES%
    echo PC10 Block Words : %PC10_BLOCK_WORDS%
    echo Local UDP Port   : %LOCAL_PORT%
    echo Log Dir          : %LOGDIR%
    echo Start            : %START_AT%
    echo.
) > "%SUMMARY%"

echo [1/4] Basic areas
echo [1/4] Basic areas>> "%SUMMARY%"
echo Command: python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --count %COUNT% --timeout %TIMEOUT% --retries %RETRIES% --log "%LOGDIR%\basic.log">> "%SUMMARY%"
python -m tools.auto_rw_test ^
  --host %HOST% ^
  --port %PORT% ^
  --local-port %LOCAL_PORT% ^
  --protocol %PROTOCOL% ^
  --count %COUNT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --log "%LOGDIR%\basic.log"
if errorlevel 1 goto :failed
echo Result: PASS>> "%SUMMARY%"
type "%LOGDIR%\basic.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
echo.>> "%SUMMARY%"

echo.
echo [2/4] Mixed CMD=98/99
echo [2/4] Mixed CMD=98/99>> "%SUMMARY%"
echo Command: python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout %TIMEOUT% --retries %RETRIES% --ext-multi-test --skip-errors --log "%LOGDIR%\ext_multi.log">> "%SUMMARY%"
python -m tools.auto_rw_test ^
  --host %HOST% ^
  --port %PORT% ^
  --local-port %LOCAL_PORT% ^
  --protocol %PROTOCOL% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --ext-multi-test ^
  --skip-errors ^
  --log "%LOGDIR%\ext_multi.log"
if errorlevel 1 goto :failed
echo Result: PASS>> "%SUMMARY%"
type "%LOGDIR%\ext_multi.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
echo.>> "%SUMMARY%"

echo [3/4] PC10G full + P1/P2/P3
echo [3/4] PC10G full + P1/P2/P3>> "%SUMMARY%"
echo Command: python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --count %COUNT% --timeout %TIMEOUT% --retries %RETRIES% --pc10g-full --include-p123 --skip-errors --log "%LOGDIR%\pc10g_full.log">> "%SUMMARY%"
python -m tools.auto_rw_test ^
  --host %HOST% ^
  --port %PORT% ^
  --local-port %LOCAL_PORT% ^
  --protocol %PROTOCOL% ^
  --count %COUNT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --pc10g-full ^
  --include-p123 ^
  --skip-errors ^
  --log "%LOGDIR%\pc10g_full.log"
if errorlevel 1 goto :failed
echo Result: PASS>> "%SUMMARY%"
type "%LOGDIR%\pc10g_full.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
echo.>> "%SUMMARY%"

echo.
echo [4/4] Block length test
echo [4/4] Block length test>> "%SUMMARY%"
echo Command: python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout %TIMEOUT% --retries %RETRIES% --max-block-test --pc10-block-words %PC10_BLOCK_WORDS% --skip-errors --log "%LOGDIR%\block.log">> "%SUMMARY%"
python -m tools.auto_rw_test ^
  --host %HOST% ^
  --port %PORT% ^
  --local-port %LOCAL_PORT% ^
  --protocol %PROTOCOL% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --max-block-test ^
  --pc10-block-words %PC10_BLOCK_WORDS% ^
  --skip-errors ^
  --log "%LOGDIR%\block.log"
if errorlevel 1 goto :failed
echo Result: PASS>> "%SUMMARY%"
type "%LOGDIR%\block.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
echo.>> "%SUMMARY%"

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""`) do set "END_AT=%%i"
echo End              : %END_AT%>> "%SUMMARY%"
echo Overall          : PASS>> "%SUMMARY%"

echo.
echo All tests completed successfully.
echo Logs: %LOGDIR%
echo Summary: %SUMMARY%
goto :eof

:failed
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""`) do set "END_AT=%%i"
echo Result: FAIL>> "%SUMMARY%"
echo End              : %END_AT%>> "%SUMMARY%"
echo Overall          : FAIL>> "%SUMMARY%"
echo.
echo Test sequence failed. Check logs under %LOGDIR%.
exit /b 1

:usage
echo Usage:
echo   tools\run_auto_tests.bat ^<HOST^> ^<PORT^> [PROTOCOL] [COUNT] [TIMEOUT] [RETRIES] [PC10_BLOCK_WORDS] [LOCAL_PORT]
echo.
echo Example:
echo   tools\run_auto_tests.bat 192.168.250.101 1025 udp 4 3 0 0x200 12000
exit /b 2
