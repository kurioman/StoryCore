@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === Envoi de StoryCore vers GitHub ===
echo.
where git >nul 2>nul
if errorlevel 1 (
  echo Git n'est pas installe sur ce PC.
  echo Installe-le depuis https://git-scm.com/download/win puis relance ce fichier.
  pause
  exit /b 1
)
git config --global --add safe.directory "%CD:\=/%" >nul 2>nul
git remote get-url origin >nul 2>nul
if errorlevel 1 (
  git remote add origin https://github.com/kurioman/StoryCore.git
)
echo Envoi en cours... (la premiere fois, une fenetre GitHub s'ouvre pour te connecter)
echo.
git push -u origin main
if errorlevel 1 (
  echo.
  echo L'envoi a echoue. Copie le message ci-dessus et montre-le a Claude.
) else (
  echo.
  echo Termine ! Ton code est sur https://github.com/kurioman/StoryCore
)
echo.
pause
