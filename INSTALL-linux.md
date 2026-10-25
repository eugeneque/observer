# Установка на Linux-сервер

Инструкция для Ubuntu 22.04+/Debian 12+ и RHEL/AlmaLinux/Rocky 9. Для Windows — [INSTALL.md](INSTALL.md).
Время установки — около 10 минут.

---

## 1. Что понадобится

| | |
|---|---|
| Сервер | Linux с systemd, от 2 ядер и 4 ГБ памяти, 1 ГБ на диске |
| Доступ | SSH и пользователь с правами `sudo` |
| Интернет | github.com и api.github.com (обновления), rusprofile.ru, globas.credinform.ru, routerai.ru (и/или GigaChat, Claude), pypi.org и cdn.playwright.dev (откуда скачивается Chromium) |
| Учётки | логин и пароль Rusprofile, логин и пароль Глобаса |
| Ключ ИИ | хотя бы один: RouterAI, GigaChat или Claude |

Ставить из-под root не обязательно: обычный пользователь с `sudo` удобнее — служба будет работать от его имени.

---

## 2. Скопируйте сервис на сервер

```bash
sudo mkdir -p /opt/counterparty-checker && sudo chown $USER: /opt/counterparty-checker
```
```bash
git clone https://github.com/eugeneque/observer.git /opt/counterparty-checker && cd /opt/counterparty-checker
```

(Нет `git` — `sudo apt install git` или `sudo dnf install git`.)

Если сервер без доступа к GitHub — скопируйте архив (`scp counterparty-checker.zip пользователь@сервер:~`)
и распакуйте: `unzip ~/counterparty-checker.zip -d /opt/counterparty-checker`. Такую папку `linux/update.sh`
сам подключит к GitHub при первом обновлении, когда доступ появится.

---

## 3. Запустите установку

```bash
bash linux/install.sh
```

Скрипт сам:
- найдёт Python 3.11+ или поставит его из репозитория системы (спросит пароль sudo);
- создаст окружение `.venv`, поставит библиотеки и Chromium (~150 МБ);
- поставит системные библиотеки, без которых Chromium не запускается на сервере без экрана;
- создаст `.env` и **сгенерирует ключ доступа `API_TOKEN`** — запишите его, он выводится на экран;
- проверит, что Chromium запускается.

В конце должно появиться **«=== Готово ===»**.

> **Ubuntu 22.04**: в системе Python 3.10 — скрипт подскажет, как поставить 3.12 из `ppa:deadsnakes`.
>
> **Через прокси**: `export HTTPS_PROXY=http://адрес-прокси:порт` перед запуском. Для `sudo apt` прокси
> настраивается отдельно (`/etc/apt/apt.conf.d/`).
>
> **Системные пакеты ставит администратор**: `SKIP_SYSTEM_DEPS=1 bash linux/install.sh`.

---

## 4. Впишите логины

```bash
nano .env
```

```
RUSPROFILE_LOGIN=почта@компании.ru
RUSPROFILE_PASSWORD=пароль

GLOBAS_LOGIN=почта@компании.ru
GLOBAS_PASSWORD=пароль
```

`API_TOKEN` уже заполнен. Файл доступен только владельцу (`chmod 600`) — не копируйте его в общие места.

---

## 5. Проверочный запуск

```bash
bash linux/run.sh
```

Откройте в браузере `http://<IP-сервера>:8010/`, введите ключ `API_TOKEN`, затем **«Настройки ИИ»** →
вставьте ключ RouterAI/GigaChat/Claude → выберите модель → «Проверить». Сделайте пробную проверку по ИНН.
Остановить — Ctrl+C.

---

## 6. Служба (автозапуск)

```bash
sudo bash linux/autostart-on.sh
```

Скрипт создаст службу systemd `counterparty-checker`, включит запуск при загрузке, откроет порт в
ufw/firewalld (если они включены) и дождётся ответа сервиса.

| Действие | Команда |
|---|---|
| Состояние | `sudo systemctl status counterparty-checker` |
| Перезапуск (после правки `.env`) | `sudo systemctl restart counterparty-checker` |
| Журнал | `bash linux/logs.sh` |
| Отключить | `sudo bash linux/autostart-off.sh` |

