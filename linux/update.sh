#!/usr/bin/env bash
# Обновление из GitHub с сохранением настроек:  bash linux/update.sh [--force]
# Берёт последнюю версию ветки main, на которой прошли проверки CI, ставит изменившиеся зависимости,
# перезапускает службу и проверяет её. Если сервис не поднялся — возвращает прежнюю версию.
# Не трогает .env и data/ (ключи ИИ, входы в Rusprofile/Глобас, история проверок): они не хранятся
# в git, а перед обновлением дополнительно копируются в data/backups/.
#   --force  обновить, даже если CI не пройден или ещё идёт, и переустановить зависимости
#   --auto   режим таймера (autoupdate-on.sh): пока идут проверки — отложить обновление
# REPO_URL, BRANCH — откуда брать обновления (по умолчанию origin или github.com/eugeneque/observer, main).
# Папка, установленная из архива, при первом запуске подключается к репозиторию.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Весь сценарий в функции: bash прочитает его целиком до того, как git заменит этот файл новой версией
main() {
  local force=0 auto=0 a
  for a in "$@"; do
    case "$a" in
      --force) force=1 ;;
      --auto) auto=1 ;;
      *) echo "Использование: bash linux/update.sh [--force]" >&2; exit 1 ;;
    esac
  done

  require_venv
  command -v git >/dev/null 2>&1 || {
    echo "[ОШИБКА] Нет git:  sudo apt install git   или   sudo dnf install git" >&2; exit 1; }

  # Владельцы могут различаться: data/ и .env отдаются пользователю службы (autostart-on.sh),
  # а код и .venv остаются за тем, кто устанавливал. Каждую часть меняем от имени её владельца.
  OWNER="$(owner_of "$ROOT/.git" 2>/dev/null || owner_of "$ROOT")"
  VENV_OWNER="$(owner_of "$ROOT/.venv")"
  DATA_DIR="$(env_get DATA_DIR "$ROOT/data")"
  BRANCH="${BRANCH:-main}"
  [ -d "$DATA_DIR" ] || as_owner mkdir -p "$DATA_DIR"
  DATA_OWNER="$(owner_of "$DATA_DIR")"

  # Не запускать два обновления сразу (таймер и вручную)
  if command -v flock >/dev/null 2>&1; then
    as_data touch "$DATA_DIR/.update.lock"
    exec 9>>"$DATA_DIR/.update.lock"
    flock -n 9 || { echo "Обновление уже идёт."; exit 0; }
  fi

  local bootstrap=0
  if [ ! -d .git ]; then
    REPO_URL="${REPO_URL:-https://github.com/eugeneque/observer.git}"
    echo "Папка установлена из архива — подключаю её к $REPO_URL ..."
    g init -q
    g remote add origin "$REPO_URL"
    bootstrap=1
  else
    REPO_URL="${REPO_URL:-$(g remote get-url origin)}"
  fi

  g fetch -q "$REPO_URL" "$BRANCH"
  local old new
  old="$(g rev-parse -q --verify HEAD || true)"
  new="$(g rev-parse FETCH_HEAD)"
  if [ "$old" = "$new" ] && [ $force -eq 0 ]; then
    echo "Установлена последняя версия: $(describe "$new")"
    exit 0
  fi
  echo "Доступна версия: $(describe "$new")"

  # Выкатываем только версии, прошедшие CI (.github/workflows/ci.yml)
  local ci
  ci="$(ci_status "$new")"
  case "$ci" in
    success) echo "Проверки CI пройдены." ;;
    failure)
      if [ $force -eq 0 ]; then
        echo "[ПРОПУСК] Проверки CI для этой версии не прошли — обновление отменено (принудительно: --force)." >&2
        exit 1
      fi
      echo "[ВНИМАНИЕ] CI не пройден, обновляю из-за --force." ;;
    pending|none|unknown)
      local why="ещё идут"
      [ "$ci" = none ] && why="не найдены"
      [ "$ci" = unknown ] && why="недоступны (нет связи с api.github.com)"
      if [ $auto -eq 1 ]; then
        echo "Проверки CI $why — обновлю при следующем запуске."; exit 0
      elif [ $force -eq 0 ] && [ "$ci" = pending ]; then
        echo "Проверки CI ещё идут — повторите через пару минут (или --force)." >&2; exit 1
      fi
      echo "[ВНИМАНИЕ] Проверки CI $why — обновляю без них." ;;
  esac

  # Таймер не прерывает идущие проверки (после перезапуска они продолжились бы, но с начала этапа)
  if [ $auto -eq 1 ] && [ "$(busy_checks)" -gt 0 ]; then
    echo "Идут проверки контрагентов — обновлю при следующем запуске."; exit 0
  fi

  # Новая версия не должна приносить файлы поверх настроек
  local env_rel
  env_rel="$(rel_path "$DATA_DIR")"
  if [ -n "$(g ls-tree -r --name-only "$new" -- .env ${env_rel:+"$env_rel"})" ]; then
    echo "[ОШИБКА] В новой версии в git попали .env или data/ — обновление остановлено, чтобы не затереть настройки." >&2
    exit 1
  fi

  local bk
  bk="$(backup)"
  echo "Копия настроек: $bk"
  if [ -n "$old" ] && [ -n "$(g status --porcelain --untracked-files=no)" ]; then
    g diff HEAD | as_data tee "$bk/local-changes.diff" >/dev/null
    echo "[ВНИМАНИЕ] В коде на сервере были правки — они заменяются версией из GitHub, сохранены в $bk/local-changes.diff"
  fi

  echo "Обновляю код ..."
  g reset -q --hard "$new"
  if [ $bootstrap -eq 1 ]; then
    g branch -M "$BRANCH"
  fi

  if [ $force -eq 1 ] || [ -z "$old" ] || ! g diff --quiet "$old" "$new" -- requirements.txt; then
    install_deps
  fi

  if restart_and_check; then
    echo
    echo "=== Обновлено: $(describe "$new") ==="
    new_settings_hint "$old"
    exit 0
  fi

  if [ -z "$old" ]; then
    echo "[ОШИБКА] Сервис не запустился после обновления, прежней версии в git нет. Журнал: bash linux/logs.sh" >&2
    exit 1
  fi
  echo "[ОШИБКА] Сервис не запустился на новой версии — возвращаю $(describe "$old") ..." >&2
  g reset -q --hard "$old"
  if ! g diff --quiet "$old" "$new" -- requirements.txt; then
    install_deps
  fi
  if restart_and_check; then
    echo "Прежняя версия восстановлена. Причину ищите в журнале: bash linux/logs.sh" >&2
  else
    echo "[ОШИБКА] Прежняя версия тоже не запускается. Журнал: bash linux/logs.sh" >&2
  fi
  exit 1
}

