# Agent Guide: Kufar Telegram Bot MVP

Этот файл предназначен для AI-агентов и разработчиков, которые продолжают работу над проектом.

## Project Summary

Проект — Telegram-бот для мониторинга объявлений Kufar.by.

Бот позволяет пользователю создать фильтр поиска недвижимости, периодически опрашивает неофициальный Kufar API и отправляет новые объявления в Telegram без дублей.

MVP сейчас сфокусирован на недвижимости:

- квартиры: долгосрочная аренда и покупка;
- дома, агроусадьбы, коттеджи: покупка;
- один город на один фильтр;
- цена в USD;
- количество комнат как обязательный дополнительный параметр.

## Context7

Пользователь просил использовать Context7. В текущей сессии отдельный Context7 tool не был доступен.

Если в будущей среде Context7 доступен, используйте его перед изменениями, завязанными на актуальные API библиотек:

- `aiogram` 3.x;
- `httpx`;
- `SQLAlchemy` 2.x;
- `APScheduler`;
- `python-dotenv`.

Не меняйте версии библиотек и публичные API проекта только по памяти, если можно проверить документацию через Context7.

## Tech Stack

- Python 3.11+; локально проект проверялся на Python 3.14.
- `aiogram` 3.x — Telegram bot и FSM.
- `httpx` — async HTTP-клиент Kufar API.
- `SQLAlchemy` 2.x + SQLite — users, subscriptions, sent ads.
- `APScheduler` — периодический polling.
- `python-dotenv` — переменные окружения из `.env`.

Зависимости описаны в `requirements.txt`.

## Important Files

- `main.py` — точка входа, настройка Bot/Dispatcher, подключение router, старт scheduler.
- `config.py` — чтение `.env`.
- `bot/handlers.py` — команды Telegram и FSM создания фильтра.
- `bot/filter_config.py` — конфиг категорий, городов, типов сделки и сборка `query_params`.
- `parser/kufar_client.py` — Kufar API client, `search_ads()`, `build_image_url()`.
- `parser/scheduler.py` — job polling, форматирование карточек и отправка в Telegram.
- `db/models.py` — SQLAlchemy models.
- `db/crud.py` — операции с пользователями, подписками и отправленными объявлениями.
- `db/session.py` — engine/session factory и создание таблиц.
- `scripts/test_parser.py` — smoke test Kufar API.
- `docs/api_notes.md` — результаты ручной разведки Kufar API.
- `deploy/` — systemd unit и logrotate шаблон.
- `.env.example` — пример окружения.

## Runtime Configuration

`.env`:

```text
BOT_TOKEN=
DB_PATH=data/kufar_bot.sqlite3
POLL_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
MAX_ADS_PER_POLL=5
REQUEST_PAUSE_SECONDS=1.5
FRESH_AD_GRACE_SECONDS=30
```

`BOT_TOKEN` должен быть задан реальным токеном от BotFather перед запуском `main.py`.

