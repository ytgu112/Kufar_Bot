from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_kufar_list_time(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None

    normalized = raw_value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    return as_utc(parsed)


def extract_ad_id(ad: Mapping[str, Any]) -> int | None:
    raw_ad_id = ad.get("ad_id") or ad.get("list_id")
    try:
        return int(raw_ad_id)
    except (TypeError, ValueError):
        return None

