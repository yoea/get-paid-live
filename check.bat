@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Page in sync with src\ ...
python merge.py --check
if errorlevel 1 (
  echo       out of date, regenerating ...
  python merge.py
  python merge.py --check
  if errorlevel 1 goto fail
)

echo [2/4] Syntax check src\*.js ...
node --check src\engine.js
if errorlevel 1 goto fail
node --check src\ui.js
if errorlevel 1 goto fail

echo [3/4] Engine + theme + holiday tests ...
node tests\engine.test.js
if errorlevel 1 goto fail
python tests\theme.test.py
if errorlevel 1 goto fail
python tests\holidays.test.py
if errorlevel 1 goto fail

echo [4/4] Python compile ...
python -m py_compile desktop.py store.py build.py merge.py version.py win_titlebar.py
if errorlevel 1 goto fail

echo.
echo ALL CHECKS PASSED
exit /b 0

:fail
echo.
echo CHECK FAILED - see messages above.
exit /b 1
