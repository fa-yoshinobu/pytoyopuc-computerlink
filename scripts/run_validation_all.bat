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
set "RECOVERY_COUNT=%~9"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%COUNT%"=="" set "COUNT=4"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=2"
if "%PC10_BLOCK_WORDS%"=="" set "PC10_BLOCK_WORDS=0x200"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%RECOVERY_COUNT%"=="" set "RECOVERY_COUNT=60"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""`) do set "START_AT=%%i"
set "LOGDIR=logs\validation_%STAMP%"
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
echo Recovery Count   : %RECOVERY_COUNT%
echo Log Dir          : %LOGDIR%
echo Start            : %START_AT%
echo.

(
echo Validation Summary
echo ==================
echo.
echo Host             : %HOST%
echo Port             : %PORT%
echo Protocol         : %PROTOCOL%
echo Count            : %COUNT%
echo Timeout          : %TIMEOUT%
echo Retries          : %RETRIES%
echo PC10 Block Words : %PC10_BLOCK_WORDS%
echo Local UDP Port   : %LOCAL_PORT%
echo Recovery Count   : %RECOVERY_COUNT%
echo Log Dir          : %LOGDIR%
echo Start            : %START_AT%
echo.
) > "%SUMMARY%"

call :run_step 1 "Full test" "python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --count %COUNT% --timeout %TIMEOUT% --retries %RETRIES% --pc10g-full --include-p123 --skip-errors --log ""%LOGDIR%\full.log"""
if errorlevel 1 goto :failed

call :run_step 2 "Mixed CMD=98/99" "python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout %TIMEOUT% --retries %RETRIES% --ext-multi-test --skip-errors --log ""%LOGDIR%\ext_multi.log"""
if errorlevel 1 goto :failed

call :run_step 3 "Block test" "python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout %TIMEOUT% --retries %RETRIES% --max-block-test --pc10-block-words %PC10_BLOCK_WORDS% --skip-errors --log ""%LOGDIR%\block.log"""
if errorlevel 1 goto :failed

call :run_step 4 "Boundary test" "python -m tools.auto_rw_test --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout %TIMEOUT% --retries %RETRIES% --boundary-test --skip-errors --log ""%LOGDIR%\boundary.log"""
if errorlevel 1 goto :failed

call :run_step 5 "Recovery write" "python -m tools.recovery_write_loop --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout 1 --retries 0 --target D0000 --interval-ms 200 --count %RECOVERY_COUNT% --log ""%LOGDIR%\recovery_write.log"""
if errorlevel 1 goto :failed

call :run_step 6 "Recovery read" "python -m tools.recovery_write_loop --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout 1 --retries 0 --target D0000 --mode read --expect 0xFFFF --interval-ms 200 --count %RECOVERY_COUNT% --log ""%LOGDIR%\recovery_read.log"""
if errorlevel 1 goto :failed

call :run_step 7 "Last writable probe" "python -m tools.find_last_writable --host %HOST% --port %PORT% --local-port %LOCAL_PORT% --protocol %PROTOCOL% --timeout %TIMEOUT% --retries %RETRIES% --auto-pending --log ""%LOGDIR%\last_pending.log"""
if errorlevel 1 goto :failed

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""`) do set "END_AT=%%i"
echo End              : %END_AT%>> "%SUMMARY%"
echo Overall          : PASS>> "%SUMMARY%"

echo.
echo Validation completed successfully.
echo Logs: %LOGDIR%
echo Summary: %SUMMARY%
goto :eof

:run_step
set "STEP_NO=%~1"
set "STEP_NAME=%~2"
set "STEP_CMD=%~3"
echo [%STEP_NO%/7] %STEP_NAME%
echo [%STEP_NO%/7] %STEP_NAME%>> "%SUMMARY%"
echo Command: %STEP_CMD%>> "%SUMMARY%"
call %STEP_CMD%
if errorlevel 1 exit /b 1
echo Result: PASS>> "%SUMMARY%"
if exist "%LOGDIR%\full.log" if "%STEP_NAME%"=="Full test" type "%LOGDIR%\full.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
if exist "%LOGDIR%\ext_multi.log" if "%STEP_NAME%"=="Mixed CMD=98/99" type "%LOGDIR%\ext_multi.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
if exist "%LOGDIR%\block.log" if "%STEP_NAME%"=="Block test" type "%LOGDIR%\block.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
if exist "%LOGDIR%\boundary.log" if "%STEP_NAME%"=="Boundary test" type "%LOGDIR%\boundary.log" | findstr /R /C:"^\[.*: " /C:"^TOTAL:" /C:"^TOLERATED:" /C:"^  ">> "%SUMMARY%"
if exist "%LOGDIR%\recovery_write.log" if "%STEP_NAME%"=="Recovery write" type "%LOGDIR%\recovery_write.log" | findstr /R /C:"^summary ">> "%SUMMARY%"
if exist "%LOGDIR%\recovery_read.log" if "%STEP_NAME%"=="Recovery read" type "%LOGDIR%\recovery_read.log" | findstr /R /C:"^summary ">> "%SUMMARY%"
if exist "%LOGDIR%\last_pending.log" if "%STEP_NAME%"=="Last writable probe" type "%LOGDIR%\last_pending.log" >> "%SUMMARY%"
echo.>> "%SUMMARY%"
exit /b 0

:failed
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm:ss\""`) do set "END_AT=%%i"
echo Result: FAIL>> "%SUMMARY%"
echo End              : %END_AT%>> "%SUMMARY%"
echo Overall          : FAIL>> "%SUMMARY%"
echo.
echo Validation sequence failed. Check logs under %LOGDIR%.
exit /b 1

:usage
echo Usage:
echo   tools\run_validation_all.bat ^<HOST^> ^<PORT^> [PROTOCOL] [COUNT] [TIMEOUT] [RETRIES] [PC10_BLOCK_WORDS] [LOCAL_PORT] [RECOVERY_COUNT]
echo.
echo Example:
echo   tools\run_validation_all.bat 192.168.250.101 1027 udp 4 5 2 0x200 12000 60
exit /b 2
