@echo off
setlocal
cd /d "%~dp0"

if exist ".venv-build\Scripts\python.exe" goto build

echo [1/2] Preparing build environment, internet needed once...
python -m venv .venv-build
if errorlevel 1 goto fail
".venv-build\Scripts\python.exe" -m pip install -U pip -q
".venv-build\Scripts\python.exe" -m pip install pywebview pyinstaller pillow -q
if errorlevel 1 goto fail

:build
echo [2/2] Packaging...
".venv-build\Scripts\python.exe" build.py
if errorlevel 1 goto fail
pause
exit /b 0

:fail
echo.
echo BUILD FAILED - check the messages above.
pause
exit /b 1
