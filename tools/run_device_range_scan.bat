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
set "TARGETS=%~7"

set "DEFAULT_TARGETS=P,K,V,T,C,L,X,Y,M,S,N,R,D,B,P1-P,P1-K,P1-V,P1-T,P1-C,P1-L,P1-X,P1-Y,P1-M,P1-S,P1-N,P1-R,P1-D,P2-P,P2-K,P2-V,P2-T,P2-C,P2-L,P2-X,P2-Y,P2-M,P2-S,P2-N,P2-R,P2-D,P3-P,P3-K,P3-V,P3-T,P3-C,P3-L,P3-X,P3-Y,P3-M,P3-S,P3-N,P3-R,P3-D,EP,EK,EV,ET,EC,EL,EX,EY,EM,GX,GY,GM,ES,EN,H,U,EB"
set "INCLUDE_FR="

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%COARSE_STEP%"=="" set "COARSE_STEP=16"
if "%STOP_AFTER_NG%"=="" set "STOP_AFTER_NG=32"
if "%TARGETS%"=="" set "TARGETS=%DEFAULT_TARGETS%"

for /f %%i in ('powershell -NoProfile -Command "$targets='%TARGETS%'.Split(','); if($targets -contains 'FR'){'--include-fr'}"') do set "INCLUDE_FR=%%i"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
set "LOGDIR=logs\device_range_scan_%STAMP%"
set "COARSE_LOG=%LOGDIR%\coarse.log"
set "FINE_LOG=%LOGDIR%\fine.log"
set "SUMMARY=%LOGDIR%\summary.txt"
set "FINE_TARGETS="

if not exist logs mkdir logs
mkdir "%LOGDIR%"

echo.
echo Host           : %HOST%
echo Port           : %PORT%
echo Protocol       : %PROTOCOL%
echo Local UDP Port : %LOCAL_PORT%
echo Coarse Step    : %COARSE_STEP%
echo Stop After NG  : %STOP_AFTER_NG%
echo Targets        : %TARGETS%
echo Log Dir        : %LOGDIR%
echo.

(
echo Device Range Scan Summary
echo =========================
echo Host           : %HOST%
echo Port           : %PORT%
echo Protocol       : %PROTOCOL%
echo Local UDP Port : %LOCAL_PORT%
echo Coarse Step    : %COARSE_STEP%
echo Stop After NG  : %STOP_AFTER_NG%
echo Targets        : %TARGETS%
echo Log Dir        : %LOGDIR%
echo.
) > "%SUMMARY%"

echo [1/2] Coarse forward scan
echo [1/2] Coarse forward scan>> "%SUMMARY%"
echo Command: python -m tools.exhaustive_writable_scan --host %HOST% --port %PORT% --protocol %PROTOCOL% --local-port %LOCAL_PORT% --targets %TARGETS% %INCLUDE_FR% --step %COARSE_STEP% --refine-boundary --stop-after-ng %STOP_AFTER_NG% --log "%COARSE_LOG%">> "%SUMMARY%"
python -m tools.exhaustive_writable_scan --host %HOST% --port %PORT% --protocol %PROTOCOL% --local-port %LOCAL_PORT% --targets %TARGETS% %INCLUDE_FR% --step %COARSE_STEP% --refine-boundary --stop-after-ng %STOP_AFTER_NG% --log "%COARSE_LOG%"
if errorlevel 1 goto :failed

echo.>> "%SUMMARY%"
type "%COARSE_LOG%" >> "%SUMMARY%"
echo.>> "%SUMMARY%"

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command ^
  "$current=''; $needs=@(); $hasIssue=$false; " ^
  "foreach($line in Get-Content '%COARSE_LOG%'){" ^
    "if($line -match '^=== (.+?)(?: \([^)]+\))? ===$'){" ^
      "if($current -and $hasIssue){$needs += $current}; " ^
      "$current = $matches[1]; $hasIssue = $false; continue" ^
    "} " ^
    "if($line -match '^ok=\d+\s+error=(\d+)$' -and [int]$matches[1] -gt 0){$hasIssue = $true; continue} " ^
    "if($line -like 'stopped early*'){$hasIssue = $true; continue} " ^
    "if($line -match '^holes:\s*(.+)$' -and $matches[1] -ne 'none'){$hasIssue = $true; continue}" ^
  "} " ^
  "if($current -and $hasIssue){$needs += $current}; " ^
  "[string]::Join(',', ($needs | Select-Object -Unique))"` ) do set "FINE_TARGETS=%%i"

echo [2/2] Fine forward scan
if not "%FINE_TARGETS%"=="" (
  echo Fine Targets   : %FINE_TARGETS%
  echo [2/2] Fine forward scan>> "%SUMMARY%"
  echo Fine Targets   : %FINE_TARGETS%>> "%SUMMARY%"
  echo Command: python -m tools.exhaustive_writable_scan --host %HOST% --port %PORT% --protocol %PROTOCOL% --local-port %LOCAL_PORT% --targets %FINE_TARGETS% %INCLUDE_FR% --step 1 --stop-after-ng %STOP_AFTER_NG% --log "%FINE_LOG%">> "%SUMMARY%"
  python -m tools.exhaustive_writable_scan --host %HOST% --port %PORT% --protocol %PROTOCOL% --local-port %LOCAL_PORT% --targets %FINE_TARGETS% %INCLUDE_FR% --step 1 --stop-after-ng %STOP_AFTER_NG% --log "%FINE_LOG%"
  if errorlevel 1 goto :failed

  echo.>> "%SUMMARY%"
  type "%FINE_LOG%" >> "%SUMMARY%"
) else (
  echo Fine Targets   : none
  echo [2/2] Fine forward scan>> "%SUMMARY%"
  echo Fine Targets   : none>> "%SUMMARY%"
  echo Skipped because coarse scan found no targets needing refinement.>> "%SUMMARY%"
)

echo.
echo Device range scan completed successfully.
echo Logs: %LOGDIR%
echo Summary: %SUMMARY%
goto :eof

:failed
echo.
echo Device range scan failed. Check logs under %LOGDIR%.
exit /b 1

:usage
echo Usage:
echo   tools\run_device_range_scan.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [COARSE_STEP] [STOP_AFTER_NG] [TARGETS]
echo.
echo Example ^(TCP^):
echo   tools\run_device_range_scan.bat 192.168.250.101 1025 tcp 0 16 32
echo.
echo Example ^(UDP^):
echo   tools\run_device_range_scan.bat 192.168.250.101 1027 udp 12000 16 32
echo.
echo Note:
echo   By default, this scans all device families currently listed in the project docs.
echo   Missing families are treated as unsupported and skipped automatically.
echo   FR is excluded by default and is scanned only when FR is explicitly included in TARGETS.
exit /b 2
