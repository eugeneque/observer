#!/usr/bin/env bash
# Журнал службы в реальном времени (выход — Ctrl+C):  bash linux/logs.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
exec journalctl -u "$SERVICE" -n 200 -f
