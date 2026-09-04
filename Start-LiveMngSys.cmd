@echo off
setlocal
cd /d "%~dp0"
title LiveMngSys

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-LiveMngSys.ps1"
if errorlevel 1 (
  echo.
  echo LiveMngSys failed to start. See the error above.
  pause
)
