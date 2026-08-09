@echo off
setlocal
cd /d "%~dp0"
title Uninstall CampusCue
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_campuscue.ps1" -Action Uninstall -Destination "%~dp0"
if errorlevel 1 (
  echo.
  echo Uninstall failed. Review the message above and retry.
  pause
)
