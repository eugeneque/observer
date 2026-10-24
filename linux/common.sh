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

# Порт из .env (как его читает run.py), по умолчанию 8010
env_port() {
  local p=""
  [ -f "$ROOT/.env" ] && p="$(grep -E '^[[:space:]]*PORT[[:space:]]*=' "$ROOT/.env" | tail -n1 | cut -d= -f2- | tr -d ' "\r')"
  echo "${p:-8010}"
}

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
