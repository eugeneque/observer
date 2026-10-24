class SourceError(Exception):
    """Не удалось получить отчёт из источника (текст уходит в предупреждения ответа)."""


class SourceLoginRequired(SourceError):
    """Автоматический вход не прошёл — нужен ручной вход: python -m scripts.login <источник>."""
