#!/usr/bin/env bash
# Отключить автообновление из GitHub:  sudo bash linux/autoupdate-off.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$ROOT/linux/autoupdate-off.sh" "$@"
fi

systemctl disable --now "$SERVICE-update.timer" 2>/dev/null || true
rm -f "/etc/systemd/system/$SERVICE-update.timer" "/etc/systemd/system/$SERVICE-update.service"
systemctl daemon-reload
echo "Автообновление отключено. Обновить вручную: bash linux/update.sh"