## Local Setup

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\test_parser.py
.\.venv\Scripts\python main.py
```

Если sandbox блокирует сеть, `scripts/test_parser.py` может вернуть `ads_count=0` и залогировать сетевую ошибку. Это ожидаемое graceful-поведение клиента, но для реальной проверки нужен доступ к `api.kufar.by`.

## Data Model

`users`

- `id`
- `telegram_id`
- `created_at`

`subscriptions`

- `id`
- `user_id`
- `title`
- `query_params` как JSON-строка;
- `is_active`
- `created_at`

`sent_ads`

- `id`
- `subscription_id`
- `ad_id`
- `sent_at`
- unique constraint: `(subscription_id, ad_id)`

Дубли предотвращаются через `sent_ads`.

## Kufar API Notes

Проверенный endpoint:

```text
GET https://api.kufar.by/search-api/v2/search/rendered-paginated
```

Базовый пример:

```text
cat=1010
cur=USD
gtsy=country-belarus~province-minsk~locality-minsk
lang=ru
prc=r:0,450
rms=v.or:2
size=30
typ=let
```

Изображения для `media_storage=rms` собираются так:

```text
https://rms.kufar.by/v1/list_thumbs_2x/{images[].path}
```

Подробности и результаты разведки лежат в `docs/api_notes.md`.

Kufar API неофициальный. При изменении структуры ответа код должен логировать ошибку и продолжать работу, а не падать.

## Bot Commands

- `/start` — создать пользователя и показать команды.
- `/help` — краткая справка.
- `/new_filter` — FSM создания фильтра.
- `/my_filters` — активные фильтры пользователя и кнопки удаления.
- `/cancel` — отмена текущего FSM-действия.

FSM sequence:

```text
category -> deal_type -> city -> price_from -> price_to -> rooms -> confirm
```

На подтверждении `bot/filter_config.py` собирает `query_params`, пригодный для `search_ads()`.

## Extending Categories Or Cities

Менять сначала `bot/filter_config.py`.

Для новой категории нужно знать:

- Kufar `cat`;
- допустимые `typ`;
- query-параметры дополнительных фильтров;
- человекочитаемый label.

Для нового города нужен Kufar `gtsy`.

После изменения конфига:

```powershell
.\.venv\Scripts\python -m compileall .
.\.venv\Scripts\python scripts\test_parser.py
```

Если добавляется новый шаг FSM, изменяйте `bot/handlers.py` и добавляйте проверку сборки router:

```powershell
.\.venv\Scripts\python -c "from bot.handlers import build_router; from db.session import create_session_factory; sf=create_session_factory(':memory:'); router=build_router(sf); print('router ok')"
```

## Scheduler Behavior

`parser/scheduler.py`:

- берёт активные подписки;
- парсит `query_params`;
- вызывает `search_ads()`;
- идёт по объявлениям в обратном порядке, чтобы более старые из текущей пачки отправились раньше;
- отправляет только объявления с `list_time` свежее окна `POLL_INTERVAL_SECONDS + FRESH_AD_GRACE_SECONDS` и не старше `subscriptions.created_at`;
- проверяет `sent_ads`;
- отправляет фото или fallback text;
- пишет `ad_id` в `sent_ads` только после успешной отправки;
- делает паузу между подписками.

`MAX_ADS_PER_POLL` ограничивает количество новых объявлений за один проход по подписке.

При создании нового фильтра текущая выдача Kufar заранее записывается в `sent_ads`.
Это baseline: первая плановая проверка не должна отправлять уже существующие объявления.

## Verification Checklist

Перед завершением изменений выполните минимум:

```powershell
.\.venv\Scripts\python -m compileall .
.\.venv\Scripts\python scripts\test_parser.py
```

Для DB smoke test:

```powershell
.\.venv\Scripts\python -c "from db.session import create_session_factory; from db import crud; sf=create_session_factory(':memory:'); s=sf(); u=crud.create_user(s,123); sub=crud.add_subscription(s,123,'test',{'cat':'1010'}); assert crud.mark_ad_sent(s,sub.id,111); assert crud.deactivate_subscription(s,123,sub.id); print('db crud ok')"
```

Для запуска реального бота нужен заполненный `BOT_TOKEN`.

## Git And Workspace Notes

- `.env`, `.venv`, `data/`, `logs/`, `__pycache__/` игнорируются.
- В этой среде `git status` может требовать safe directory из-за sandbox ownership. Не меняйте глобальный git config без явной просьбы пользователя; можно использовать одноразово:

```powershell
git -c safe.directory=D:/kufar_bot status --short
```

## Common Pitfalls

- Не хранить токен бота в документации или коммитах.
- Не пытаться получать скрытый телефон продавца: это вне MVP.
- Не хардкодить новые категории в handler-логике; добавлять их через `bot/filter_config.py`.
- Не считать Kufar API стабильным: все parsing changes должны быть defensive.
- Не отправлять объявление как sent до успешной отправки в Telegram.
- Цена Kufar в ответе приходит в сотых: `35000` значит `350.00 USD`.

## Recent Architecture Changes (2026)

### Mini-App First Strategy
- **Bot role simplified**: Telegram bot теперь только доставляет уведомления об новых объявлениях. Все взаимодействия (создание/редактирование фильтров, управление подписками) перенесены в Mini App.
- **Удалены интерактивные кнопки**: FSM-диалоги создания фильтров в боте удалены. Команды `/new_filter`, `/my_filters` больше не используются для основного потока.
- **Команды бота**: 
  - `/start` — приветствие с кнопкой открытия Mini App
  - `/miniapp` — прямая ссылка на Mini App
  - `/help` — справка о том, как работает бот
- **Преимущество**: Более богатый UX для сложных форм, меньше зависимость от ограничений Telegram Bot API.

### Улучшения обработки данных
- **Цена и валюта**: Функция `_format_price()` теперь корректно связывает поле цены с валютой (`price_usd` → USD, `price_byn` → BYN), избегая ошибок когда цена в USD но валюта указана как BYN.
- **Изображения**: Добавлены fallback-механизмы для извлечения изображений из альтернативных полей (`primary_image`, `thumbnail`, `cover_photo`), если основное поле `images` отсутствует или имеет неожиданную структуру.

### Mini App: Редактирование фильтров
- **Автозаполнение**: При редактировании фильтра все поля预заполняются существующими данными из `normalized_params`.
- **Города**: Исправлена проблема маппинга — в форме хранится label города (для валидации и отображения), при отправке конвертируется обратно в key через `getSelectedCityKey()`.
- **UI карточек**: Убрано дублирование описания фильтра — теперь описание показывается только в заголовке карточки, в meta-секции осталась только дата создания.
- **Обработчики кликов**: Клик по карточке больше не открывает редактирование. Редактирование запускается только при явном нажатии кнопки "Редактировать". Это предотвращает случайные переходы.

### Стратегия хранения данных
- **SQLite с persistent volume**: Для деплоя в Railway рекомендуется использовать SQLite с подключенным volume (путь `/app/data/kufar_bot.sqlite3`). Это обеспечивает сохранность данных между деплоями без перехода на PostgreSQL.
- **PostgreSQL не требуется**: Код поддерживает только SQLite. Добавление поддержки PostgreSQL не планируется для MVP.

### Обновленный Checklist верификации
```powershell
# Проверка компиляции
.\.venv\Scripts\python -m compileall .

# Проверка импорта роутера
.\.venv\Scripts\python -c "from bot.handlers import build_router; from db.session import create_session_factory; sf=create_session_factory(':memory:'); router=build_router(sf, 'http://test'); print('router ok')"

# Проверка форматирования цены
.\.venv\Scripts\python -c "from parser.scheduler import _format_price; print(_format_price({'price_usd': 50000, 'currency': 'USD'})); print(_format_price({'price_byn': 10000, 'currency': 'BYN'}))"
```
