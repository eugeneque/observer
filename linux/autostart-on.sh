#!/usr/bin/env bash
# Служба systemd: запуск при загрузке сервера и перезапуск при сбое:  sudo bash linux/autostart-on.sh
# Служба работает от имени владельца папки сервиса; другой пользователь — SERVICE_USER=имя
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_venv

if [ "$(id -u)" -ne 0 ]; then
  exec sudo SERVICE_USER="${SERVICE_USER:-}" bash "$ROOT/linux/autostart-on.sh" "$@"
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "[ОШИБКА] systemd не найден. Запускайте сервис через linux/run.sh (например, в screen/tmux)." >&2
  exit 1
fi

RUN_USER="${SERVICE_USER:-${SUDO_USER:-$(stat -c %U "$ROOT")}}"
PORT="$(env_port)"
id "$RUN_USER" >/dev/null 2>&1 || { echo "[ОШИБКА] Нет пользователя $RUN_USER" >&2; exit 1; }

mkdir -p "$ROOT/data"
chown -R "$RUN_USER": "$ROOT/data"
[ -f "$ROOT/.env" ] && chown "$RUN_USER": "$ROOT/.env"

echo "Создаю службу $SERVICE (пользователь $RUN_USER, порт $PORT) ..."
cat > "$UNIT" <<UNIT
[Unit]
Description=Проверка контрагентов (Rusprofile, Глобас, ИИ)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$ROOT
Environment=PLAYWRIGHT_BROWSERS_PATH=0
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUNBUFFERED=1
ExecStart=$PY run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

# Порт для 1С и браузеров в сети
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  echo "Открываю порт $PORT в ufw ..."
  ufw allow "$PORT/tcp" comment "$SERVICE" >/dev/null
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  echo "Открываю порт $PORT в firewalld ..."
  firewall-cmd --permanent --add-port="$PORT/tcp" >/dev/null && firewall-cmd --reload >/dev/null
fi

echo -n "Жду запуска "
for _ in $(seq 1 20); do
  if "$PY" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$PORT/health', timeout=2)" 2>/dev/null; then
    echo
    echo
    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "Готово. Интерфейс: http://${IP:-localhost}:$PORT/"
    echo "Журнал:      bash linux/logs.sh"
    echo "Управление:  sudo systemctl status|restart|stop $SERVICE"
    exit 0
  fi
  echo -n "."; sleep 1
done
echo
echo "[ОШИБКА] Сервис не ответил за 20 секунд. Журнал:" >&2
journalctl -u "$SERVICE" -n 40 --no-pager >&2
exit 1
