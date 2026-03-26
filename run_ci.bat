@echo off
setlocal EnableDelayedExpansion
set PUBLISH_DIR=.\publish
set SIM_HOST=127.0.0.1
set SIM_PORT=15000
set "PYTHONPATH=%CD%;%PYTHONPATH%"

echo ===================================================
echo [CI] Starting Python Quality Checks and CLI EXE Build...
echo ===================================================

echo [1/7] Running Ruff (Linting)...
python -m ruff check toyopuc tests scripts samples
if %errorlevel% neq 0 (
    echo [ERROR] Ruff check failed.
    exit /b %errorlevel%
)

echo [2/7] Running Ruff (Formatting Check)...
python -m ruff format --check toyopuc tests scripts samples
if %errorlevel% neq 0 (
    echo [ERROR] Code is not formatted.
    exit /b %errorlevel%
)

echo [3/7] Running Mypy (Type Checking core library)...
python -m mypy toyopuc
if %errorlevel% neq 0 (
    echo [ERROR] Mypy type check failed.
    exit /b %errorlevel%
)

echo [4/7] Compiling scripts and samples...
for %%F in (scripts\*.py samples\*.py) do (
    python -m py_compile "%%F"
    if !errorlevel! neq 0 (
        echo [ERROR] Python compile check failed for %%F.
        exit /b !errorlevel!
    )
)

echo [5/7] Running Tests...
python -m pytest tests
if %errorlevel% neq 0 (
    echo [ERROR] Tests failed.
    exit /b %errorlevel%
)

echo [6/7] Running simulator smoke tests...
set "SIM_PID="
set "SIM_PID_FILE=%TEMP%\\toyopuc_computerlink_sim.pid"
if exist "%SIM_PID_FILE%" del /q "%SIM_PID_FILE%"
powershell -NoProfile -Command "$p = Start-Process python -ArgumentList 'scripts\\sim_server.py','--host','%SIM_HOST%','--port','%SIM_PORT%' -PassThru -WindowStyle Hidden; [System.IO.File]::WriteAllText('%SIM_PID_FILE%', $p.Id.ToString())"
if exist "%SIM_PID_FILE%" (
    set /p SIM_PID=<"%SIM_PID_FILE%"
    del /q "%SIM_PID_FILE%"
)
timeout /t 1 /nobreak >nul
call scripts\run_sim_tests.bat %SIM_HOST% %SIM_PORT% tcp
set "SIM_RC=%errorlevel%"
if defined SIM_PID powershell -NoProfile -Command "Stop-Process -Id %SIM_PID% -ErrorAction SilentlyContinue"
if %SIM_RC% neq 0 (
    echo [ERROR] Simulator smoke tests failed.
    exit /b %SIM_RC%
)

echo [7/7] Building CLI Tool with PyInstaller...
python -m PyInstaller --onefile --noconfirm --distpath "%PUBLISH_DIR%" --name toyopuc scripts/interactive_cli.py
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    exit /b %errorlevel%
)

echo ===================================================
echo [SUCCESS] CI passed and CLI EXE published to:
echo %cd%\publish
echo ===================================================
