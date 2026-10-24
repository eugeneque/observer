#!/usr/bin/env bash
# Установка на Linux-сервер (Ubuntu/Debian, RHEL/Alma/Rocky) или macOS:  bash linux/install.sh
# Ставит системные пакеты (через sudo), создаёт .venv, библиотеки, Chromium и .env.
# SKIP_SYSTEM_DEPS=1 — не трогать системные пакеты (если их ставит администратор).
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

echo "=== Установка сервиса проверки контрагентов ==="
echo "Папка: $ROOT"
echo

is_linux() { [ "$(uname -s)" = "Linux" ]; }
want_system() { is_linux && [ "${SKIP_SYSTEM_DEPS:-0}" != "1" ]; }

# --- Python 3.11+
find_python() {
  local c
  for c in python3.13 python3.12 python3.11 python3.14 python3; do
    if command -v "$c" >/dev/null 2>&1 &&
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}

SYS_PY="$(find_python || true)"
if [ -z "$SYS_PY" ] && want_system; then
  echo "Python 3.11+ не найден — ставлю из репозитория системы ..."
  if command -v apt-get >/dev/null 2>&1; then
    as_root apt-get update -q
    as_root apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    as_root dnf install -y python3.12 || as_root dnf install -y python3.11
  fi
  SYS_PY="$(find_python || true)"
fi
if [ -z "$SYS_PY" ]; then
  echo "[ОШИБКА] Не найден Python 3.11 или новее."
  echo "  Ubuntu 24.04+, Debian 12+:  sudo apt install python3 python3-venv"
  echo "  Ubuntu 22.04:               sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv"
  echo "  RHEL/Alma/Rocky 9:          sudo dnf install python3.12"
  echo "  macOS:                      brew install python@3.12"
  exit 1
fi
echo "Python: $SYS_PY ($("$SYS_PY" -V 2>&1))"

# --- Виртуальное окружение
if [ ! -x "$PY" ]; then
  echo "Создаю виртуальное окружение .venv ..."
  if ! "$SYS_PY" -m venv .venv 2>/dev/null; then
    rm -rf .venv
    # Debian/Ubuntu: модуль venv идёт отдельным пакетом
    if want_system && command -v apt-get >/dev/null 2>&1; then
      ver="$("$SYS_PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
      as_root apt-get install -y "python$ver-venv"
    fi
    "$SYS_PY" -m venv .venv
  fi
fi

echo "Устанавливаю зависимости ..."
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -r requirements.txt

echo "Скачиваю браузер Chromium для Rusprofile и Глобаса (около 150 МБ) ..."
"$PY" -m playwright install chromium

if want_system; then
  echo "Ставлю системные библиотеки для Chromium ..."
  if ! as_root env PATH="$PATH" "$PY" -m playwright install-deps chromium; then
    echo "[ВНИМАНИЕ] Не удалось поставить библиотеки автоматически (поддерживаются Ubuntu/Debian)."
    echo "            Установите их вручную, если проверка ниже не пройдёт."
  fi
fi

# --- Настройки
if [ ! -f .env ]; then
  cp .env.example .env
  # Сервер обычно доступен из сети — сразу закрываем API и настройки ключом
  TOKEN="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')"
  sed -i.bak "s|^API_TOKEN=.*|API_TOKEN=$TOKEN|" .env && rm -f .env.bak
  chmod 600 .env
  echo
  echo "Создан файл .env — впишите в него логины Rusprofile и Глобаса."
  echo "Сгенерирован ключ доступа API_TOKEN=$TOKEN"
  echo "  (его вводят в веб-интерфейсе и передают из 1С в заголовке X-API-Key)"
fi
mkdir -p data

# --- Проверка, что Chromium запускается на этой машине
echo
echo "Проверяю запуск Chromium ..."
if "$PY" - <<'EOF'
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        await b.close()

asyncio.run(main())
EOF
then
  echo "Chromium работает."
else
  echo "[ОШИБКА] Chromium не запускается — не хватает системных библиотек."
  echo "  Ubuntu/Debian:  sudo $PY -m playwright install-deps chromium"
  exit 1
fi

echo
echo "=== Готово ==="
echo "Запуск в консоли:   bash linux/run.sh"
echo "Как служба:         sudo bash linux/autostart-on.sh   (запуск при загрузке сервера)"
echo "Ключи ИИ вводятся в интерфейсе: кнопка «Настройки ИИ»."
