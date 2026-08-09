@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Stop CampusCue

if not exist ".venv\Scripts\python.exe" (
  echo CampusCue is not installed in this folder.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "scripts\campuscue_runtime.py" stop
set "CAMPUSCUE_EXIT=%errorlevel%"
echo.
pause
exit /b %CAMPUSCUE_EXIT%
