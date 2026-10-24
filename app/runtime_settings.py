"""Настройки ИИ, которые меняются из веб-интерфейса. Хранятся в data/ai_settings.json
поверх .env и применяются сразу, без перезапуска сервиса."""
import json
import os

from .config import settings

EDITABLE = {
    "ai_provider", "gigachat_auth_key", "gigachat_scope", "gigachat_model",
    "anthropic_api_key", "anthropic_model", "routerai_api_key", "routerai_models",
}
SECRETS = {"gigachat_auth_key", "anthropic_api_key", "routerai_api_key"}
_path = settings.data_dir / "ai_settings.json"


def _apply(values: dict) -> None:
    for k, v in values.items():
        if k in EDITABLE:
            setattr(settings, k, v)


def load() -> None:
    if _path.exists():
        _apply(json.loads(_path.read_text(encoding="utf-8")))


def save(updates: dict) -> None:
    updates = {k: v for k, v in updates.items() if k in EDITABLE}
    stored = json.loads(_path.read_text(encoding="utf-8")) if _path.exists() else {}
    stored.update(updates)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)  # в файле ключи
    tmp.replace(_path)
    _apply(updates)
    from . import ai
    ai._instances.clear()  # провайдеры пересоздадутся с новыми ключами


def mask(secret: str) -> str:
    return f"•••• {secret[-4:]}" if len(secret) > 8 else ("••••" if secret else "")


load()
