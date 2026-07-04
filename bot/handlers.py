from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from sqlalchemy.orm import Session, sessionmaker

from bot.filter_config import CATEGORIES, CITIES, DEAL_TYPES, ROOMS, build_query_params, describe_filter, get_allowed_deals
from db import crud
from parser.ad_utils import extract_ad_id
from parser.kufar_client import search_ads

logger = logging.getLogger(__name__)


class FilterWizard(StatesGroup):
    category = State()
    deal_type = State()
    city = State()
    price_from = State()
    price_to = State()
    rooms = State()
    confirm = State()


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=callback_data) for text, callback_data in row]
            for row in rows
        ]
    )


def _single_column_keyboard(items: list[tuple[str, str]], back_button: tuple[str, str] | None = ("🔙 В главное меню", "main_menu:show")) -> InlineKeyboardMarkup:
    rows = [[item] for item in items]
    if back_button:
        rows.append([back_button])
    return _keyboard(rows)

def _main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Главное меню")]],
        resize_keyboard=True,
    )

def _main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("➕ Создать фильтр", "main_menu:create")],
            [("📋 Мои фильтры", "main_menu:filters")],
            [("❓ Помощь", "main_menu:help")],
        ]
    )


def _miniapp_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть miniapp", web_app=WebAppInfo(url=webapp_url))],
        ]
    )


def _category_keyboard() -> InlineKeyboardMarkup:
    return _single_column_keyboard([(value["label"], f"cat:{key}") for key, value in CATEGORIES.items()])


def _deal_type_keyboard(category_key: str) -> InlineKeyboardMarkup:
    return _single_column_keyboard(
        [(DEAL_TYPES[key], f"deal:{key}") for key in get_allowed_deals(category_key)],
        back_button=("🔙 Назад", "back:category")
    )


def _city_keyboard() -> InlineKeyboardMarkup:
    return _single_column_keyboard(
        [(value["label"], f"city:{key}") for key, value in CITIES.items()],
        back_button=("🔙 Назад", "back:deal_type")
    )


def _rooms_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    current_row: list[tuple[str, str]] = []
    for key, label in ROOMS.items():
        current_row.append((label, f"rooms:{key}"))
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([("🔙 Назад", "back:price_to")])
    return _keyboard(rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [("Сохранить", "confirm:save")],
            [("Отмена", "confirm:cancel")],
            [("🔙 Назад", "back:rooms")],
        ]
    )


def _delete_filters_keyboard(subscriptions: list) -> InlineKeyboardMarkup:
    return _single_column_keyboard(
        [(f"Удалить #{index}", f"delete_filter:{subscription.id}") for index, subscription in enumerate(subscriptions, start=1)],
        back_button=("🔙 В главное меню", "main_menu:show")
    )


def _parse_optional_price(raw_text: str) -> int | None:
    normalized = raw_text.strip().lower().replace(" ", "")
    if normalized in {"", "-", "нет", "неважно", "безлимита"}:
        return None

    value = int(normalized)
    if value < 0:
        raise ValueError("price must be non-negative")
    return value


async def _get_existing_ad_ids(query_params: dict[str, str]) -> set[int]:
    ads = await search_ads(query_params)
    ad_ids: set[int] = set()
    for ad in ads:
        ad_id = extract_ad_id(ad)
        if ad_id is not None:
            ad_ids.add(ad_id)
    return ad_ids


async def _show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    
    category = CATEGORIES[data["category"]]["label"]
    deal_type = DEAL_TYPES[data["deal_type"]]
    city = CITIES[data["city"]]["label"]
    rooms = ROOMS[data["rooms"]]
    
    price_from = data.get("price_from")
    price_to = data.get("price_to")
    if price_from is None and price_to is None:
        price = "Любая"
    elif price_to is None:
        price = f"От {price_from} USD"
    elif price_from is None:
        price = f"До {price_to} USD"
    else:
        price = f"{price_from} - {price_to} USD"

    details = (
        f"<b>Категория:</b> {html.escape(category)}\n"
        f"<b>Тип сделки:</b> {html.escape(deal_type)}\n"
        f"<b>Город:</b> {html.escape(city)}\n"
        f"<b>Комнаты:</b> {html.escape(rooms)}\n"
        f"<b>Цена:</b> {html.escape(price)}"
    )

    await state.set_state(FilterWizard.confirm)
    await message.edit_text(
        "Проверьте данные вашего фильтра:\n\n"
        f"{details}",
        reply_markup=_confirm_keyboard(),
    )


