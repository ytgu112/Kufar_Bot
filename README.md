# Kufar Telegram Bot MVP

Telegram-бот отслеживает объявления Kufar.by по сохранённым фильтрам и отправляет новые карточки в чат без дублей.

## Возможности MVP

- `/start` — регистрация пользователя.
- `/new_filter` — пошаговое создание фильтра.
- `/my_filters` — список активных фильтров и удаление.
- Периодический опрос Kufar через `APScheduler`.
- SQLite-хранилище пользователей, фильтров и уже отправленных объявлений.

По умолчанию доступны категории недвижимости:

- квартиры: аренда и покупка;
- дома: покупка.

## Настройка

Перед запуском создайте файл `.env` в корне проекта (можете использовать `.env.example` как шаблон) и укажите актуальные данные:

```text
BOT_TOKEN=telegram_bot_token_from_botfather
DB_PATH=data/kufar_bot.sqlite3
POLL_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
MAX_ADS_PER_POLL=5
REQUEST_PAUSE_SECONDS=1.5
FRESH_AD_GRACE_SECONDS=30
```

## Запуск через Docker (рекомендуется)

Самый быстрый и надежный способ запустить бота — использовать Docker. Убедитесь, что у вас установлены Docker и Docker Compose.

```bash
docker-compose up -d --build
```

База данных и логи будут автоматически сохраняться в папках `data/` и `logs/` на вашем хосте (используются volume), поэтому они не пропадут при перезапуске или обновлении контейнера.

Для просмотра логов в реальном времени:
```bash
docker-compose logs -f bot
```

## Локальный запуск (без Docker)

Создайте виртуальное окружение и установите зависимости:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### Проверка парсера

Вы можете запустить скрипт, который делает тестовый запрос к Kufar и выводит результаты:
```powershell
.\.venv\Scripts\python scripts\test_parser.py
```

### Запуск бота

```powershell
.\.venv\Scripts\python main.py
```

Если `BOT_TOKEN` пустой, приложение завершится с понятной ошибкой.

> Бот отправляет только свежие объявления: текущая выдача при создании фильтра сразу помечается как просмотренная, а планировщик пропускает объявления старше окна `POLL_INTERVAL_SECONDS + FRESH_AD_GRACE_SECONDS`.

## Деплой на VPS (systemd)

Если вы не используете Docker и хотите настроить сервис вручную:

1. Скопируйте проект в `/opt/kufar_bot`.
2. Создайте venv и установите зависимости.
3. Заполните `/opt/kufar_bot/.env`.
4. Скопируйте `deploy/kufar-bot.service` в `/etc/systemd/system/kufar-bot.service`.
5. Скопируйте `deploy/logrotate.kufar-bot` в `/etc/logrotate.d/kufar-bot`.
6. Создайте каталог логов:

```bash
sudo mkdir -p /var/log/kufar-bot
sudo chown -R kufar-bot:kufar-bot /var/log/kufar-bot
```

7. Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kufar-bot
sudo systemctl status kufar-bot
```

Обновление кода при использовании systemd:

```bash
cd /opt/kufar_bot
git pull
./.venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart kufar-bot
```
