"""Claude (Anthropic API): PDF передаются как есть — модель видит и текст, и таблицы."""
import base64
from pathlib import Path

import httpx

from ..config import settings
from .base import AIProvider, AIResult

API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicProvider(AIProvider):
    name = "Claude"

    def __init__(self):
        self.model = settings.anthropic_model

    async def analyze(self, system: str, user: str, files: list[Path]) -> AIResult:
        content = [
            {
                "type": "document",
                "title": f.name,
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(f.read_bytes()).decode()},
            }
            for f in files
        ]
        content.append({"type": "text", "text": user})
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                API_URL,
                headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                json={"model": self.model, "max_tokens": 4000, "system": system,
                      "messages": [{"role": "user", "content": content}]},
            )
            r.raise_for_status()
            data = r.json()
        text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
        return AIResult(text=text, ai_name=self.name, model=data.get("model", self.model))
