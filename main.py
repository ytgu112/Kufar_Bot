from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import build_router
from config import load_settings
from db.session import create_session_factory
from parser.scheduler import start_scheduler
from webapp import MiniAppServer


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Put your Telegram bot token into .env")

    session_factory = create_session_factory(settings.db_path)
    webapp_server = MiniAppServer(
        host=settings.webapp_host,
        port=settings.webapp_port,
        session_factory=session_factory,
        bot_token=settings.bot_token,
        public_url=settings.webapp_url,
    )
    webapp_server.start()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router(session_factory, webapp_url=webapp_server.url if settings.webapp_url else None))

    scheduler = start_scheduler(
        bot=bot,
        session_factory=session_factory,
        poll_interval_seconds=settings.poll_interval_seconds,
        max_ads_per_poll=settings.max_ads_per_poll,
        request_pause_seconds=settings.request_pause_seconds,
    )

    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        webapp_server.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
