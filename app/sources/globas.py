"""Глобас (Крединформ): вход, поиск по ИНН, выгрузка отчёта по компании в PDF."""
import logging
import re
from pathlib import Path

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..browser import browser_context, debug_dump
from ..config import settings
from . import SourceError, SourceLoginRequired
from .common import click_and_capture_pdf, is_pdf

log = logging.getLogger(__name__)

# Тексты кнопок выгрузки, которые пробуем по очереди, если GLOBAS_EXPORT_STEPS не задан
EXPORT_TEXTS = ["Выгрузка", "Выгрузить", "Скачать отчёт", "Скачать отчет", "Экспорт", "Отчёт", "Отчет", "PDF"]
CONFIRM_TEXTS = ["PDF", "Скачать", "Сформировать", "Выгрузить"]
# Глобас пускает одного пользователя за раз. Если логин уже занят, на странице входа
# появляется кнопка принудительного разрыва чужой сессии — нажимаем её (монопольный доступ).
KICK_PATTERN = re.compile(
    r"(завершить|разорвать|закрыть|прервать|сбросить).{0,30}(сесси|сеанс)|войти\s+и\s+завершить",
    re.I)
KICK_CONFIRM_TEXTS = ["Да", "Подтвердить", "Продолжить", "Завершить", "OK", "ОК"]
# Боковая панель «Выгрузка разделов справки»
PANEL_SELECTOR = ".aside-modal .export-company-details-modal-header"
PUBLIC_SITE_MARKER ="a.main-nav__btn[href*='/Home/Login'], a.main-nav__login[href*='/Home/Login']"


def _url(path: str) -> str:
    return settings.globas_url.rstrip("/") + path


async def _kick_other_sessions(page: Page) -> bool:
    """Ищет на странице входа кнопку «завершить другие сессии» и нажимает её."""
    candidates = (
        page.get_by_role("button", name=KICK_PATTERN)
        .or_(page.get_by_role("link", name=KICK_PATTERN))
        .or_(page.locator("input[type=submit],input[type=button]").filter(has_text=KICK_PATTERN))
    )
    for i in range(await candidates.count()):
        el = candidates.nth(i)
        if not await el.is_visible():
            continue
        log.warning("Глобас: логин занят, разрываю чужую сессию: %r", (await el.inner_text() or "").strip()[:80])
        await el.click()
        await page.wait_for_timeout(1000)
        # Возможен диалог подтверждения
        for text in KICK_CONFIRM_TEXTS:
            c = page.locator("dialog,[role=dialog],.modal").get_by_role("button", name=text, exact=True)
            if await c.count() and await c.first.is_visible():
                await c.first.click()
                break
        return True
    return False


async def _fill_checked(page: Page, selector: str, value: str) -> None:
    """Заполняет поле и убеждается, что значение не стёр скрипт формы."""
    field = page.locator(selector)
    for _ in range(5):
        await field.fill(value)
        await page.wait_for_timeout(300)
        if await field.input_value() == value:
            return
    # Последняя попытка — посимвольный ввод, как у живого пользователя
    await field.fill("")
    await field.press_sequentially(value, delay=30)


async def _submit_login(page: Page) -> bool:
    # Скрипт формы при инициализации сбрасывает поля — заполнять можно только после неё
    try:
        await page.locator("form[data-view=Login][data-login-form-initialized]").wait_for(
            state="attached", timeout=15_000)
    except PlaywrightTimeoutError:
        log.warning("Глобас: форма входа не отметилась как инициализированная, заполняю как есть")
    await _fill_checked(page, "#LoginName", settings.globas_login)
    await _fill_checked(page, "#Password", settings.globas_password)
    # Если на форме есть опция «завершить другие сессии при входе» — включаем сразу
    opt = page.get_by_role("checkbox", name=KICK_PATTERN)
    if await opt.count() and await opt.first.is_visible():
        await opt.first.check()
    await page.locator("form[action*='Auth'] button[type=submit]").click()
    # Ждём либо ухода со страницы входа, либо экрана «Все доступные подключения уже используются»
    for _ in range(30):
        if await page.get_by_role("button", name=KICK_PATTERN).count():
            return False
        if "/Login" not in page.url:
            return True
        await page.wait_for_timeout(500)
    return False


