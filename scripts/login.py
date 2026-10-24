"""Ручной вход в источник в видимом окне браузера. Cookies сохраняются в профиле сервиса,
после чего сервис работает без повторного входа (нужно, если сайт просит код из письма или капчу).

    python -m scripts.login rusprofile
    python -m scripts.login globas
"""
import asyncio
import sys

from app.browser import browser_context
from app.config import settings

URLS = {
    "rusprofile": "https://www.rusprofile.ru/",
    "globas": settings.globas_url.rstrip("/") + "/ru-RU/Home/Login",
}


async def main(source: str) -> None:
    async with browser_context(source, headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URLS[source])
        print(f"Войдите в {source} в открывшемся окне, затем нажмите Enter здесь.")
        await asyncio.get_running_loop().run_in_executor(None, input)
    print("Сессия сохранена.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in URLS:
        sys.exit(f"Использование: python -m scripts.login {{{'|'.join(URLS)}}}")
    asyncio.run(main(sys.argv[1]))
