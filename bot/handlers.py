from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.orm import Session, sessionmaker

from db import crud

logger = logging.getLogger(__name__)


def _miniapp_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=webapp_url))],
        ]
    )


async def _set_bot_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands([
            BotCommand(command="miniapp", description="Открыть приложение"),
            BotCommand(command="help", description="Как использовать бота"),
        ])
    except Exception:
        logger.warning("Failed to set bot commands", exc_info=True)


def build_router(session_factory: sessionmaker[Session], webapp_url: str | None = None) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user is None:
            return

        with session_factory() as session:
            crud.create_user(session, message.from_user.id)

        await message.answer(
            "<b>Kufar Monitoring Bot</b>\n\n"
            "Бот мониторит объявления по вашим фильтрам и отправляет их вам.\n\n"
            "Все взаимодействия происходят в приложении. Открыть его можно кнопкой ниже, либо кнопкой слева от поля ввода сообщения.",
            reply_markup=_miniapp_keyboard(webapp_url) if webapp_url else None,
            parse_mode="HTML",
        )

    @router.message(Command("miniapp"))
    async def miniapp_command(message: Message) -> None:
        if not webapp_url:
            await message.answer(
                "WEBAPP_URL is not configured. Please set it in your .env file and restart the bot."
            )
            return

        await message.answer(
            "Open the Mini App to create and manage your filters:",
            reply_markup=_miniapp_keyboard(webapp_url),
        )

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "📋 <b>How it works:</b>\n\n"
            "1. Open the Mini App using the menu button or /miniapp command\n"
            "2. Create filters for the properties you're looking for\n"
            "3. I'll monitor Kufar and send new matching listings to this chat\n\n"
            "All filter management is done through the Mini App."
            "\n\n"
            "<b>Commands:</b>\n"
            "/miniapp - Open the Mini App\n"
            "/help - Show this help message",
            parse_mode="HTML",
        )

    @router.startup()
    async def on_startup(bot: Bot) -> None:
        await _set_bot_commands(bot)

    return router
