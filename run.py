"""Запуск сервиса на Windows, macOS и Linux:  python run.py [--open]

Почему не просто `uvicorn ... --reload`: на Windows в режиме --reload uvicorn использует
SelectorEventLoop, в котором Playwright не может запустить браузер. Здесь сервер работает
в стандартном цикле событий (ProactorEventLoop на Windows)."""
import argparse
import asyncio
import threading
import webbrowser

import uvicorn

from app.config import settings


def main() -> None:
    ap = argparse.ArgumentParser(description="Сервис проверки контрагентов")
    ap.add_argument("--host", default=settings.host)
    ap.add_argument("--port", type=int, default=settings.port)
    ap.add_argument("--open", action="store_true", help="открыть интерфейс в браузере после запуска")
    args = ap.parse_args()

    url = f"http://localhost:{args.port}/"
    print(f"Сервис проверки контрагентов: {url}  (остановить — Ctrl+C)")
    if args.open:
        threading.Timer(2.0, webbrowser.open, (url,)).start()

    server = uvicorn.Server(uvicorn.Config("app.main:app", host=args.host, port=args.port, log_level="info"))
    asyncio.run(server.serve())  # на Windows asyncio.run создаёт ProactorEventLoop — он нужен Playwright


if __name__ == "__main__":
    main()
