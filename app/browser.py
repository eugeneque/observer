"""Общий Playwright: у каждого источника свой постоянный профиль браузера,
поэтому вход выполняется один раз, а дальше используются сохранённые cookies."""
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

if sys.platform == "win32":
    # Chromium лежит внутри .venv (его ставит install.bat) — так его видит и автозапуск под SYSTEM
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import settings

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@asynccontextmanager
async def browser_context(profile: str, headless: bool | None = None):
    async with async_playwright() as p:
        ctx: BrowserContext = await p.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_dir / profile),
            headless=settings.headless if headless is None else headless,
            accept_downloads=True,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 1000},
        )
        ctx.set_default_timeout(settings.browser_timeout_ms)
        try:
            yield ctx
        finally:
            await ctx.close()


async def debug_dump(page: Page, name: str) -> str:
    """Сохраняет скриншот и HTML страницы — чтобы быстро поправить селекторы, если сайт изменится."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = settings.debug_dir / f"{stamp}_{name}"
    try:
        await page.screenshot(path=f"{base}.png", full_page=True)
        (base.with_suffix(".html")).write_text(await page.content(), encoding="utf-8")
    except Exception as e:  # отладка не должна ронять задачу
        log.warning("debug_dump failed: %s", e)
    return str(base)
