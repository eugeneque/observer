@echo off
chcp 65001 >nul
net session >nul 2>&1
if errorlevel 1 (
  echo Запустите этот файл от имени администратора.
  pause & exit /b 1
)
set "TASK=CounterpartyChecker"
schtasks /End /TN "%TASK%" >nul 2>&1
schtasks /Delete /TN "%TASK%" /F
netsh advfirewall firewall delete rule name="%TASK%" >nul 2>&1
rem Задача остановлена, но python мог остаться — завершаем процесс, слушающий порт сервиса
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8010 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
echo Автозапуск отключён, сервис остановлен.
pause
