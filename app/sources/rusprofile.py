"""Rusprofile: HTML не парсим. Карточку находим через JSON-поиск сайта,
а отчёт получаем кнопкой «Скачать PDF» (как пользователь)."""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from ..browser import browser_context, debug_dump
from ..config import settings
from . import SourceError, SourceLoginRequired
from .common import click_and_capture_pdf, is_pdf

log = logging.getLogger(__name__)
BASE = "https://www.rusprofile.ru"
PDF_BUTTON = 'a[data-track-click*="pdf_report"]'


@dataclass
class Company:
    name: str
    ogrn: str
    link: str


async def find_company(page: Page, inn: str) -> Company:
    resp = await page.request.get(
        f"{BASE}/ajax.php", params={"query": inn, "action": "search"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    if not resp.ok:
        raise SourceError(f"Rusprofile: поиск вернул HTTP {resp.status}")
    data = await resp.json()
    candidates = (data.get("ul") or []) + (data.get("ip") or [])
    for c in candidates:
        if re.sub(r"\D", "", str(c.get("inn", ""))) == inn:
            return Company(name=c.get("raw_name") or c.get("name", ""), ogrn=c.get("raw_ogrn") or c.get("ogrn", ""),
                           link=c["link"])
    raise SourceError(f"Rusprofile: организация с ИНН {inn} не найдена")


async def is_logged_in(page: Page) -> bool:
    return bool(await page.evaluate("() => !!(window.RPF && RPF.store && RPF.store.user && RPF.store.user.id)"))


async def login(page: Page) -> None:
    if not (settings.rusprofile_login and settings.rusprofile_password):
        raise SourceLoginRequired("Rusprofile: не заданы RUSPROFILE_LOGIN / RUSPROFILE_PASSWORD")
    try:
        await page.locator("span.btn-text", has_text="Войти").first.click()
        email = page.locator("input[type=email]:visible").first
        await email.fill(settings.rusprofile_login)
        await page.get_by_role("button", name="Продолжить").first.click()
        pwd = page.locator("input[type=password]:visible").first
        await pwd.wait_for(timeout=15_000)
        await pwd.fill(settings.rusprofile_password)
        await pwd.press("Enter")
        await page.wait_for_function(
            "() => !!(window.RPF && RPF.store && RPF.store.user && RPF.store.user.id)", timeout=20_000)
    except Exception:
        # Страница могла перезагрузиться после входа — проверяем ещё раз
        await page.reload(wait_until="domcontentloaded")
        if await is_logged_in(page):
            return
        dump = await debug_dump(page, "rusprofile_login")
        raise SourceLoginRequired(
            "Rusprofile: автоматический вход не удался (возможно, код из письма или капча). "
            f"Выполните один раз: python -m scripts.login rusprofile. Отладка: {dump}")


async def fetch(inn: str, kpp: str | None, out_dir: Path) -> tuple[Path, Company]:
    async with browser_context("rusprofile") as ctx:
        return await _fetch(ctx, inn, out_dir)


async def _fetch(ctx: BrowserContext, inn: str, out_dir: Path) -> tuple[Path, Company]:
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(BASE, wait_until="domcontentloaded")
    company = await find_company(page, inn)
    await page.goto(BASE + company.link, wait_until="domcontentloaded")
    if not await is_logged_in(page):
        await login(page)
        await page.goto(BASE + company.link, wait_until="domcontentloaded")

    out = out_dir / f"Rusprofile_{inn}.pdf"
    button = page.locator(PDF_BUTTON).first
    try:
        result = await click_and_capture_pdf(ctx, page, button, out, timeout_ms=90_000)
    except Exception as e:
        log.warning("Rusprofile: кнопка PDF не сработала: %s", e)
        result = None
    if result and is_pdf(result):
        return result, company

    dump = await debug_dump(page, "rusprofile_pdf")
    if await page.locator(".prohibition, [class*=prohibition]:visible").count():
        raise SourceError(f"Rusprofile: нет доступа к PDF-отчёту на текущем тарифе. Отладка: {dump}")
    # Запасной вариант: печатаем саму карточку — для ИИ этого достаточно
    log.warning("Rusprofile: PDF не скачан, сохраняю карточку компании как PDF")
    await page.pdf(path=str(out), format="A4", print_background=True)
    return out, company
