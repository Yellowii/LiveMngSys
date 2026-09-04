@echo off
setlocal
cd /d "%~dp0"
title MusicBot

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-MusicBot.ps1"
if errorlevel 1 (
  echo.
  echo MusicBot failed to start. See the error above.
  pause
)

