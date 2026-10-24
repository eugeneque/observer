#!/usr/bin/env bash
# Запуск сервиса в консоли (остановить — Ctrl+C):  bash linux/run.sh [--port 8020] [--open]
# Для постоянной работы на сервере используйте службу: sudo bash linux/autostart-on.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_venv

if [ -f "$UNIT" ] && systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
  echo "Служба $SERVICE уже запущена (порт $(env_port)). Остановить: sudo systemctl stop $SERVICE" >&2
  exit 1
fi

exec "$PY" run.py "$@"
