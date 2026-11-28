@echo off
rem Publier ou sauvegarder StoryCore (voir scripts\release\version_and_push.ps1 et scripts\release\publish.ps1).
rem Pour fabriquer l installateur sans rien publier ni envoyer : Publier une mise a jour.bat -NoUpload
title Publier StoryCore
cd /d "%~dp0.."
if /i "%~1"=="-NoUpload" goto publish
echo.
echo   1. Publier une nouvelle version (testeurs PC + telephones)
echo   2. Envoyer seulement le code sur GitHub (sauvegarde, APK de test)
echo.
choice /c 12 /n /m "   Ton choix (1 ou 2) : "
if errorlevel 2 goto pushonly
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\release\version_and_push.ps1"
if errorlevel 1 goto end
:publish
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\release\publish.ps1" %*
goto end
:pushonly
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\release\version_and_push.ps1" -PushOnly
:end
echo.
pause
