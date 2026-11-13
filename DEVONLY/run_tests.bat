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
"%PYEXE%" DEVONLY\run_tests.py %*
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo  All tests passed.) else (echo  Some tests FAILED: see above.)
echo.
pause
exit /b %RC%
