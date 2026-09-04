@echo off
setlocal
cd /d "%~dp0"

set "RESTYLE_PORT=7650"
set "RESTYLE_URL=http://127.0.0.1:%RESTYLE_PORT%/"

netstat -ano | findstr /R /C:":%RESTYLE_PORT% .*LISTENING" >nul
if %errorlevel%==0 goto :open

where py >nul 2>nul
if %errorlevel%==0 (
  start "LiveMngSys ReStyle Server" /min py "%~dp0server.py"
) else (
  where python >nul 2>nul
  if errorlevel 1 goto :missing_python
  start "LiveMngSys ReStyle Server" /min python "%~dp0server.py"
)

timeout /t 1 /nobreak >nul

:open
start "" "%RESTYLE_URL%"
exit /b 0

:missing_python
echo [ReStyle] Python 3 was not found. Install Python 3 to enable local file saving.
pause
exit /b 1
