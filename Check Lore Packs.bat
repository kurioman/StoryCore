@echo off
setlocal
title StoryCore - Check Lore Packs
cd /d "%~dp0"

rem Checks every lore pack in the Lorepack folder (or the folders dropped on this file) and prints a report.
rem Nothing in the data folder is read or written. Keep this file ASCII-only.
set "PYEXE=%~dp0app\python\python.exe"
if not exist "%PYEXE%" (
  echo.
  echo  StoryCore cannot find its files. Extract the whole ZIP first, then run this file from the extracted folder.
  echo.
  pause
  exit /b 1
)
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

echo.
echo  Checking lore packs...
echo.
"%PYEXE%" --check-hash-based-pycs always scripts\check_packs.py %*
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" (
  echo  Some packs have ERRORS: the app may skip them or files inside them. See above.
) else (
  echo  Done. Warnings are worth fixing but do not stop the pack from loading.
)
echo.
pause
