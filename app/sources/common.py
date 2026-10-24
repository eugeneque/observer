import asyncio
import logging
from pathlib import Path

from playwright.async_api import BrowserContext, Locator, Page

log = logging.getLogger(__name__)


async def click_and_capture_pdf(ctx: BrowserContext, page: Page, target: Locator, out: Path,
                                timeout_ms: int = 120_000) -> Path | None:
    """Нажимает кнопку и ловит результат в любом виде:
    скачивание файла, новая вкладка с PDF или новая вкладка с HTML «версии для печати»."""
    loop = asyncio.get_running_loop()
    got_download: asyncio.Future = loop.create_future()
    got_popup: asyncio.Future = loop.create_future()

    def on_download(d):
        if not got_download.done():
            got_download.set_result(d)

    def on_page(p):
        if not got_popup.done():
            got_popup.set_result(p)

    ctx.on("page", on_page)
    for p in ctx.pages:
        p.on("download", on_download)
    try:
        await target.click()
        done, _ = await asyncio.wait({got_download, got_popup}, timeout=timeout_ms / 1000,
                                     return_when=asyncio.FIRST_COMPLETED)
        if got_download in done:
            await got_download.result().save_as(out)
            return out
        if got_popup in done:
            popup: Page = got_popup.result()
            popup.on("download", on_download)
            # Вкладка может сама начать скачивание
            try:
                d = await asyncio.wait_for(asyncio.shield(got_download), timeout=15)
                await d.save_as(out)
                return out
            except asyncio.TimeoutError:
                pass
            await popup.wait_for_load_state("networkidle")
            resp = await popup.request.get(popup.url)
            if "pdf" in (resp.headers.get("content-type") or ""):
                out.write_bytes(await resp.body())
            else:
                await popup.pdf(path=str(out), format="A4", print_background=True)  # только headless
            await popup.close()
            return out
        return None
    finally:
        ctx.remove_listener("page", on_page)


def is_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False
