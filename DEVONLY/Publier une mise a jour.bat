@echo off
rem Publie une nouvelle version de StoryCore pour les testeurs (voir scripts\release\publish.ps1).
rem Avant : change APP_VERSION dans app\backend\story\config.py.
rem Pour fabriquer l installateur sans rien publier : Publier une mise a jour.bat -NoUpload
title Publier StoryCore
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\release\publish.ps1" %*
echo.
pause
