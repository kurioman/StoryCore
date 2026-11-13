@echo off
setlocal
title StoryCore
cd /d "%~dp0"

rem Everything is found relative to this file. Keep this file ASCII-only.
set "PYEXE=%~dp0app\python\python.exe"

if not exist "%PYEXE%" (
  echo.
  echo  StoryCore cannot find its files.
  echo  Please extract the WHOLE ZIP to a normal folder first, then run this file
  echo  from the extracted folder. Do not run it from inside the ZIP window.
  echo.
  pause
  exit /b 1
)

rem Ignore any Python settings from this computer: the app uses its own bundled Python.
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist "data\" mkdir "data" >nul 2>nul
set "PROBE=data\.write_test"
(echo ok) > "%PROBE%" 2>nul
if not exist "%PROBE%" (
  echo.
  echo  StoryCore cannot write to this folder:
  echo  %~dp0
  echo  Move the whole folder somewhere you can write, such as Documents or Desktop.
  echo  Avoid Program Files and read-only drives.
  echo.
  pause
  exit /b 1
)
del "%PROBE%" >nul 2>nul

echo.
echo  Starting StoryCore. Your browser will open by itself.
echo  The first start can take up to a minute. Keep this window open while you play.
echo.

rem The release build ships pre-compiled files that Python would otherwise run instead of the edited source.
rem This option makes Python check them against the source and ignore any that are out of date.
"%PYEXE%" --check-hash-based-pycs always scripts\serve.py %*
if errorlevel 1 (
  echo.
  echo  StoryCore stopped with an error. See the messages above.
  echo  README.md has a troubleshooting section.
  echo.
  pause
  exit /b 1
)
exit /b 0
