import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta

from .config import settings

_lock = threading.Lock()
_conn = sqlite3.connect(settings.db_path, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("""
CREATE TABLE IF NOT EXISTS checks (
    id TEXT PRIMARY KEY,
    inn TEXT NOT NULL,
    kpp TEXT,
    params TEXT,
    status TEXT NOT NULL,          -- queued | running | done | error
    stage TEXT,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)""")
_conn.execute("CREATE INDEX IF NOT EXISTS ix_checks_inn ON checks (inn, kpp, created_at)")
_conn.commit()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create(inn: str, kpp: str | None, params: dict) -> str:
    cid = uuid.uuid4().hex
    with _lock:
        _conn.execute("INSERT INTO checks (id, inn, kpp, params, status, created_at, updated_at) "
                      "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                      (cid, inn, kpp, json.dumps(params, ensure_ascii=False), _now(), _now()))
        _conn.commit()
    return cid


def update(cid: str, **fields) -> None:
    if "result" in fields:
        fields["result"] = json.dumps(fields["result"], ensure_ascii=False)
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock:
        _conn.execute(f"UPDATE checks SET {cols} WHERE id = ?", (*fields.values(), cid))
        _conn.commit()


def get(cid: str) -> dict | None:
    with _lock:
        row = _conn.execute("SELECT * FROM checks WHERE id = ?", (cid,)).fetchone()
    return _row(row)


def find_recent(inn: str, kpp: str | None, hours: int) -> dict | None:
    """Готовая или выполняющаяся проверка по тем же реквизитам — чтобы не платить за повторный анализ."""
    since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    with _lock:
        row = _conn.execute(
            "SELECT * FROM checks WHERE inn = ? AND IFNULL(kpp, '') = ? AND status != 'error' AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1", (inn, kpp or "", since)).fetchone()
    return _row(row)


def list_recent(query: str = "", limit: int = 50) -> list[dict]:
    """История для веб-интерфейса: поиск по ИНН или наименованию контрагента."""
    sql, args = "SELECT * FROM checks", []
    if query:
        sql += " WHERE inn LIKE ? OR result LIKE ?"
        args += [f"{query}%", f"%{query}%"]
    sql += " ORDER BY created_at DESC LIMIT ?"
    with _lock:
        rows = _conn.execute(sql, (*args, limit)).fetchall()
    return [_row(r) for r in rows]


def delete(cid: str) -> None:
    with _lock:
        _conn.execute("DELETE FROM checks WHERE id = ?", (cid,))
        _conn.commit()


def unfinished() -> list[dict]:
    with _lock:
        rows = _conn.execute("SELECT * FROM checks WHERE status IN ('queued', 'running') ORDER BY created_at").fetchall()
    return [_row(r) for r in rows]


def _row(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["result"] = json.loads(d["result"]) if d["result"] else None
    d["params"] = json.loads(d["params"]) if d["params"] else {}
    return d
