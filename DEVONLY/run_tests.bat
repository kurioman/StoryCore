@echo off
setlocal
title StoryCore - Engine tests
cd /d "%~dp0.."
rem Runs the engine tests with the bundled Python (Mock narrator, throw-away data: your stories are never touched).
set "PYEXE=%cd%\app\python\python.exe"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
rem --check-hash-based-pycs always: the release ships hash-based .pyc files; without it Python would run old compiled
rem code instead of the current .py files (same flag as Start StoryCore.bat).
"%PYEXE%" --check-hash-based-pycs always DEVONLY\run_tests.py %*
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo  All tests passed.) else (echo  Some tests FAILED: see above.)
echo.
pause
exit /b %RC%
