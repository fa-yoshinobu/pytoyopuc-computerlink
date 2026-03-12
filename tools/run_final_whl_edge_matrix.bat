@echo off
setlocal EnableDelayedExpansion

if "%~1"=="" goto usage
if "%~2"=="" goto usage

set "HOST=%~1"
set "TCP_PORT=%~2"
set "UDP_PORT=%~3"
set "LOCAL_PORT=%~4"
set "TIMEOUT=%~5"
set "RETRIES=%~6"
set "LOG_DIR=%~7"

if "%UDP_PORT%"=="" set "UDP_PORT=1027"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=12000"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=1"
if "%LOG_DIR%"=="" set "LOG_DIR=final_whl_edge_matrix_logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "OVERALL=0"

echo === final_whl_edge_test matrix start ===
echo host=%HOST% tcp_port=%TCP_PORT% udp_port=%UDP_PORT% local_port=%LOCAL_PORT% timeout=%TIMEOUT% retries=%RETRIES%

for %%P in (P1 P2 P3) do (
  for %%M in (bits hl) do (
    set "LOG_FILE=%LOG_DIR%\tcp_%%P_%%M.log"
    echo.
    echo [TCP] prefix=%%P mode=%%M
    python tools\final_whl_edge_test.py ^
      --host %HOST% ^
      --port %TCP_PORT% ^
      --protocol tcp ^
      --program-prefix %%P ^
      --write-mode %%M ^
      --timeout %TIMEOUT% ^
      --retries %RETRIES% ^
      --log "!LOG_FILE!"
    if errorlevel 1 set "OVERALL=1"
  )
)

for %%P in (P1 P2 P3) do (
  for %%M in (bits hl) do (
    set "LOG_FILE=%LOG_DIR%\udp_%%P_%%M.log"
    echo.
    echo [UDP] prefix=%%P mode=%%M
    python tools\final_whl_edge_test.py ^
      --host %HOST% ^
      --port %UDP_PORT% ^
      --protocol udp ^
      --local-port %LOCAL_PORT% ^
      --program-prefix %%P ^
      --write-mode %%M ^
      --timeout %TIMEOUT% ^
      --retries %RETRIES% ^
      --log "!LOG_FILE!"
    if errorlevel 1 set "OVERALL=1"
  )
)

echo.
if "%OVERALL%"=="0" (
  echo Matrix result: PASS
) else (
  echo Matrix result: FAIL
)
echo Logs: %LOG_DIR%
exit /b %OVERALL%

:usage
echo Usage:
echo   tools\run_final_whl_edge_matrix.bat HOST TCP_PORT [UDP_PORT] [LOCAL_PORT] [TIMEOUT] [RETRIES] [LOG_DIR]
echo.
echo Example:
echo   tools\run_final_whl_edge_matrix.bat 192.168.250.101 1025 1027 12000 5 1 final_whl_edge_matrix_logs
exit /b 1
