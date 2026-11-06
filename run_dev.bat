@echo off
rem Runs GOCR from source (no executable needed). Run build.bat once first to install the dependencies.
cd /d "%~dp0"
taskkill /IM GOCR.exe /F >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
  echo Run build.bat first to install the dependencies.
  pause
  exit /b 1
)
echo Checking dependencies...
call scripts\install_deps.bat --quiet
if errorlevel 1 (
  echo Could not install the dependencies. Check your internet connection and try again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
