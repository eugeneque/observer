@echo off
rem Запуск без окна и браузера — его вызывает задача автозапуска. Журнал: data\service.log
chcp 65001 >nul
cd /d "%~dp0.."
if not exist data mkdir data
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" run.py >> "data\service.log" 2>&1
