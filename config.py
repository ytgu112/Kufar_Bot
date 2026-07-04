from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str
    poll_interval_seconds: int
    log_level: str
    max_ads_per_poll: int
    request_pause_seconds: float
    fresh_ad_grace_seconds: int
    webapp_host: str
    webapp_port: int
    webapp_url: str


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def load_settings() -> Settings:
    load_dotenv()

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        db_path=os.getenv("DB_PATH", "data/kufar_bot.sqlite3").strip(),
        poll_interval_seconds=_get_int("POLL_INTERVAL_SECONDS", 300),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        max_ads_per_poll=_get_int("MAX_ADS_PER_POLL", 5),
        request_pause_seconds=_get_float("REQUEST_PAUSE_SECONDS", 1.5),
        fresh_ad_grace_seconds=_get_int("FRESH_AD_GRACE_SECONDS", 30),
        webapp_host=os.getenv("WEBAPP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        webapp_port=_get_int("WEBAPP_PORT", 8080),
        webapp_url=os.getenv("WEBAPP_URL", "").strip(),
    )
