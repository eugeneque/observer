from ..config import settings
from .base import AIProvider, AIResult


def routerai_models() -> list[str]:
    return [m.strip() for m in settings.routerai_models.split(",") if m.strip()]


def available_providers() -> list[dict]:
    """Настроенные ИИ: id передаётся в запросе (поле «ИИ»), name — для интерфейса."""
    out = []
    if settings.gigachat_auth_key:
        out.append({"id": "gigachat", "name": f"GigaChat ({settings.gigachat_model})"})
    if settings.anthropic_api_key:
        out.append({"id": "anthropic", "name": f"Claude ({settings.anthropic_model})"})
    if settings.routerai_api_key:
        from .routerai import pretty_name
        for m in routerai_models():
            out.append({"id": f"routerai:{m}", "name": f"{pretty_name(m)} · RouterAI"})
    return out


def get_provider(name: str | None = None) -> AIProvider:
    name = (name or settings.ai_provider or "auto").strip()
    if name.lower() == "auto":
        configured = available_providers()
        if not configured:
            raise RuntimeError("Не подключена ни одна модель ИИ — введите ключ в «Настройки ИИ» "
                               "(или GIGACHAT_AUTH_KEY / ANTHROPIC_API_KEY / ROUTERAI_API_KEY в .env)")
        name = configured[0]["id"]
    if name.lower() == "claude":
        name = "anthropic"
    if name.lower() == "routerai":  # без модели — первая из ROUTERAI_MODELS
        name = f"routerai:{routerai_models()[0]}"
    if name not in _instances:  # экземпляр живёт долго — GigaChat переиспользует токен
        if name == "gigachat":
            from .gigachat import GigaChatProvider
            _instances[name] = GigaChatProvider()
        elif name == "anthropic":
            from .anthropic_ai import AnthropicProvider
            _instances[name] = AnthropicProvider()
        elif name.startswith("routerai:"):
            if not settings.routerai_api_key:
                raise RuntimeError("Не задан ROUTERAI_API_KEY в .env")
            from .routerai import RouterAIProvider
            _instances[name] = RouterAIProvider(name.split(":", 1)[1])
        else:
            raise ValueError(f"Неизвестный ИИ-провайдер: {name}")
    return _instances[name]


_instances: dict[str, AIProvider] = {}

__all__ = ["AIProvider", "AIResult", "get_provider", "available_providers"]
