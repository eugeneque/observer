"""Обновление из интерфейса (кнопка «Обновить»).

Служба работает без прав root и перезапустить себя не может. Поэтому страница только оставляет
запрос data/.update-request, а юнит systemd counterparty-checker-update-ui.path (ставит
linux/autostart-on.sh) от имени root запускает linux/update.sh --ui. Скрипт пишет вывод в
data/update.log и итог в data/update-status.json — их страница читает, пока ждёт перезапуска."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .config import BASE_DIR, settings

SERVICE = "counterparty-checker"
PATH_UNIT = Path(f"/etc/systemd/system/{SERVICE}-update-ui.path")
BRANCH = "main"

_latest: dict = {"at": 0.0, "value": None}


def _files() -> tuple[Path, Path, Path, Path]:
    d = settings.data_dir
    return d / ".update-request", d / "update.log", d / "update-status.json", d / ".update.lock"


def _git(*args: str) -> str:
    # safe.directory: код принадлежит установившему, а служба может работать под другим пользователем
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(BASE_DIR), *args],
                       capture_output=True, text=True, timeout=10)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "git")
    return r.stdout.strip()


def available() -> tuple[bool, str]:
    """Можно ли обновить кнопкой; если нет — что сделать администратору."""
    if not sys.platform.startswith("linux"):
        return False, "Кнопка работает на Linux-сервере со службой systemd."
    if not (BASE_DIR / ".git").is_dir():
        return False, "Папка не подключена к GitHub. Выполните на сервере один раз:  bash linux/update.sh"
    if not PATH_UNIT.exists():
        return False, "Кнопка ещё не включена. Выполните на сервере один раз:  sudo bash linux/autostart-on.sh"
    return True, ""


def current() -> dict | None:
    try:
        sha, short, date, subject = _git("log", "-1", "--format=%H%x1f%h%x1f%cI%x1f%s").split("\x1f")
        return {"sha": sha, "short": short, "date": date, "subject": subject}
    except Exception:
        return None


def outdated(cur: dict | None, new: dict | None) -> bool:
    """Есть ли на GitHub версия новее установленной (локальные коммиты поверх main — не повод обновляться)."""
    if not cur or not new or cur["sha"] == new["sha"]:
        return False
    try:
        _git("merge-base", "--is-ancestor", new["sha"], "HEAD")
        return False
    except Exception:
        return True


def _repo() -> str | None:
    try:
        url = _git("remote", "get-url", "origin")
    except Exception:
        url = "https://github.com/eugeneque/observer.git"
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else None


async def latest(refresh: bool = False) -> dict | None:
    """Последняя версия ветки main на GitHub и итог CI по ней (кэш на минуту)."""
    if not refresh and _latest["value"] and time.monotonic() - _latest["at"] < 60:
        return _latest["value"]
    repo = _repo()
    if not repo:
        return None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "counterparty-checker"}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            r = await client.get(f"https://api.github.com/repos/{repo}/commits/{BRANCH}")
            r.raise_for_status()
            c = r.json()
            ci = "unknown"
            r2 = await client.get(f"https://api.github.com/repos/{repo}/commits/{c['sha']}/check-runs",
                                  params={"per_page": 100})
            if r2.is_success:
                runs = r2.json().get("check_runs", [])
                if not runs:
                    ci = "none"
                elif any(x["status"] != "completed" for x in runs):
                    ci = "pending"
                elif all(x["conclusion"] in ("success", "skipped", "neutral") for x in runs):
                    ci = "success"
                else:
                    ci = "failure"
    except Exception:
        return None
    value = {"sha": c["sha"], "short": c["sha"][:7], "date": c["commit"]["committer"]["date"],
             "subject": c["commit"]["message"].split("\n", 1)[0], "ci": ci}
    _latest.update(at=time.monotonic(), value=value)
    return value


def _locked(lock: Path) -> bool:
    """Держит ли кто-то блокировку update.sh (flock) — значит, обновление идёт прямо сейчас."""
    try:
        import fcntl
        with open(lock, "a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass
    return False


def state() -> dict:
    req, log, status, lock = _files()
    try:
        last = json.loads(status.read_text(encoding="utf-8"))
    except Exception:
        last = None
    started = 0.0
    if last and last.get("state") == "running":
        try:
            from datetime import datetime
            started = datetime.fromisoformat(last["time"]).timestamp()
        except Exception:
            pass
    if req.exists():
        phase = "queued"
    # update.sh берёт блокировку не сразу после старта — первые секунды верим update-status.json
    elif _locked(lock) or time.time() - started < 120:
        phase = "running"
    else:
        phase = "idle"
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
    except Exception:
        lines = []
    return {"phase": phase, "last": last, "log": lines}


def request(force: bool) -> None:
    req = _files()[0]
    req.parent.mkdir(parents=True, exist_ok=True)
    tmp = req.with_suffix(".tmp")
    tmp.write_text(json.dumps({"force": force, "time": time.time()}), encoding="utf-8")
    tmp.replace(req)  # юнит .path срабатывает на появление файла — он должен появиться уже целым
