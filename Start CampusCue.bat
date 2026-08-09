@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title CampusCue

if not exist ".venv\Scripts\python.exe" (
  echo CampusCue is not installed yet. Double-click "Install CampusCue.bat" first.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if errorlevel 1 (
  echo CampusCue requires a Python 3.12 virtual environment.
  echo Run "Install CampusCue.bat" to repair this installation.
  echo.
  pause
  exit /b 1
)

if not exist ".tmp" mkdir ".tmp"
echo CampusCue is starting. The board will open when it is ready.
echo Runtime log: .tmp\backend.log
echo Close this window or use "Stop CampusCue.bat" to stop it.
echo.

".venv\Scripts\python.exe" "scripts\campuscue_runtime.py" run >> ".tmp\backend.log" 2>&1
set "CAMPUSCUE_EXIT=%errorlevel%"

if not "%CAMPUSCUE_EXIT%"=="0" (
  echo CampusCue exited with code %CAMPUSCUE_EXIT%.
  powershell.exe -NoProfile -Command "Get-Content -LiteralPath '.tmp\backend.log' -Tail 20 -ErrorAction SilentlyContinue"
  echo.
  pause
)
exit /b %CAMPUSCUE_EXIT%
