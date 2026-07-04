from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def _miniapp_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Open Mini App", web_app=WebAppInfo(url=webapp_url))],
        ]
    )


async def _set_bot_commands(bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="miniapp", description="Open Mini App"),
        BotCommand(command="help", description="How to use this bot"),
    ])


def build_router(session_factory: sessionmaker[Session], webapp_url: str | None = None) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user is None:
            return

        await message.answer(
            "🏠 <b>Kufar Monitoring Bot</b>\n\n"
            "I track new listings on Kufar.by and send them to you automatically.\n\n"
            "All interaction happens in the Mini App - tap the button below to get started.",
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
    async def on_startup(bot) -> None:
        await _set_bot_commands(bot)

    return router
