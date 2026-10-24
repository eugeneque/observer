@echo off
rem Ручной вход в источник (если сайт просит код из письма или капчу):  windows\login.bat rusprofile | globas
chcp 65001 >nul
cd /d "%~dp0.."
if "%~1"=="" (
  echo Использование: windows\login.bat rusprofile   или   windows\login.bat globas
  pause & exit /b 1
)
".venv\Scripts\python.exe" -m scripts.login %1
pause
