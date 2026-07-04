from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session, sessionmaker

from db import crud
from parser.ad_utils import extract_ad_id, parse_kufar_list_time
from parser.kufar_client import build_image_url, search_ads

logger = logging.getLogger(__name__)


def _money_from_cents(raw_value: Any) -> str | None:
    if raw_value in (None, ""):
        return None

    try:
        value = Decimal(str(raw_value)) / Decimal("100")
    except (InvalidOperation, ValueError):
        return None

    if value == value.to_integral():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ")


def _format_price(ad: dict[str, Any]) -> str:
    # Try direct price fields first (in order of preference)
    price_currency_map = {
        "price_usd": "USD",
        "price_byn": "BYN",
        "price": ad.get("currency", "USD"),
    }
    
    for price_field, currency in price_currency_map.items():
        raw_price = ad.get(price_field)
        if raw_price not in (None, "", 0):
            price = _money_from_cents(raw_price)
            if price:
                return f"{price} {currency}"

    # Fallback to calculator array
    calculator = ad.get("calculator")
    if isinstance(calculator, list):
        for item in calculator:
            if isinstance(item, dict):
                price = _money_from_cents(item.get("price"))
                if price:
                    currency = str(item.get("currency") or "USD").upper()
                    return f"{price} {currency}"

    return "Цена не указана"


_TZ_MINSK = timezone(timedelta(hours=3))


def _format_list_time(raw_value: Any) -> str:
    """Convert Kufar list_time to a human-readable GMT+3 string."""
    dt = parse_kufar_list_time(raw_value)
    if dt is None:
        return ""
    local_dt = dt.astimezone(_TZ_MINSK)
    return local_dt.strftime("%d.%m.%Y %H:%M (GMT+3)")


def _caption(ad: dict[str, Any]) -> str:
    subject = html.escape(str(ad.get("subject") or "Объявление Kufar"))
    price = html.escape(_format_price(ad))
    body = html.escape(str(ad.get("body_short") or "")).strip()
    list_time = html.escape(_format_list_time(ad.get("list_time")))

    lines = [
        f"<b>{subject}</b>",
        f"Цена: {price}",
    ]
    if list_time:
        lines.append(f"Опубликовано: {list_time}")
    if body:
        lines.append("")
        lines.append(body)

    caption = "\n".join(lines)
    if len(caption) > 1000:
        return caption[:997] + "..."
    return caption


def _ad_keyboard(ad: dict[str, Any]) -> InlineKeyboardMarkup | None:
    ad_link = ad.get("ad_link")
    if not isinstance(ad_link, str) or not ad_link:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть на Kufar", url=ad_link)],
        ]
    )


async def _send_ad(bot: Bot, telegram_id: int, ad: dict[str, Any]) -> bool:
    caption = _caption(ad)
    reply_markup = _ad_keyboard(ad)

    # Robust image extraction with fallbacks
    images = ad.get("images")
    image_url = None

    # Try primary images field (list)
    if isinstance(images, list) and len(images) > 0:
        image_url = build_image_url(images[0])

    # Fallback: try if images is a single dict
    if not image_url and isinstance(images, dict):
        image_url = build_image_url(images)

    # Fallback: try alternative image fields
    if not image_url:
        for img_field in ("primary_image", "thumbnail", "cover_photo"):
            img_data = ad.get(img_field)
            if img_data:
                if isinstance(img_data, dict):
                    image_url = build_image_url(img_data)
                else:
                    image_url = build_image_url({"path": img_data})
                if image_url:
                    break

    try:
        if image_url:
            await bot.send_photo(
                chat_id=telegram_id,
                photo=image_url,
                caption=caption,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id=telegram_id,
                text=caption,
                reply_markup=reply_markup,
            )
        return True
    except TelegramForbiddenError:
        # Re-raise to disable subscription
        raise
    except TelegramAPIError as exc:
        if image_url:
            logger.warning("Could not send ad image %s, falling back to text: %s", image_url, exc)
            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=caption,
                    reply_markup=reply_markup,
                )
                return True
            except TelegramForbiddenError:
                raise
            except TelegramAPIError as fallback_exc:
                logger.warning("Could not send ad %s to user %s: %s", ad.get("ad_id"), telegram_id, fallback_exc)
        else:
            logger.warning("Could not send ad %s to user %s: %s", ad.get("ad_id"), telegram_id, exc)
        return False


async def poll_once(
    bot: Bot,
    session_factory: sessionmaker[Session],
    max_ads_per_poll: int = 5,
    request_pause_seconds: float = 1.5,
) -> None:
    logger.info("Starting Kufar polling job")

    with session_factory() as session:
        subscriptions = crud.get_active_subscriptions(session)

        for index, subscription in enumerate(subscriptions):
            try:
                query_params = json.loads(subscription.query_params)
            except json.JSONDecodeError:
                logger.warning("Subscription %s has invalid query_params JSON", subscription.id)
                continue

            if not isinstance(query_params, dict):
                logger.warning("Subscription %s query_params is not a dict", subscription.id)
                continue

            ads = await search_ads(query_params)
            sent_count = 0
            skipped_already_sent_count = 0

            logger.debug("Subscription %s: fetched %s ads", subscription.id, len(ads))
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=15)

            for ad in reversed(ads):
                ad_id = extract_ad_id(ad)
                if ad_id is None:
                    logger.warning("Skipping ad with invalid ad_id: %s", ad.get("ad_id") or ad.get("list_id"))
                    continue

                list_time = parse_kufar_list_time(ad.get("list_time"))
                if list_time and list_time < cutoff_time:
                    logger.debug("Ad %s is older than 15 minutes, skipping", ad_id)
                    continue

                if crud.is_ad_sent(session, subscription.id, ad_id):
                    logger.debug("Ad %s already sent for subscription %s", ad_id, subscription.id)
                    skipped_already_sent_count += 1
                    continue

                if sent_count >= max_ads_per_poll:
                    logger.debug(
                        "Subscription %s: reached max_ads_per_poll=%s, stopping",
                        subscription.id,
                        max_ads_per_poll,
                    )
                    break

                try:
                    is_sent = await _send_ad(bot, subscription.user.telegram_id, ad)
                except TelegramForbiddenError:
                    logger.warning("User %s blocked the bot. Deactivating subscription %s", subscription.user.telegram_id, subscription.id)
                    crud.deactivate_subscription(session, subscription.user.telegram_id, subscription.id)
                    break

                if is_sent:
                    crud.mark_ad_sent(session, subscription.id, ad_id)
                    sent_count += 1

            logger.info(
                "Subscription %s checked: fetched=%s, sent=%s, skipped_already_sent=%s",
                subscription.id,
                len(ads),
                sent_count,
                skipped_already_sent_count,
            )

            if index < len(subscriptions) - 1 and request_pause_seconds > 0:
                await asyncio.sleep(request_pause_seconds)


def start_scheduler(
    bot: Bot,
    session_factory: sessionmaker[Session],
    poll_interval_seconds: int,
    max_ads_per_poll: int,
    request_pause_seconds: float,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")
    scheduler.add_job(
        poll_once,
        trigger="interval",
        seconds=poll_interval_seconds,
        kwargs={
            "bot": bot,
            "session_factory": session_factory,
            "max_ads_per_poll": max_ads_per_poll,
            "request_pause_seconds": request_pause_seconds,
        },
        id="poll_kufar",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=10),
    )
    scheduler.start()
    return scheduler
