@echo off
rem Double-click to open the PGx Translator upload page in your browser.
cd /d "%~dp0"
set PY=py
where py >nul 2>nul || set PY=python
if not exist ".installed" (
  echo Installing required libraries - first run only...
  %PY% -m pip install -r requirements.txt || goto :fail
  echo ok> .installed
)
echo.
echo PGx Translator is running. Your browser will open in a moment.
echo Close this window to stop it.
start "" http://127.0.0.1:5000
%PY% -m pgx_translator.web
goto :eof
:fail
echo.
echo Setup failed. Make sure Python is installed from python.org, then try again.
pause
