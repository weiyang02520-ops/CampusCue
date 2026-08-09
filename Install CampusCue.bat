@echo off
setlocal
cd /d "%~dp0"
title Install CampusCue
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_campuscue.ps1" -Action Install -SourceRoot "%~dp0"
if errorlevel 1 (
  echo.
  echo Installation failed. Review the message above and retry.
  pause
)
