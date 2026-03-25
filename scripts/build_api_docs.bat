@echo off
setlocal

REM Generate API documentation with pdoc.
REM Install dependency first:
REM   pip install .[docs]
REM or
REM   pip install pdoc

python -m pdoc toyopuc -o docs/api
if errorlevel 1 exit /b %errorlevel%

echo API docs generated under docs\api
exit /b 0
