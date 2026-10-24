"""Конвейер проверки: отчёты из источников → ИИ → разбор → JSON для 1С."""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from . import store
from .ai import get_provider
from .ai.parse import parse_conclusion
from .ai.prompt import SYSTEM_PROMPT, build_user_prompt
from .config import settings
from .sources import SourceError, globas, rusprofile

log = logging.getLogger(__name__)
_queue: asyncio.Queue[str] = asyncio.Queue()


def validate_inn(inn: str) -> bool:
    if not inn.isdigit() or len(inn) not in (10, 12):
        return False
    d = [int(c) for c in inn]

    def check(weights):
        return sum(w * x for w, x in zip(weights, d)) % 11 % 10

    if len(inn) == 10:
        return check([2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[9]
    return (check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[10]
            and check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[11])


def enqueue(cid: str) -> None:
    _queue.put_nowait(cid)


async def worker() -> None:
    for job in store.unfinished():  # задачи, прерванные перезапуском сервиса
        _queue.put_nowait(job["id"])
    while True:
        cid = await _queue.get()
        try:
            await run_check(cid)
        except Exception as e:
            log.exception("Проверка %s завершилась ошибкой", cid)
            store.update(cid, status="error", stage=None, error=str(e) or e.__class__.__name__)
        finally:
            _queue.task_done()


async def collect_reports(inn: str, kpp: str | None, out_dir: Path) -> tuple[list[Path], str, list[str]]:
    """Скачивает отчёты параллельно; падение одного источника не останавливает проверку."""
    tasks, labels = [], []
    if settings.rusprofile_enabled:
        tasks.append(rusprofile.fetch(inn, kpp, out_dir))
        labels.append("Rusprofile")
    if settings.globas_enabled:
        tasks.append(globas.fetch(inn, kpp, out_dir))
        labels.append("Глобас")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    files, name, warnings = [], "", []
    for label, res in zip(labels, results):
        if isinstance(res, Exception):
            log.warning("%s: %s", label, res)
            warnings.append(str(res) if isinstance(res, SourceError) else f"{label}: {res}")
            continue
        if isinstance(res, tuple):  # rusprofile возвращает ещё и найденную компанию
            path, company = res
            name = company.name
        else:
            path = res
        files.append(path)
    return files, name, warnings


async def run_check(cid: str) -> None:
    job = store.get(cid)
    inn, kpp, params = job["inn"], job["kpp"], job["params"]
    out_dir = settings.files_dir / cid
    out_dir.mkdir(parents=True, exist_ok=True)

    provider = get_provider(params.get("ai"))  # до скачивания: без настроенного ИИ нет смысла ходить на сайты
    store.update(cid, status="running", stage="Скачивание отчётов")
    files, name, warnings = await collect_reports(inn, kpp, out_dir)
    if not files:
        raise RuntimeError("Не удалось получить ни одного отчёта: " + "; ".join(warnings))

    store.update(cid, stage=f"Анализ ИИ ({provider.name})")
    user_prompt = build_user_prompt([f.name for f in files], provider.name, provider.model, params.get("context"))
    ai = await provider.analyze(SYSTEM_PROMPT, user_prompt, files)
    parsed = parse_conclusion(ai.text)
    if not parsed["Итог"]:
        warnings.append("Не удалось однозначно определить ИТОГ в ответе ИИ — см. ТекстЗаключения")

    result = {
        "Контрагент": name or inn,
        "ИНН": inn,
        "КПП": kpp or "",
        "ДатаФормированияЗаключения": datetime.now().isoformat(timespec="seconds"),
        "ТекстЗаключения": ai.text,
        "ИИ/МодельИИ": f"{ai.ai_name} / {ai.model}",
        "ИИ": ai.ai_name,
        "МодельИИ": ai.model,
        **parsed,
        "ФайлыПроверки": [f.name for f in files],
        "Предупреждения": warnings,
    }
    store.update(cid, status="done", stage=None, result=result)
