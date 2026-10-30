from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # Адрес, на котором слушает сервис (run.py)
    host: str = "0.0.0.0"
    port: int = 8010
    # Префикс адреса за обратным прокси, например /observer/observer-main.
    # Запросы принимаются и с ним, и без него — неважно, срезает ли его прокси.
    root_path: str = ""

    # API для 1С
    api_token: str = ""  # если задан — 1С передаёт его в заголовке X-API-Key
    data_dir: Path = BASE_DIR / "data"
    cache_hours: int = 24  # повторный запрос по тому же ИНН/КПП в течение N часов отдаёт готовое заключение

    # Браузер
    headless: bool = True
    browser_timeout_ms: int = 60_000

    # Rusprofile
    rusprofile_enabled: bool = True
    rusprofile_login: str = ""
    rusprofile_password: str = ""

    # Глобас
    globas_enabled: bool = True
    globas_url: str = "https://globas.credinform.ru"
    globas_login: str = ""
    globas_password: str = ""
    # Шаблон страницы поиска внутри системы; {inn} подставляется
    globas_search_path: str = "/search/rezultaty-poiska?query={inn}"
    # Необязательно: селекторы Playwright через «;», которые нужно нажать на карточке компании,
    # чтобы получить PDF (последний клик запускает скачивание). Пусто — автоматический поиск кнопки.
    globas_export_steps: str = ""

    # ИИ: gigachat | anthropic | auto (первый настроенный)
    ai_provider: str = "auto"

    gigachat_auth_key: str = ""  # «Ключ авторизации» из личного кабинета (Base64 client_id:secret)
    gigachat_scope: str = "GIGACHAT_API_CORP"  # GIGACHAT_API_PERS / GIGACHAT_API_B2B / GIGACHAT_API_CORP
    gigachat_model: str = "GigaChat-2-Max"
    gigachat_ca_bundle: str = ""  # путь к сертификату НУЦ Минцифры (russian_trusted_root_ca.cer)
    gigachat_verify_ssl: bool = True
    gigachat_send_files: bool = False  # True — грузить PDF в /files; False — передавать извлечённый текст

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    # RouterAI (OpenAI-совместимый агрегатор, оплата в рублях); модели — через запятую
    routerai_api_key: str = ""
    routerai_base_url: str = "https://routerai.ru/api/v1"
    routerai_models: str = "qwen/qwen3.8-27b,deepseek/deepseek-v4-pro-0813"

    ai_temperature: float = 0.2

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def browser_dir(self) -> Path:
        return self.data_dir / "browser"

    @property
    def debug_dir(self) -> Path:
        return self.data_dir / "debug"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "checks.sqlite"


settings = Settings()
for d in (settings.files_dir, settings.browser_dir, settings.debug_dir):
    d.mkdir(parents=True, exist_ok=True)
