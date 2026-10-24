"""GigaChat API (Сбер): OAuth-токен на 30 минут, файлы через /files или текстом в промте."""
import time
import uuid
from pathlib import Path

import httpx

from ..config import settings
from .base import AIProvider, AIResult, files_as_text

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1"


class GigaChatProvider(AIProvider):
    name = "GigaChat"

    def __init__(self):
        self.model = settings.gigachat_model
        self._token: str | None = None
        self._expires_at = 0.0

    def _verify(self):
        return settings.gigachat_ca_bundle or settings.gigachat_verify_ssl

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        r = await client.post(
            OAUTH_URL,
            headers={"Authorization": f"Basic {settings.gigachat_auth_key}", "RqUID": str(uuid.uuid4()),
                     "Accept": "application/json"},
            data={"scope": settings.gigachat_scope},
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._expires_at = data["expires_at"] / 1000
        return self._token

    async def analyze(self, system: str, user: str, files: list[Path]) -> AIResult:
        async with httpx.AsyncClient(verify=self._verify(), timeout=300) as client:
            headers = {"Authorization": f"Bearer {await self._get_token(client)}"}
            user_msg: dict = {"role": "user"}
            if settings.gigachat_send_files:
                ids = []
                for f in files:
                    r = await client.post(f"{API_URL}/files", headers=headers,
                                          files={"file": (f.name, f.read_bytes(), "application/pdf")},
                                          data={"purpose": "general"})
                    r.raise_for_status()
                    ids.append(r.json()["id"])
                user_msg.update(content=user, attachments=ids)
            else:
                user_msg["content"] = f"{user}\n\nСодержимое файлов:\n{files_as_text(files)}"
            r = await client.post(f"{API_URL}/chat/completions", headers=headers, json={
                "model": self.model,
                "messages": [{"role": "system", "content": system}, user_msg],
                "temperature": settings.ai_temperature,
            })
            r.raise_for_status()
            data = r.json()
        return AIResult(text=data["choices"][0]["message"]["content"], ai_name=self.name,
                        model=data.get("model", self.model))
