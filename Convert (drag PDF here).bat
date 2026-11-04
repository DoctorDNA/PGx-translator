@echo off
rem Drag one or more Quest PGx PDFs onto this file. Reports are saved in the morpheus_reports folder.
cd /d "%~dp0"
if not exist "%~dp0requirements.txt" (
  echo.
  echo This file must be run from the extracted PGx-translator folder,
  echo not from inside the zip. Right-click the zip, choose "Extract All...",
  echo open the extracted folder and double-click this file there.
  echo.
  pause
  goto :eof
)
set PY=py
where py >nul 2>nul || set PY=python
if "%~1"=="" (
  echo Drag a Quest PGx report PDF onto this file to convert it.
  pause
  goto :eof
)
if not exist ".installed" (
  echo Installing required libraries - first run only...
  %PY% -m pip install -r requirements.txt || goto :fail
  echo ok> .installed
)
echo.
echo Type the patient's current medications, separated by commas
echo (brand or generic names are fine), or just press Enter to skip:
set "MEDS="
set /p "MEDS=Medications: "
%PY% -m pgx_translator %* -o "%~dp0morpheus_reports" --meds "%MEDS%"
echo.
echo Done. Opening the morpheus_reports folder...
start "" "%~dp0morpheus_reports"
pause
goto :eof
:fail
echo.
echo Setup failed. Make sure Python is installed from python.org, then try again.
pause
