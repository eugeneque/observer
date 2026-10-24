"""RouterAI: OpenAI-совместимый API ко многим моделям (Qwen, DeepSeek и др.).
Модели текстовые, поэтому PDF передаются извлечённым текстом."""
import re
import time
from pathlib import Path

import httpx

from ..config import settings
from .base import AIProvider, AIResult, files_as_text

VENDORS = {"qwen": "Qwen", "deepseek": "DeepSeek", "meta-llama": "Llama", "mistralai": "Mistral",
           "google": "Gemini", "openai": "OpenAI", "anthropic": "Claude", "yandex": "YandexGPT", "sber": "GigaChat"}


_catalog: dict = {"at": 0.0, "items": []}


def display_name(model: str) -> str:
    vendor = model.split("/", 1)[0]
    return VENDORS.get(vendor, vendor.capitalize())


def pretty_name(model: str) -> str:
    """«Qwen3.8 27B» из каталога RouterAI, иначе идентификатор."""
    for m in _catalog["items"]:
        if m["id"] == model:
            return m["name"].split(": ", 1)[-1]
    return model.split("/", 1)[-1]


async def catalog() -> list[dict]:
    """Каталог моделей RouterAI: цена за 1 млн токенов и оценка цены одной проверки
    (~25 тыс. токенов отчётов на входе и ~3 тыс. на выходе). Кэшируется на час."""
    if time.time() - _catalog["at"] < 3600 and _catalog["items"]:
        return _catalog["items"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(settings.routerai_base_url.rstrip("/") + "/models")
            r.raise_for_status()
            data = r.json().get("data", [])
    except Exception:
        return _catalog["items"]
    items = []
    for m in data:
        arch = m.get("architecture") or {}
        if "text" not in (arch.get("output_modalities") or ["text"]) or (m.get("context_length") or 0) < 64_000:
            continue  # нужен текстовый ответ и контекст, в который влезают отчёты
        pr = m.get("pricing") or {}
        try:
            p_in, p_out = float(pr.get("prompt", 0)), float(pr.get("completion", 0))
        except (TypeError, ValueError):
            continue
        items.append({"id": m["id"], "name": m.get("name") or m["id"], "context": m.get("context_length"),
                      "in_1m": round(p_in * 1e6, 2), "out_1m": round(p_out * 1e6, 2),
                      "per_check": round(p_in * 25_000 + p_out * 3_000, 2)})
    items.sort(key=lambda x: x["name"].lower())
    _catalog.update(at=time.time(), items=items)
    return items


class RouterAIProvider(AIProvider):
    def __init__(self, model: str):
        self.model = model
        self.name = f"{display_name(model)} (RouterAI)"

    async def analyze(self, system: str, user: str, files: list[Path]) -> AIResult:
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(
                settings.routerai_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.routerai_api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"{user}\n\nСодержимое файлов:\n{files_as_text(files)}"},
                    ],
                    "temperature": settings.ai_temperature,
                    "max_tokens": 16000,  # с запасом: модели с рассуждениями тратят часть на «мышление»
                },
            )
            if r.status_code >= 400:
                hint = {401: "ключ не принят — проверьте его", 402: "недостаточно средств на балансе",
                        403: "доступ к модели запрещён", 404: "модель не найдена в каталоге",
                        429: "превышен лимит запросов, повторите позже"}.get(r.status_code, r.text[:300])
                raise RuntimeError(f"RouterAI ({r.status_code}): {hint}")
            data = r.json()
        text = data["choices"][0]["message"].get("content") or ""
        text = re.sub(r"(?s)<think>.*?</think>", "", text).strip()  # если рассуждения пришли в тексте
        if not text:
            raise RuntimeError("RouterAI вернул пустой ответ (возможно, не хватило max_tokens на рассуждения)")
        return AIResult(text=text, ai_name=self.name, model=data.get("model") or self.model)
