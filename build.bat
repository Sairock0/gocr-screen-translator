@echo off
setlocal
cd /d "%~dp0"
title GOCR - build
echo.
echo  ===  GOCR: building the executable  ===
echo.

set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto :nopython
echo Using Python: %PY%
echo Closing GOCR if it is running...
taskkill /IM GOCR.exe /F >nul 2>&1

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :error
)

echo Installing dependencies, the first time takes a few minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo Packaging with PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean GOCR.spec
if errorlevel 1 goto :error

echo Creating the portable zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\GOCR\*' -DestinationPath 'dist\GOCR-portable.zip' -Force"

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC goto :installer
echo.
echo  Optional: install Inno Setup 6 from jrsoftware.org to also build an installer.
goto :done

:installer
echo Building the installer...
"%ISCC%" /Q installer.iss
if errorlevel 1 echo Could not build the installer, but the executable is ready.

:done
echo.
echo  ===  DONE  ===
echo   App:        dist\GOCR\GOCR.exe
echo   Portable:   dist\GOCR-portable.zip   (to share)
if defined ISCC echo   Installer:  dist\GOCR-Setup.exe
echo.
explorer "dist"
pause
exit /b 0

:nopython
echo.
echo  Python 3.10 or newer was not found.
echo  Download it from https://www.python.org/downloads/
echo  IMPORTANT: check "Add python.exe to PATH" during the installation.
echo  Then run build.bat again.
echo.
pause
exit /b 1

:error
echo.
echo  Something went wrong. Check the messages above.
pause
exit /b 1