owner_of() { stat -c %U "$1" 2>/dev/null || stat -f %Su "$1"; }

# Команда от имени пользователя: при запуске от root (таймер, sudo) файлы не должны стать root-овыми
run_as() {
  local user="$1"; shift
  if [ "$(id -u)" -eq 0 ] && [ "$user" != "root" ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo -H -u "$user" --preserve-env=PLAYWRIGHT_BROWSERS_PATH,PYTHONIOENCODING,HTTPS_PROXY,HTTP_PROXY,NO_PROXY "$@"
    else
      runuser -u "$user" -- "$@"
    fi
  else
    "$@"
  fi
}

as_owner() { run_as "$OWNER" "$@"; }       # код и git
as_data() { run_as "$DATA_OWNER" "$@"; }   # data/: блокировка, копии, база проверок
as_venv() { run_as "$VENV_OWNER" "$@"; }   # зависимости в .venv

g() { as_owner git -C "$ROOT" "$@"; }

describe() { g log -1 --format='%h %cd «%s»' --date=format:'%d.%m.%Y %H:%M' "$1"; }

# Путь внутри папки сервиса (для data/), пусто — если DATA_DIR вынесен за её пределы
rel_path() {
  case "$1" in
    "$ROOT"/*) echo "${1#"$ROOT"/}" ;;
    /*) ;;
    *) echo "${1#./}" ;;
  esac
}

# Итог проверок GitHub Actions для коммита: success | failure | pending | none | unknown
ci_status() {
  local repo
  repo="$(echo "$REPO_URL" | sed -nE 's#^.*github\.com[:/]([^/]+/[^/]+)$#\1#p' | sed 's/\.git$//')"
  [ -n "$repo" ] || { echo unknown; return; }
  "$PY" - "$repo" "$1" <<'EOF'
import json, sys, urllib.request

repo, sha = sys.argv[1:]
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100",
                             headers={"Accept": "application/vnd.github+json", "User-Agent": "counterparty-checker"})
try:
    runs = json.load(urllib.request.urlopen(req, timeout=15))["check_runs"]
except Exception:
    print("unknown")
    sys.exit()
if not runs:
    print("none")
elif any(r["status"] != "completed" for r in runs):
    print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("success")
else:
    print("failure")
EOF
}

# Сколько проверок в очереди или в работе
busy_checks() {
  local db="$DATA_DIR/checks.sqlite"
  [ -f "$db" ] || { echo 0; return; }
  as_data "$PY" - "$db" 2>/dev/null <<'EOF' || echo 0
import sqlite3, sys
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print(c.execute("SELECT count(*) FROM checks WHERE status IN ('queued', 'running')").fetchone()[0])
EOF
}

# Копия .env, настроек ИИ и базы проверок; хранятся 10 последних
backup() {
  local bk
  bk="$DATA_DIR/backups/$(date +%Y%m%d-%H%M%S)"
  as_data mkdir -p "$bk"
  as_data chmod 700 "$bk"
  # .env может принадлежать другому пользователю — читаем текущим (root), пишем владельцем data/
  [ -f "$ROOT/.env" ] && as_data tee "$bk/.env" <"$ROOT/.env" >/dev/null
  [ -f "$DATA_DIR/ai_settings.json" ] && as_data cp -p "$DATA_DIR/ai_settings.json" "$bk/"
  if [ -f "$DATA_DIR/checks.sqlite" ]; then
    as_data "$PY" -c 'import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' \
      "$DATA_DIR/checks.sqlite" "$bk/checks.sqlite"
  fi
  ls -1dt "$DATA_DIR"/backups/*/ 2>/dev/null | tail -n +11 | while read -r d; do as_data rm -rf "$d"; done
  echo "$bk"
}

install_deps() {
  echo "Обновляю зависимости ..."
  as_venv "$PY" -m pip install -q -r "$ROOT/requirements.txt"
  as_venv "$PY" -m playwright install chromium  # скачает браузер, только если сменилась версия Playwright
}

# Перезапуск службы и ожидание ответа /health. Без службы — подсказка перезапустить вручную.
restart_and_check() {
  if [ ! -f "$UNIT" ]; then
    echo "Служба не установлена — если сервис запущен через linux/run.sh, перезапустите его."
    return 0
  fi
  echo -n "Перезапускаю службу "
  as_root systemctl restart "$SERVICE"
  local port
  port="$(env_port)"
  for _ in $(seq 1 30); do
    if "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/health', timeout=2)" 2>/dev/null; then
      echo " работает."
      return 0
    fi
    echo -n "."; sleep 1
  done
  echo
  journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
  return 1
}

# Параметры, добавленные в .env.example с прежней версии и отсутствующие в .env (значения по умолчанию уже действуют)
new_settings_hint() {
  [ -f "$ROOT/.env" ] && [ -n "$1" ] || return 0
  local k missing="" before
  before="$(g show "$1:.env.example" 2>/dev/null || true)"
  for k in $(grep -oE '^[A-Z0-9_]+=' "$ROOT/.env.example" | tr -d =); do
    echo "$before" | grep -qE "^$k=" && continue
    grep -qE "^[[:space:]]*${k}[[:space:]]*=" "$ROOT/.env" || missing="$missing $k"
  done
  if [ -n "$missing" ]; then
    echo "В новой версии есть параметры, которых нет в вашем .env (работают значения по умолчанию):"
    echo " $missing"
    echo "Описание — в .env.example."
  fi
}

main "$@"
