@echo off
setlocal

set HOST=%1
if "%HOST%"=="" set HOST=127.0.0.1

set PORT=%2
if "%PORT%"=="" set PORT=15000

set PROTOCOL=%3
if "%PROTOCOL%"=="" set PROTOCOL=tcp

set LOGDIR=logs\sim_tests
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo Host      : %HOST%
echo Port      : %PORT%
echo Protocol  : %PROTOCOL%
echo Log Dir   : %LOGDIR%
echo.

echo [1/4] High-level API
python -m tools.high_level_api_test --host %HOST% --port %PORT% --protocol %PROTOCOL% --skip-errors --log "%LOGDIR%\high_level_api.log"
if errorlevel 1 goto :fail
echo.

echo [2/4] W/H/L addressing
python -m tools.whl_addressing_test --host %HOST% --port %PORT% --protocol %PROTOCOL% --skip-errors --log "%LOGDIR%\whl_addressing.log"
if errorlevel 1 goto :fail
echo.

echo [3/4] Clock
python -m tools.clock_test --host %HOST% --port %PORT% --protocol %PROTOCOL% > "%LOGDIR%\clock.log"
if errorlevel 1 goto :fail
echo clock test log: %LOGDIR%\clock.log
echo.

echo [4/4] CPU status
python -m tools.cpu_status_test --host %HOST% --port %PORT% --protocol %PROTOCOL% > "%LOGDIR%\cpu_status.log"
if errorlevel 1 goto :fail
echo cpu status log: %LOGDIR%\cpu_status.log
echo.

echo All simulator tests completed successfully.
exit /b 0

:fail
echo Simulator test failed.
exit /b 1
