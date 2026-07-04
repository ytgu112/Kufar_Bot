# Kufar Telegram Bot

Telegram-бот для отслеживания объявлений на Kufar.by. Фильтры создаются и управляются через Telegram Mini App. Бот периодически проверяет новые объявления и отправляет их в чат без дублей.

## Архитектура

- **Bot** — aiogram-сервер с командами для навигации и регистрации.
- **Mini App** — веб-интерфейс внутри Telegram для управления фильтрами (создание, редактирование, удаление, пауза).
- **Parser** — парсер Kufar.by с `APScheduler`, проверяет объявления по каждому активному фильтру.
- **DB** — SQLite (SQLAlchemy + alembic).

## Команды бота

| Команда | Действие |
|---------|----------|
| `/start` | Регистрация пользователя |
| `/my_filters` | Список фильтров (если Mini App недоступен) |
| `/miniapp` | Открыть Mini App |

## Mini App

Telegram Mini App — основной интерфейс управления фильтрами. Позволяет:

- просматривать список фильтров с индикацией статуса;
- создавать фильтр с выбором категории, типа сделки, города, количества комнат и цены;
- редактировать существующий фильтр;
- приостанавливать / возобновлять фильтр;
- удалять фильтр.

### Доступные категории

- квартиры: аренда и покупка;
- дома: покупка.

## Настройка

Создайте файл `.env` в корне проекта (образец — `.env.example`):

```text
BOT_TOKEN=telegram_bot_token_from_botfather
DB_PATH=data/kufar_bot.sqlite3
POLL_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
MAX_ADS_PER_POLL=5
REQUEST_PAUSE_SECONDS=1.5
FRESH_AD_GRACE_SECONDS=30
WEBAPP_HOST=0.0.0.0
WEBAPP_PORT=8080
WEBAPP_URL=https://your-domain.example/miniapp
```

## Запуск

### Docker

```bash
docker-compose up -d --build
```

### Локально

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

### Проверка парсера

```powershell
.\.venv\Scripts\python scripts\test_parser.py
```
