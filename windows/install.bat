@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
echo === Установка сервиса проверки контрагентов ===
echo.

rem --- Python 3.11+ : сначала py-launcher, затем python из PATH
set "PY="
for %%V in (3.13 3.12 3.11 3.14) do if not defined PY py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [ОШИБКА] Не найден Python 3.11 или новее.
  echo Установите его с https://www.python.org/downloads/windows/
  echo и при установке отметьте "Add python.exe to PATH". Затем запустите install.bat снова.
  pause & exit /b 1
)
echo Python: %PY%

if not exist ".venv\Scripts\python.exe" (
  echo Создаю виртуальное окружение .venv ...
  %PY% -m venv .venv || goto :fail
)

echo Устанавливаю зависимости ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail

echo Скачиваю браузер Chromium для Rusprofile и Глобаса (около 150 МБ) ...
set "PLAYWRIGHT_BROWSERS_PATH=0"
".venv\Scripts\python.exe" -m playwright install chromium || goto :fail

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Создан файл .env - впишите в него логины Rusprofile и Глобаса.
)

echo.
echo === Готово ===
echo Запуск:       windows\start.bat
echo Автозапуск:   windows\autostart-on.bat  (от имени администратора)
echo Ключи ИИ вводятся в интерфейсе: кнопка "Настройки ИИ".
pause
exit /b 0

:fail
echo.
echo [ОШИБКА] Установка не завершена - см. сообщения выше.
echo Если интернет идёт через прокси, задайте его перед запуском:  set HTTPS_PROXY=http://прокси:порт
pause
exit /b 1