Служба работает от имени владельца папки. Отдельный пользователь: `sudo SERVICE_USER=checker bash linux/autostart-on.sh`
(пользователя создайте заранее: `sudo useradd -r -s /usr/sbin/nologin checker`).

Сменили `PORT` в `.env` — запустите `autostart-on.sh` ещё раз, он обновит службу и брандмауэр.

---

## 7. Ручной вход в Rusprofile/Глобас

Нужен, если сайт просит код из письма или капчу. На сервере нет экрана, поэтому один из вариантов:

1. **Пересылка окон по SSH**: на сервере `sudo apt install xauth`, подключитесь `ssh -X пользователь@сервер`
   (с Windows — через MobaXterm), затем:
   ```bash
   sudo systemctl stop counterparty-checker
   ```
   ```bash
   bash linux/login.sh rusprofile
   ```
   Войдите в открывшемся окне, нажмите Enter в консоли и запустите службу: `sudo systemctl start counterparty-checker`.
2. **Перенос профиля**: войдите на своём компьютере (`windows\login.bat rusprofile`), остановите службу на сервере
   и скопируйте папку `data\browser\rusprofile` в `/opt/counterparty-checker/data/browser/`, затем запустите службу.

---

## 8. Подключение 1С

Адрес: `http://<сервер>:8010`, заголовок `X-API-Key: <API_TOKEN>`. Проверка доступности с сервера 1С —
`http://<сервер>:8010/health`. Методы и код для 1С — в [README.md](README.md), раздел «Пример для 1С».

---

## 9. Обновление

Новые версии берутся из GitHub (ветка `main`):

```bash
bash linux/update.sh
```

Скрипт:
- скачивает последнюю версию и ставит её, **только если на ней прошли проверки CI** на GitHub;
- **не трогает настройки**: `.env`, ключи ИИ из интерфейса (`data/ai_settings.json`), входы в Rusprofile/Глобас
  (`data/browser/`) и историю проверок — они не хранятся в git; перед обновлением копирует `.env`,
  настройки ИИ и базу в `data/backups/<дата>/` (хранятся 10 последних копий);
- обновляет библиотеки, если они изменились, и перезапускает службу;
- если служба не ответила за 30 секунд — **возвращает прежнюю версию**;
- сообщает о новых параметрах из `.env.example`, которых нет в вашем `.env` (до их заполнения действуют
  значения по умолчанию).

Правки кода прямо на сервере заменяются версией из GitHub — их копия сохраняется в
`data/backups/<дата>/local-changes.diff`. Обновить, даже если CI не пройден: `bash linux/update.sh --force`.

### Автообновление

```bash
sudo bash linux/autoupdate-on.sh
```

Таймер systemd раз в 15 минут проверяет GitHub и ставит новую версию сам. Пока идут проверки контрагентов,
обновление откладывается до следующего раза. Другой интервал — `sudo UPDATE_INTERVAL=1h bash linux/autoupdate-on.sh`.

| Действие | Команда |
|---|---|
| Журнал обновлений | `journalctl -u counterparty-checker-update -n 50` |
| Отключить | `sudo bash linux/autoupdate-off.sh` |

---

## 10. Если что-то не работает

| Признак | Что делать |
|---|---|
| «Chromium не запускается» | `sudo .venv/bin/python -m playwright install-deps chromium` (Ubuntu/Debian); на RHEL — поставить пакеты `nss atk at-spi2-atk libdrm libxkbcommon mesa-libgbm alsa-lib` |
| `ensurepip is not available` | `sudo apt install python3.X-venv` (X — версия Python), затем `rm -rf .venv` и снова `install.sh` |
| Страница не открывается из сети | `sudo ss -ltnp \| grep 8010` — слушает ли; открыт ли порт в брандмауэре/облачной группе безопасности |
| Служба перезапускается по кругу | `bash linux/logs.sh` — причина в последних строках |
| Ошибка входа на Rusprofile/Глобас | проверьте логин в `.env`, затем шаг 7 |
| GigaChat: ошибка сертификата | скачайте «Russian Trusted Root CA» с https://www.gosuslugi.ru/crt, укажите путь в `GIGACHAT_CA_BUNDLE` |

---

## 11. Удаление

```bash
sudo bash linux/autostart-off.sh
```
```bash
rm -rf /opt/counterparty-checker
```
