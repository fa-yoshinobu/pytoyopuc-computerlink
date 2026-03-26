@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."

set HOST=%1
if "%HOST%"=="" set HOST=127.0.0.1

set PORT=%2
if "%PORT%"=="" set PORT=15000

set PROTOCOL=%3
if "%PROTOCOL%"=="" set PROTOCOL=tcp

set LOGDIR=logs\sim_tests

pushd "%ROOT_DIR%" >nul
set "PYTHONPATH=%CD%;%PYTHONPATH%"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo Host      : %HOST%
echo Port      : %PORT%
echo Protocol  : %PROTOCOL%
echo Log Dir   : %LOGDIR%
echo.

echo [1/4] High-level API
python "%SCRIPT_DIR%high_level_api_test.py" --host %HOST% --port %PORT% --protocol %PROTOCOL% --skip-errors --log "%LOGDIR%\high_level_api.log"
if errorlevel 1 goto :fail
echo.

echo [2/4] W/H/L addressing
python "%SCRIPT_DIR%whl_addressing_test.py" --host %HOST% --port %PORT% --protocol %PROTOCOL% --skip-errors --log "%LOGDIR%\whl_addressing.log"
if errorlevel 1 goto :fail
echo.

echo [3/4] Clock
python "%SCRIPT_DIR%clock_test.py" --host %HOST% --port %PORT% --protocol %PROTOCOL% > "%LOGDIR%\clock.log"
if errorlevel 1 goto :fail
echo clock test log: %LOGDIR%\clock.log
echo.

echo [4/4] CPU status
python "%SCRIPT_DIR%cpu_status_test.py" --host %HOST% --port %PORT% --protocol %PROTOCOL% > "%LOGDIR%\cpu_status.log"
if errorlevel 1 goto :fail
echo cpu status log: %LOGDIR%\cpu_status.log
echo.

echo All simulator tests completed successfully.
popd >nul
exit /b 0

:fail
popd >nul
echo Simulator test failed.
exit /b 1
