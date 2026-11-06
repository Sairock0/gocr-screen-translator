@echo off
rem Installs or updates GOCR's Python dependencies in .venv (used by build.bat and run_dev.bat).
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
rem Older versions used the CPU-only onnxruntime: replace it with the DirectML build (same module name).
".venv\Scripts\python.exe" -m pip show onnxruntime >nul 2>&1
if not errorlevel 1 (
  echo Switching ONNX Runtime to the graphics-card build...
  ".venv\Scripts\python.exe" -m pip uninstall -y onnxruntime >nul
  ".venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps onnxruntime-directml
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt %*
exit /b %errorlevel%
