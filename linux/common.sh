# shellcheck shell=bash
# Общие переменные для скриптов linux/*.sh (подключается через source, сам не запускается)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
SERVICE="counterparty-checker"
UNIT="/etc/systemd/system/$SERVICE.service"

# Chromium лежит внутри .venv — так его видит и служба, запущенная под другим пользователем
export PLAYWRIGHT_BROWSERS_PATH=0
export PYTHONIOENCODING=utf-8

# Значение из .env:  env_get ИМЯ [по умолчанию]
env_get() {
  local v=""
  [ -f "$ROOT/.env" ] && v="$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$ROOT/.env" | tail -n1 | cut -d= -f2- | tr -d ' "\r')"
  echo "${v:-${2:-}}"
}

# Папка данных (DATA_DIR из .env) абсолютным путём
data_dir() {
  local d
  d="$(env_get DATA_DIR "$ROOT/data")"
  case "$d" in /*) ;; *) d="$ROOT/${d#./}" ;; esac
  echo "$d"
}

# Порт из .env (как его читает run.py), по умолчанию 8010
env_port() { env_get PORT 8010; }

# sudo, если скрипт запущен не от root
as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else echo "[ОШИБКА] Нужны права root для: $*" >&2; return 1
  fi
}

require_venv() {
  if [ ! -x "$PY" ]; then
    echo "Сначала запустите установку:  bash linux/install.sh" >&2
    exit 1
  fi
}

# Кнопка «Обновить» в интерфейсе. Служба работает без прав root и перезапустить себя не может, поэтому
# она только кладёт файл-запрос data/.update-request, а юнит .path (от root) замечает его и запускает
# update.sh --ui. Ставится вместе со службой (autostart-on.sh), снимается autostart-off.sh.
UI_UPDATE="$SERVICE-update-ui"

install_update_button() {
  local data
  data="$(data_dir)"
  cat > "/etc/systemd/system/$UI_UPDATE.service" <<UNIT
[Unit]
Description=Обновление сервиса проверки контрагентов по кнопке в интерфейсе
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $ROOT/linux/update.sh --ui
ExecStopPost=/bin/rm -f $data/.update-request
TimeoutStartSec=30min
UNIT
  cat > "/etc/systemd/system/$UI_UPDATE.path" <<UNIT
[Unit]
Description=Запрос обновления из интерфейса сервиса проверки контрагентов

[Path]
PathExists=$data/.update-request
Unit=$UI_UPDATE.service

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now "$UI_UPDATE.path" >/dev/null
}

remove_update_button() {
  systemctl disable --now "$UI_UPDATE.path" 2>/dev/null || true
  rm -f "/etc/systemd/system/$UI_UPDATE.path" "/etc/systemd/system/$UI_UPDATE.service"
}
