@echo off
chcp 65001 >nul
setlocal
net session >nul 2>&1
if errorlevel 1 (
  echo Запустите этот файл от имени администратора: правой кнопкой - "Запуск от имени администратора".
  pause & exit /b 1
)
set "TASK=CounterpartyChecker"
set "SVC=%~dp0service.bat"
set "PORT=8010"

echo Создаю задачу "%TASK%": запуск сервиса при включении компьютера (под SYSTEM) ...
schtasks /Create /TN "%TASK%" /TR "\"%SVC%\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F || goto :fail

echo Открываю порт %PORT% в брандмауэре Windows для 1С и браузеров в сети ...
netsh advfirewall firewall delete rule name="%TASK%" >nul 2>&1
netsh advfirewall firewall add rule name="%TASK%" dir=in action=allow protocol=TCP localport=%PORT% >nul || goto :fail

echo Запускаю сервис сейчас ...
schtasks /Run /TN "%TASK%" >nul
echo.
echo Готово. Интерфейс: http://localhost:%PORT%/   журнал: data\service.log
echo Если порт другой - поменяйте PORT в .env и в этом файле.
pause
exit /b 0

:fail
echo [ОШИБКА] Не удалось настроить автозапуск.
pause
exit /b 1
