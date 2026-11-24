@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"

py -3.12 -m venv .venv-build
if errorlevel 1 goto error

".venv-build\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto error

".venv-build\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto error

".venv-build\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --clean --onefile --windowed --name WhatToCook ^
    --collect-submodules PyQt6.uic ^
    --add-data "ui:ui" ^
    --add-data "data\schema.sql:data" ^
    --add-data "data\help.txt:data" main.py
if errorlevel 1 goto error

echo Build completed: dist\WhatToCook.exe
echo Check the application on Windows before submitting it.
pause
exit /b 0

:error
echo Build stopped. Read the error above.
pause
exit /b 1
