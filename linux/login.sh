#!/usr/bin/env bash
# Ручной вход в источник (если сайт просит код из письма или капчу):  bash linux/login.sh rusprofile|globas
# Нужно окно браузера: запускайте на сервере с рабочим столом или через  ssh -X сервер
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_venv

case "${1:-}" in
  rusprofile|globas) ;;
  *) echo "Использование: bash linux/login.sh rusprofile   или   bash linux/login.sh globas" >&2; exit 1 ;;
esac

if [ "$(uname -s)" = "Linux" ] && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  cat >&2 <<MSG
[ОШИБКА] Нет графического экрана — окно браузера открыть негде.
Варианты:
  1) подключиться с пересылкой окон:  ssh -X пользователь@сервер  и запустить скрипт снова
     (на сервере нужен пакет xauth, на Windows-компьютере — X-сервер, например VcXsrv или MobaXterm);
  2) войти на любом компьютере с этим же сервисом (windows\\login.bat $1 или linux/login.sh $1),
     затем скопировать папку data/browser/$1 на сервер в $ROOT/data/browser/ и перезапустить службу.
MSG
  exit 1
fi

# Профиль браузера должен принадлежать пользователю службы, иначе она не сможет его открыть
OWNER="$(stat -c %U "$ROOT/data" 2>/dev/null || stat -f %Su "$ROOT/data")"
if [ "$(id -u)" -eq 0 ] && [ "$OWNER" != "root" ]; then
  exec sudo -u "$OWNER" --preserve-env=DISPLAY,XAUTHORITY,PLAYWRIGHT_BROWSERS_PATH,PYTHONIOENCODING "$PY" -m scripts.login "$1"
fi
exec "$PY" -m scripts.login "$1"
