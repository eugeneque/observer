import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import AliasChoices, BaseModel, Field

from . import runtime_settings, service, store
from .ai import available_providers, get_provider, routerai, routerai_models
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(service.worker())
    asyncio.create_task(routerai.catalog())  # названия и цены моделей для интерфейса
    yield
    task.cancel()


app = FastAPI(title="Проверка контрагентов", version="1.0", lifespan=lifespan)


STATIC = Path(__file__).parent / "static"


def check_token(x_api_key: str = Header(default=""), key: str = Query(default="")):
    # key в адресе — для ссылок на PDF из веб-интерфейса, где заголовок не передать
    if settings.api_token and settings.api_token not in (x_api_key, key):
        raise HTTPException(401, "Неверный X-API-Key")


class CheckRequest(BaseModel):
    inn: str = Field(validation_alias=AliasChoices("ИНН", "inn"))
    kpp: str | None = Field(default=None, validation_alias=AliasChoices("КПП", "kpp"))
    ai: str | None = Field(default=None, validation_alias=AliasChoices("ИИ", "ai"),
                           description="gigachat | anthropic; пусто — по настройке сервиса")
    context: str | None = Field(default=None, validation_alias=AliasChoices("КонтекстСделки", "context"))
    force: bool = Field(default=False, validation_alias=AliasChoices("Принудительно", "force"),
                        description="Не брать готовое заключение из кэша")
    wait: int = Field(default=0, ge=0, le=600, validation_alias=AliasChoices("Ожидать", "wait"),
                      description="Сколько секунд ждать результата в этом же запросе")


def render(job: dict) -> dict:
    out = {"id": job["id"], "Статус": job["status"], "Этап": job["stage"] or "",
           "ИНН": job["inn"], "КПП": job["kpp"] or "", "Создано": job["created_at"]}
    if job["status"] == "done":
        out.update(job["result"])
    if job["status"] == "error":
        out["Ошибка"] = job["error"]
    return out


@app.post("/api/v1/checks", dependencies=[Depends(check_token)])
async def create_check(req: CheckRequest):
    inn = req.inn.strip()
    kpp = (req.kpp or "").strip() or None
    if not service.validate_inn(inn):
        raise HTTPException(422, f"Некорректный ИНН: {inn}")
    if kpp and not (len(kpp) == 9 and kpp.isalnum()):
        raise HTTPException(422, f"Некорректный КПП: {kpp}")

    job = None if req.force else store.find_recent(inn, kpp, settings.cache_hours)
    if job is None:
        cid = store.create(inn, kpp, {"ai": req.ai, "context": req.context})
        service.enqueue(cid)
    else:
        cid = job["id"]

    deadline = asyncio.get_running_loop().time() + req.wait
    while True:
        job = store.get(cid)
        if job["status"] in ("done", "error") or asyncio.get_running_loop().time() >= deadline:
            return render(job)
        await asyncio.sleep(2)


@app.get("/api/v1/checks", dependencies=[Depends(check_token)])
async def list_checks(q: str = "", limit: int = Query(default=50, le=500)):
    out = []
    for job in store.list_recent(q.strip(), limit):
        r = job["result"] or {}
        out.append({"id": job["id"], "Статус": job["status"], "Этап": job["stage"] or "",
                    "ИНН": job["inn"], "КПП": job["kpp"] or "", "Создано": job["created_at"],
                    "Контрагент": r.get("Контрагент", ""), "Итог": r.get("Итог", ""),
                    "Ошибка": job["error"] or ""})
    return out


@app.get("/api/v1/checks/{cid}", dependencies=[Depends(check_token)])
async def get_check(cid: str):
    job = store.get(cid)
    if not job:
        raise HTTPException(404, "Проверка не найдена")
    return render(job)


@app.delete("/api/v1/checks/{cid}", dependencies=[Depends(check_token)])
async def delete_check(cid: str):
    """Удаляет проверку вместе со скачанными отчётами."""
    job = store.get(cid)
    if not job:
        raise HTTPException(404, "Проверка не найдена")
    if job["status"] in ("queued", "running"):
        raise HTTPException(409, "Проверка ещё выполняется — удалить можно после завершения")
    store.delete(cid)
    shutil.rmtree(settings.files_dir / cid, ignore_errors=True)
    return {"ok": True}


@app.get("/api/v1/checks/{cid}/files/{name}", dependencies=[Depends(check_token)])
async def get_file(cid: str, name: str):
    path = (settings.files_dir / cid / name).resolve()
    if not path.is_relative_to(settings.files_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path, media_type="application/pdf", filename=name)


# ---------- Настройки ИИ (веб-интерфейс) ----------

def settings_view() -> dict:
    mask = runtime_settings.mask
    return {
        "ai_provider": settings.ai_provider,
        "providers": available_providers(),
        "gigachat": {"key": mask(settings.gigachat_auth_key), "scope": settings.gigachat_scope,
                     "model": settings.gigachat_model},
        "anthropic": {"key": mask(settings.anthropic_api_key), "model": settings.anthropic_model},
        "routerai": {"key": mask(settings.routerai_api_key), "models": routerai_models()},
    }


class SettingsUpdate(BaseModel):
    ai_provider: str | None = None
    gigachat_auth_key: str | None = None
    gigachat_scope: str | None = None
    gigachat_model: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    routerai_api_key: str | None = None
    routerai_models: list[str] | None = None


@app.get("/api/v1/settings", dependencies=[Depends(check_token)])
async def get_settings():
    return settings_view()


@app.put("/api/v1/settings", dependencies=[Depends(check_token)])
async def update_settings(upd: SettingsUpdate):
    """Поле не передано — не меняется; пустая строка у ключа — ключ удаляется."""
    data = upd.model_dump(exclude_none=True)
    if "routerai_models" in data:
        data["routerai_models"] = ",".join(dict.fromkeys(m.strip() for m in data["routerai_models"] if m.strip()))
    for k in runtime_settings.SECRETS & data.keys():
        data[k] = data[k].strip()
    runtime_settings.save(data)
    ids = {p["id"] for p in available_providers()}
    if settings.ai_provider not in ("auto", *ids):  # выбранная модель пропала — возвращаемся к автовыбору
        runtime_settings.save({"ai_provider": "auto"})
    return settings_view()


class TestRequest(BaseModel):
    provider: str


@app.post("/api/v1/settings/test", dependencies=[Depends(check_token)])
async def test_provider(req: TestRequest):
    """Короткий запрос к модели: проверяет ключ, доступ к модели и сеть."""
    started = time.monotonic()
    try:
        provider = get_provider(req.provider)
        res = await asyncio.wait_for(
            provider.analyze("Отвечай кратко.", "Ответь одним словом: готово", []), timeout=120)
        return {"ok": True, "answer": res.text.strip()[:200], "model": res.model,
                "seconds": round(time.monotonic() - started, 1)}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except httpx.ConnectError as e:
        hint = " — для GigaChat укажите сертификат Минцифры (GIGACHAT_CA_BUNDLE)" if "CERTIFICATE" in str(e).upper() else ""
        return {"ok": False, "error": f"Нет соединения: {e}{hint}"}
    except Exception as e:
        return {"ok": False, "error": str(e) or e.__class__.__name__}


@app.get("/api/v1/settings/routerai/catalog", dependencies=[Depends(check_token)])
async def routerai_catalog():
    return await routerai.catalog()


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True, "ai": available_providers(), "default": settings.ai_provider, "auth": bool(settings.api_token),
            "sources": {"rusprofile": settings.rusprofile_enabled, "globas": settings.globas_enabled}}