def build_router(session_factory: sessionmaker[Session], webapp_url: str | None = None) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user is None:
            return

        with session_factory() as session:
            crud.create_user(session, message.from_user.id)

        await message.answer(
            "Привет. Я отслеживаю объявления Kufar по сохранённым фильтрам.\n\n"
            "Используйте главное меню для навигации.\n"
            "Miniapp доступен через команду /miniapp.",
            reply_markup=_main_menu_reply_keyboard()
        )
        await message.answer(
            "Главное меню:",
            reply_markup=_main_menu_inline_keyboard()
        )

    @router.message(F.text == "📱 Главное меню")
    @router.message(Command("menu"))
    async def main_menu_handler(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=_main_menu_inline_keyboard()
        )

    @router.callback_query(F.data == "main_menu:show")
    async def show_main_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "Главное меню:",
                reply_markup=_main_menu_inline_keyboard()
            )

    @router.callback_query(F.data == "main_menu:help")
    async def help_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
                await callback.message.edit_text(
                    "Создайте фильтр через Главное меню. Бот будет периодически проверять Kufar "
                    "и присылать объявления, которые ещё не отправлялись по этому фильтру.\n\n"
                    "Для MVP доступны категории недвижимости: квартиры и дома.\n"
                    "Miniapp доступен через команду /miniapp.",
                    reply_markup=_keyboard([[("🔙 В главное меню", "main_menu:show")]])
                )

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "Создайте фильтр через Главное меню. Бот будет периодически проверять Kufar "
            "и присылать объявления, которые ещё не отправлялись по этому фильтру.\n\n"
            "Для MVP доступны категории недвижимости: квартиры и дома.\n"
            "Miniapp доступен через команду /miniapp.",
            reply_markup=_keyboard([[("🔙 В главное меню", "main_menu:show")]])
        )

    @router.message(Command("miniapp"))
    async def miniapp_command(message: Message) -> None:
        if not webapp_url:
            await message.answer(
                "WEBAPP_URL не настроен. Укажите публичный HTTPS URL miniapp в .env и перезапустите бота."
            )
            return

        await message.answer(
            "Откройте miniapp для управления фильтрами.",
            reply_markup=_miniapp_keyboard(webapp_url),
        )

    async def _show_my_filters(user_id: int, message_to_edit: Message | None = None, send_answer: callable = None) -> None:
        with session_factory() as session:
            subscriptions = crud.get_user_active_subscriptions(session, user_id)

        if not subscriptions:
            text = "Активных фильтров нет. Создать новый можно в Главном меню."
            markup = _keyboard([[("🔙 В главное меню", "main_menu:show")]])
        else:
            lines = ["Ваши активные фильтры:"]
            for index, subscription in enumerate(subscriptions, start=1):
                lines.append(f"#{index}: {html.escape(subscription.title)}")
            text = "\n".join(lines)
            markup = _delete_filters_keyboard(subscriptions)

        if message_to_edit:
            await message_to_edit.edit_text(text, reply_markup=markup)
        elif send_answer:
            await send_answer(text, reply_markup=markup)

    @router.callback_query(F.data == "main_menu:filters")
    async def my_filters_callback(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            return
        await callback.answer()
        await _show_my_filters(callback.from_user.id, message_to_edit=callback.message)

    @router.message(Command("my_filters"))
    async def my_filters(message: Message) -> None:
        if message.from_user is None:
            return
        await _show_my_filters(message.from_user.id, send_answer=message.answer)

    @router.callback_query(F.data.startswith("delete_filter:"))
    async def delete_filter(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.data is None:
            return

        try:
            subscription_id = int(callback.data.split(":", 1)[1])
        except ValueError:
            await callback.answer("Некорректный фильтр", show_alert=True)
            return

        with session_factory() as session:
            deleted = crud.deactivate_subscription(session, callback.from_user.id, subscription_id)

        if deleted:
            await callback.answer("Фильтр удалён")
            await _show_my_filters(callback.from_user.id, message_to_edit=callback.message)
        else:
            await callback.answer("Фильтр не найден", show_alert=True)

    @router.callback_query(F.data == "main_menu:create")
    async def new_filter_callback(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(FilterWizard.category)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Выберите категорию:", reply_markup=_category_keyboard())

    @router.callback_query(F.data.startswith("back:"))
    async def back_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None or callback.message is None:
            return
        
        target_state = callback.data.split(":", 1)[1]
        
        if target_state == "category":
            await state.set_state(FilterWizard.category)
            await callback.message.edit_text("Выберите категорию:", reply_markup=_category_keyboard())
        elif target_state == "deal_type":
            await state.set_state(FilterWizard.deal_type)
            data = await state.get_data()
            category_key = data.get("category")
            if isinstance(category_key, str):
                await callback.message.edit_text("Выберите тип сделки:", reply_markup=_deal_type_keyboard(category_key))
        elif target_state == "city":
            await state.set_state(FilterWizard.city)
            await callback.message.edit_text("Выберите город:", reply_markup=_city_keyboard())
        elif target_state == "price_from":
            await state.set_state(FilterWizard.price_from)
            await callback.message.edit_text("Введите минимальную цену в USD. Если минимума нет, отправьте '-'.", reply_markup=_keyboard([[("🔙 Назад", "back:city")]]))
        elif target_state == "price_to":
            await state.set_state(FilterWizard.price_to)
            await callback.message.edit_text("Введите максимальную цену в USD. Если максимума нет, отправьте '-'.", reply_markup=_keyboard([[("🔙 Назад", "back:price_from")]]))
        elif target_state == "rooms":
            await state.set_state(FilterWizard.rooms)
            await callback.message.edit_text("Выберите количество комнат:", reply_markup=_rooms_keyboard())
        
        await callback.answer()

    @router.message(Command("new_filter"))
    async def new_filter(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(FilterWizard.category)
        await message.answer("Выберите категорию:", reply_markup=_category_keyboard())

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=_main_menu_reply_keyboard())

    @router.callback_query(FilterWizard.category, F.data.startswith("cat:"))
    async def choose_category(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None:
            return

        category_key = callback.data.split(":", 1)[1]
        if category_key not in CATEGORIES:
            await callback.answer("Неизвестная категория", show_alert=True)
            return

        await state.update_data(category=category_key)
        await state.set_state(FilterWizard.deal_type)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "Выберите тип сделки:",
                reply_markup=_deal_type_keyboard(category_key),
            )

    @router.callback_query(FilterWizard.deal_type, F.data.startswith("deal:"))
    async def choose_deal_type(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None:
            return

        deal_type = callback.data.split(":", 1)[1]
        data = await state.get_data()
        category_key = data.get("category")
        if not isinstance(category_key, str) or deal_type not in get_allowed_deals(category_key):
            await callback.answer("Этот тип сделки недоступен для категории", show_alert=True)
            return

        await state.update_data(deal_type=deal_type)
        await state.set_state(FilterWizard.city)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text("Выберите город:", reply_markup=_city_keyboard())

    @router.callback_query(FilterWizard.city, F.data.startswith("city:"))
    async def choose_city(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None:
            return

        city_key = callback.data.split(":", 1)[1]
        if city_key not in CITIES:
            await callback.answer("Неизвестный город", show_alert=True)
            return

        await state.update_data(city=city_key)
        await state.set_state(FilterWizard.price_from)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "Введите минимальную цену в USD. Если минимума нет, отправьте '-'.",
                reply_markup=_keyboard([[("🔙 Назад", "back:city")]])
            )

    @router.message(FilterWizard.price_from)
    async def enter_price_from(message: Message, state: FSMContext) -> None:
        try:
            price_from = _parse_optional_price(message.text or "")
        except ValueError:
            await message.answer("Введите целое число в USD или '-'.")
            return

        await state.update_data(price_from=price_from)
        await state.set_state(FilterWizard.price_to)
        await message.answer(
            "Введите максимальную цену в USD. Если максимума нет, отправьте '-'.",
            reply_markup=_keyboard([[("🔙 Назад", "back:price_from")]])
        )

    @router.message(FilterWizard.price_to)
    async def enter_price_to(message: Message, state: FSMContext) -> None:
        try:
            price_to = _parse_optional_price(message.text or "")
        except ValueError:
            await message.answer("Введите целое число в USD или '-'.")
            return

        data = await state.get_data()
        price_from = data.get("price_from")
        if price_from is not None and price_to is not None and price_to < price_from:
            await message.answer(
                "Максимальная цена не может быть меньше минимальной. Введите максимум ещё раз.",
                reply_markup=_keyboard([[("🔙 Назад", "back:price_from")]])
            )
            return

        await state.update_data(price_to=price_to)
        await state.set_state(FilterWizard.rooms)
        await message.answer("Выберите количество комнат:", reply_markup=_rooms_keyboard())

    @router.callback_query(FilterWizard.rooms, F.data.startswith("rooms:"))
    async def choose_rooms(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None:
            return

        rooms = callback.data.split(":", 1)[1]
        if rooms not in ROOMS:
            await callback.answer("Неизвестный вариант", show_alert=True)
            return

        await state.update_data(rooms=rooms)
        await callback.answer()
        if callback.message:
            await _show_confirmation(callback.message, state)

    @router.callback_query(FilterWizard.confirm, F.data.startswith("confirm:"))
    async def confirm_filter(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None or callback.from_user is None:
            return

        action = callback.data.split(":", 1)[1]
        if action == "cancel":
            await state.clear()
            await callback.answer("Отменено")
            if callback.message:
                await callback.message.edit_text(
                    "Создание фильтра отменено.",
                    reply_markup=_keyboard([[("🔙 В главное меню", "main_menu:show")]])
                )
            return

        if action != "save":
            await callback.answer("Неизвестное действие", show_alert=True)
            return

        data = await state.get_data()
        try:
            title = describe_filter(data)
            query_params = build_query_params(data)
        except KeyError:
            logger.exception("Filter wizard data is incomplete: %s", data)
            await callback.answer("Фильтр заполнен не полностью", show_alert=True)
            return

        await callback.answer("Сохраняю фильтр")
        existing_ad_ids = await _get_existing_ad_ids(query_params)

        with session_factory() as session:
            subscription = crud.add_subscription(session, callback.from_user.id, title, query_params)
            for ad_id in existing_ad_ids:
                crud.mark_ad_sent(session, subscription.id, ad_id)

        await state.clear()
        if callback.message:
            await callback.message.edit_text(
                f"Фильтр сохранён: <b>{html.escape(subscription.title)}</b>\n\n"
                "Текущие объявления отмечены как уже просмотренные. "
                "В чат будут приходить только новые публикации после создания фильтра.",
                reply_markup=_keyboard([[("🔙 В главное меню", "main_menu:show")]])
            )

    return router