async def _require_session(page: Page) -> None:
    """Шапка публичного сайта (ссылка «Вход») означает, что сессии нет, хотя вход «прошёл»."""
    if await page.locator(PUBLIC_SITE_MARKER).count():
        dump = await debug_dump(page, "globas_no_session")
        raise SourceLoginRequired(
            f"Глобас: вход не выполнен — открылся публичный сайт ({page.url}). Проверьте логин/пароль "
            f"или войдите вручную: python -m scripts.login globas. Отладка: {dump}")


async def ensure_login(page: Page) -> None:
    await page.goto(_url("/ru-RU/Home/Login"), wait_until="domcontentloaded")
    form = page.locator("#LoginName")
    try:
        # Форма может появиться не сразу: нельзя считать её отсутствие признаком входа
        await form.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        return  # уже авторизованы — система увела со страницы входа (проверит _require_session)
    if not (settings.globas_login and settings.globas_password):
        raise SourceLoginRequired("Глобас: не заданы GLOBAS_LOGIN / GLOBAS_PASSWORD")
    ok = await _submit_login(page)
    if not ok:
        # Не вошли — вероятно, логин занят другим пользователем: рвём его сессию и входим заново
        if await _kick_other_sessions(page):
            try:
                await page.wait_for_url(lambda u: "/Login" not in u, timeout=15_000)
                ok = True
            except Exception:
                if await page.locator("#LoginName").is_visible():
                    ok = await _submit_login(page)
    if not ok:
        dump = await debug_dump(page, "globas_login")
        raise SourceLoginRequired(
            "Глобас: вход не выполнен (проверьте логин/пароль или войдите вручную: "
            f"python -m scripts.login globas). Отладка: {dump}")


SEARCH_PATH = "/ru-RU/CompanySearch/Result?query={inn}&Country=RU"
# Старый адрес публичного поиска: из кабинета он уводит на публичный сайт. Он мог остаться в .env.
LEGACY_SEARCH_PATHS = {"/search/rezultaty-poiska?query={inn}"}

FIND_RESULT_JS = """(inn) => {
    // Ссылка на карточку компании, рядом с которой стоит «ИНН: <inn>». Путь без параметров —
    // сама компания (параметры searchId/companyId указывают на строку выдачи).
    // Выдача: <a class="entity-item__name">Название</a> в блоке .entity-item, ИНН — отдельной
    // строкой «ИНН: <strong>…</strong>» в том же блоке. ИНН руководителя/учредителя — внутри
    // ссылок на людей, их не учитываем, иначе 10-значный ИНН может «совпасть» с куском 12-значного.
    const norm = s => (s || '').replace(/\\s+/g, ' ');
    const re = new RegExp('ИНН: ?' + inn + '(?!\\\\d)');
    const ownText = el => {
        const c = el.cloneNode(true);
        c.querySelectorAll('a').forEach(x => x.remove());
        return norm(c.textContent);
    };
    const links = [...document.querySelectorAll('a[href*="/company/getcompany/" i]')];
    for (const a of links) {
        const box = a.closest('.entity-item, .entities-list__item, li, tr') || a.parentElement;
        if (re.test(norm(a.innerText)) || (box && re.test(ownText(box)))) {
            const u = new URL(a.href); u.search = ''; return u.href;
        }
    }
    return null;
}"""


async def _goto(page: Page, url: str) -> None:
    """Переход без ожидания networkidle: у Глобаса фоновые запросы не прекращаются,
    и networkidle может не наступить вовсе. Ждём DOM, затем коротко — затишья сети."""
    await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        pass


async def open_company(page: Page, inn: str) -> None:
    path = settings.globas_search_path.strip()
    if not path or path in LEGACY_SEARCH_PATHS:
        path = SEARCH_PATH
    await _goto(page, _url(path.format(inn=inn)))
    await _require_session(page)
    # Результаты подгружаются скриптом: ждём ссылку на карточку с подписью «ИНН: <inn>»
    href = None
    for _ in range(60):
        href = await page.evaluate(FIND_RESULT_JS, inn)
        if href or await page.get_by_text("Ничего не нашлось").count():
            break
        await page.wait_for_timeout(500)
    if not href:
        dump = await debug_dump(page, "globas_search")
        raise SourceError(f"Глобас: компания с ИНН {inn} не найдена в результатах поиска. Отладка: {dump}")
    await _goto(page, href)
    await _require_session(page)
    # Карточка дорисовывается скриптом: даём появиться кнопке «Выгрузка»
    try:
        await page.get_by_text("Выгрузка", exact=True).first.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeoutError:
        log.warning("Глобас: кнопка «Выгрузка» не появилась за 30 с на %s", page.url)


