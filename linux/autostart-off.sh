#!/usr/bin/env bash
# Остановить службу и убрать автозапуск:  sudo bash linux/autostart-off.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$ROOT/linux/autostart-off.sh" "$@"
fi
PORT="$(env_port)"

systemctl disable --now "$SERVICE" 2>/dev/null || true
rm -f "$UNIT"
systemctl daemon-reload

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw delete allow "$PORT/tcp" >/dev/null 2>&1 || true
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  firewall-cmd --permanent --remove-port="$PORT/tcp" >/dev/null 2>&1 && firewall-cmd --reload >/dev/null
fi
echo "Автозапуск отключён, служба остановлена."
