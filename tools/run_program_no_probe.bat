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
set "CASES="
set "CANDIDATE_NOS="
set "LOG="

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"

shift
shift
shift
shift
shift
shift

:parse_args
if "%~1"=="" goto :args_done

call :is_candidate_token "%~1"
if errorlevel 1 goto :candidate_token

:not_candidate
if defined CANDIDATE_NOS goto :treat_as_log
if /I "%~x1"==".log" goto :treat_as_log
if defined CASES (
  set "CASES=%CASES%,%~1"
) else (
  set "CASES=%~1"
)
shift
goto :parse_args

:candidate_token
if defined CANDIDATE_NOS (
  set "CANDIDATE_NOS=%CANDIDATE_NOS%,%~1"
) else (
  set "CANDIDATE_NOS=%~1"
)
shift
goto :parse_args

:treat_as_log
set "LOG=%~1"
shift
goto :parse_args

:args_done
if "%CASES%"=="" set "CASES=ext00,gx07,p1"
if "%CANDIDATE_NOS%"=="" set "CANDIDATE_NOS=0x00,0x01,0x02,0x03,0x07"

set "LOG_ARG="
if not "%LOG%"=="" set "LOG_ARG=--log ""%LOG%"""

python -m tools.program_no_probe ^
  --host %HOST% ^
  --port %PORT% ^
  --protocol %PROTOCOL% ^
  --local-port %LOCAL_PORT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --cases "%CASES%" ^
  --candidate-nos "%CANDIDATE_NOS%" ^
  %LOG_ARG%

exit /b %errorlevel%

:is_candidate_token
set "TOKEN=%~1"
if "%TOKEN%"=="" exit /b 0
set "HEAD2=%TOKEN:~0,2%"
set "HEAD1=%TOKEN:~0,1%"
if /I "%HEAD2%"=="0x" exit /b 1
for %%D in (0 1 2 3 4 5 6 7 8 9) do if "%HEAD1%"=="%%D" exit /b 1
exit /b 0

:usage
echo Usage:
echo   tools\run_program_no_probe.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [CASES] [CANDIDATE_NOS] [LOG]
echo.
echo Default probe ^(EX/GX/P1^):
echo   tools\run_program_no_probe.bat 192.168.250.101 1027 udp 12000 5 2
echo.
echo Include P2/P3:
echo   tools\run_program_no_probe.bat 192.168.250.101 1027 udp 12000 5 2 ext00,gx07,p1,p2,p3
echo.
echo With log:
echo   tools\run_program_no_probe.bat 192.168.250.101 1027 udp 12000 5 2 ext00,gx07,p1 0x00,0x01,0x02,0x03,0x07 program_no_probe.log
echo.
echo PowerShell note:
echo   comma lists may be passed either quoted or unquoted; unquoted lists are re-joined by this batch file
exit /b 2
