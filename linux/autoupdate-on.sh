#!/usr/bin/env bash
# Автообновление из GitHub по таймеру systemd:  sudo bash linux/autoupdate-on.sh
# Каждые 15 минут запускает linux/update.sh --auto: новая версия из main ставится, когда на ней прошёл CI
# и нет идущих проверок. Другой интервал — UPDATE_INTERVAL=1h (формат systemd: 30min, 2h, 1d).
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_venv

if [ "$(id -u)" -ne 0 ]; then
  exec sudo UPDATE_INTERVAL="${UPDATE_INTERVAL:-}" bash "$ROOT/linux/autoupdate-on.sh" "$@"
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "[ОШИБКА] systemd не найден. Обновляйте вручную: bash linux/update.sh" >&2
  exit 1
fi
[ -f "$UNIT" ] || echo "[ВНИМАНИЕ] Служба $SERVICE не установлена — после обновления её некому перезапускать: sudo bash linux/autostart-on.sh"

INTERVAL="${UPDATE_INTERVAL:-15min}"

cat > "/etc/systemd/system/$SERVICE-update.service" <<UNIT
[Unit]
Description=Обновление сервиса проверки контрагентов из GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $ROOT/linux/update.sh --auto
UNIT

cat > "/etc/systemd/system/$SERVICE-update.timer" <<UNIT
[Unit]
Description=Проверка обновлений сервиса проверки контрагентов

[Timer]
OnBootSec=5min
OnUnitActiveSec=$INTERVAL
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now "$SERVICE-update.timer" >/dev/null

echo "Автообновление включено: проверка каждые $INTERVAL."
echo "Журнал обновлений:  journalctl -u $SERVICE-update -n 50"
echo "Обновить сейчас:    bash linux/update.sh"
echo "Отключить:          sudo bash linux/autoupdate-off.sh"
