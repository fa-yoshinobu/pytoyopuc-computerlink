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
set "INDEXES=%~7"
set "REGISTER_EXNOS=%~8"
call set "ARG9=%%9"
call set "ARG10=%%10"

if "%PROTOCOL%"=="" set "PROTOCOL=tcp"
if "%LOCAL_PORT%"=="" set "LOCAL_PORT=0"
if "%TIMEOUT%"=="" set "TIMEOUT=5"
if "%RETRIES%"=="" set "RETRIES=0"
if "%INDEXES%"=="" set "INDEXES=0x0,0x8000"
if "%REGISTER_EXNOS%"=="" set "REGISTER_EXNOS=0x40,0x41"

rem PowerShell splits comma-separated values into separate arguments unless quoted.
rem Support the common unquoted form:
rem   ... 0x0,0x8000 0x40,0x41
rem which arrives as four arguments: 0x0 0x8000 0x40 0x41
if not "%~7"=="" if not "%ARG10%"=="" (
  set "TMP7=%~7"
  set "TMP8=%~8"
  if "%TMP7:,=%"=="%TMP7%" if "%TMP8:,=%"=="%TMP8%" (
    if "%ARG9:,=%"=="%ARG9%" if "%ARG10:,=%"=="%ARG10%" (
      set "INDEXES=%TMP7%,%TMP8%"
      set "REGISTER_EXNOS=%ARG9%,%ARG10%"
    )
  )
)

python -m tools.fr_probe ^
  --host %HOST% ^
  --port %PORT% ^
  --protocol %PROTOCOL% ^
  --local-port %LOCAL_PORT% ^
  --timeout %TIMEOUT% ^
  --retries %RETRIES% ^
  --indexes "%INDEXES%" ^
  --register-exnos "%REGISTER_EXNOS%"

exit /b %errorlevel%

:usage
echo Usage:
echo   tools\run_fr_probe.bat ^<HOST^> ^<PORT^> [PROTOCOL] [LOCAL_PORT] [TIMEOUT] [RETRIES] [INDEXES] [REGISTER_EXNOS]
echo.
echo Example ^(TCP^):
echo   tools\run_fr_probe.bat 192.168.250.101 1025 tcp 0 5 0 "0x0,0x8000" "0x40,0x41"
echo.
echo Example ^(UDP^):
echo   tools\run_fr_probe.bat 192.168.250.101 1027 udp 12000 5 2 "0x0,0x8000" "0x40,0x41"
echo   tools\run_fr_probe.bat 192.168.250.101 1027 udp 12000 5 2 0x0,0x8000 0x40,0x41
exit /b 2
