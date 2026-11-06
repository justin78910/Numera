@echo off
setlocal
cd /d "%~dp0"
title Numera Windows EXE Builder

echo =========================================
echo       Building Numera for Windows
 echo =========================================
echo.
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python not found. Install Python from https://www.python.org/downloads/
    echo and enable the Python launcher, then rerun this file.
    pause
    exit /b 1
  )
  set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating isolated build environment...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto :fail
)
set "PY=.venv\Scripts\python.exe"

echo Installing build dependencies...
"%PY%" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto :fail

echo Building the single-file Windows app...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name Numera --icon numera.ico --add-data "numera.ico;." numera.py
if errorlevel 1 goto :fail

echo.
echo SUCCESS: dist\Numera.exe
 echo You can move Numera.exe anywhere and double-click it.
echo.
explorer "%CD%\dist"
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Review the error messages above.
pause
exit /b 1