async def export_max_pdf(ctx: BrowserContext, page: Page, out: Path) -> Path | None:
    """Кнопка «Выгрузка» → панель «Выгрузка разделов справки» → «Выбрать все» → «Выгрузить»:
    максимальная выписка со всеми разделами и приложениями. None — если панель не найдена."""
    opener = (
        page.get_by_role("button", name="Выгрузка", exact=True)
        .or_(page.get_by_role("link", name="Выгрузка", exact=True))
        .or_(page.get_by_text("Выгрузка", exact=True))
    ).locator("visible=true").first
    panel = page.get_by_text("Выгрузка разделов справки").or_(
        page.locator(PANEL_SELECTOR)).locator("visible=true").first
    # Панель может быть уже открыта (Глобас запоминает её состояние): тогда она перекрывает
    # кнопку и клик по ней виснет. Открываем только если панели ещё нет.
    if not await panel.count():
        if not await opener.count():
            log.warning("Глобас: кнопка «Выгрузка» не найдена на %s", page.url)
            return None
        if await opener.get_attribute("aria-pressed") != "true":
            await opener.click(timeout=15_000)
        try:
            await panel.wait_for(timeout=10_000)
        except Exception:
            log.warning("Глобас: панель «Выгрузка разделов справки» не открылась на %s", page.url)
            return None
    manual = page.get_by_text("Выбрать вручную", exact=True)
    if await manual.count() and await manual.first.is_visible():
        await manual.first.click()
        await page.wait_for_timeout(500)
    # «Выбрать все» — отметка идемпотентна (check() не снимает уже стоящую галочку)
    select_all = page.get_by_role("checkbox", name="Выбрать все", exact=True)
    try:
        if await select_all.count():
            await select_all.first.check(force=True)
        else:
            await page.get_by_label("Выбрать все", exact=True).first.check(force=True)
    except Exception as e:
        log.warning("Глобас: не удалось отметить «Выбрать все»: %s", e)
    await page.wait_for_timeout(500)
    # Зелёная «Выгрузить» внизу панели (не «Экспресс-выгрузка» / «Экспресс-справка»)
    go = page.get_by_role("button", name="Выгрузить", exact=True).or_(
        page.get_by_text("Выгрузить", exact=True)).last
    result = await click_and_capture_pdf(ctx, page, go, out, timeout_ms=300_000)
    if result and is_pdf(result):
        return result
    log.warning("Глобас: после «Выгрузить» PDF не получен (%s)", "файл не PDF" if result else "нет файла за 5 минут")
    return None


async def export_pdf(ctx: BrowserContext, page: Page, out: Path) -> Path:
    if not settings.globas_export_steps.strip():
        try:
            result = await export_max_pdf(ctx, page, out)
            if result:
                return result
        except Exception as e:
            log.warning("Глобас: выгрузка максимальной выписки не сработала (%s), пробую запасной путь", e)
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
            try:
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
            except PlaywrightTimeoutError as e:
                log.warning("Глобас: кнопка «%s» не нажалась: %s", text, str(e).splitlines()[0])
    dump = await debug_dump(page, "globas_export")
    raise SourceError(
        "Глобас: не удалось скачать PDF. Укажите последовательность кликов в GLOBAS_EXPORT_STEPS "
        f"(см. README). Страница: {page.url}. Отладка: {dump}")


async def fetch(inn: str, kpp: str | None, out_dir: Path) -> Path:
    async with browser_context("globas") as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await ensure_login(page)
        await open_company(page, inn)
        if kpp and kpp not in (await page.inner_text("body")):
            log.warning("Глобас: КПП %s не найден на карточке ИНН %s", kpp, inn)
        return await export_pdf(ctx, page, out_dir / f"Globas_{inn}.pdf")
