"""Глобас (Крединформ): вход, поиск по ИНН, выгрузка отчёта по компании в PDF."""
import logging
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from ..browser import browser_context, debug_dump
from ..config import settings
from . import SourceError, SourceLoginRequired
from .common import click_and_capture_pdf, is_pdf

log = logging.getLogger(__name__)

# Тексты кнопок выгрузки, которые пробуем по очереди, если GLOBAS_EXPORT_STEPS не задан
EXPORT_TEXTS = ["Выгрузка", "Выгрузить", "Скачать отчёт", "Скачать отчет", "Экспорт", "Отчёт", "Отчет", "PDF"]
CONFIRM_TEXTS = ["PDF", "Скачать", "Сформировать", "Выгрузить"]


def _url(path: str) -> str:
    return settings.globas_url.rstrip("/") + path


async def ensure_login(page: Page) -> None:
    await page.goto(_url("/ru-RU/Home/Login"), wait_until="domcontentloaded")
    form = page.locator("#LoginName")
    if not await form.is_visible():
        return  # уже авторизованы — система увела со страницы входа
    if not (settings.globas_login and settings.globas_password):
        raise SourceLoginRequired("Глобас: не заданы GLOBAS_LOGIN / GLOBAS_PASSWORD")
    await form.fill(settings.globas_login)
    await page.locator("#Password").fill(settings.globas_password)
    await page.locator("form[action*='Auth'] button[type=submit]").click()
    try:
        await page.wait_for_url(lambda u: "/Login" not in u, timeout=30_000)
    except Exception:
        dump = await debug_dump(page, "globas_login")
        raise SourceLoginRequired(
            "Глобас: вход не выполнен (проверьте логин/пароль или войдите вручную: "
            f"python -m scripts.login globas). Отладка: {dump}")


async def open_company(page: Page, inn: str) -> None:
    await page.goto(_url(settings.globas_search_path.format(inn=inn)), wait_until="networkidle")
    # Ищем ссылку внутри блока результата, в тексте которого есть ИНН
    href = await page.evaluate(
        """(inn) => {
            for (const a of document.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href');
                if (!h || h.startsWith('#') || /search|poisk/i.test(h)) continue;
                let el = a;
                for (let i = 0; i < 5 && el; i++, el = el.parentElement) {
                    if ((el.innerText || '').includes(inn)) return a.href;
                }
            }
            return null;
        }""", inn)
    if not href:
        dump = await debug_dump(page, "globas_search")
        raise SourceError(f"Глобас: компания с ИНН {inn} не найдена в результатах поиска. Отладка: {dump}")
    await page.goto(href, wait_until="networkidle")


async def export_pdf(ctx: BrowserContext, page: Page, out: Path) -> Path:
    steps = [s.strip() for s in settings.globas_export_steps.split(";") if s.strip()]
    if steps:
        for sel in steps[:-1]:
            await page.locator(sel).first.click()
            await page.wait_for_timeout(800)
        result = await click_and_capture_pdf(ctx, page, page.locator(steps[-1]).first, out)
        if result and is_pdf(result):
            return result
    else:
        for text in EXPORT_TEXTS:
            btn = page.get_by_role("button", name=text).or_(page.get_by_role("link", name=text)).first
            if not await btn.count() or not await btn.is_visible():
                continue
            result = await click_and_capture_pdf(ctx, page, btn, out, timeout_ms=10_000)
            if result and is_pdf(result):
                return result
            # Кнопка могла открыть диалог выбора формата/разделов
            for confirm in CONFIRM_TEXTS:
                c = page.get_by_role("button", name=confirm).or_(page.get_by_text(confirm, exact=True)).last
                if await c.count() and await c.is_visible():
                    result = await click_and_capture_pdf(ctx, page, c, out, timeout_ms=180_000)
                    if result and is_pdf(result):
                        return result
    dump = await debug_dump(page, "globas_export")
    raise SourceError(
        "Глобас: не удалось скачать PDF. Укажите последовательность кликов в GLOBAS_EXPORT_STEPS "
        f"(см. README). Отладка: {dump}")


async def fetch(inn: str, kpp: str | None, out_dir: Path) -> Path:
    async with browser_context("globas") as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await ensure_login(page)
        await open_company(page, inn)
        if kpp and kpp not in (await page.inner_text("body")):
            log.warning("Глобас: КПП %s не найден на карточке ИНН %s", kpp, inn)
        return await export_pdf(ctx, page, out_dir / f"Globas_{inn}.pdf")
