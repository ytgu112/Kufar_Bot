from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Mapping
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
RMS_IMAGE_BASE_URL = "https://rms.kufar.by/v1/list_thumbs_2x"

DEFAULT_PARAMS: dict[str, str] = {
    "lang": "ru",
    "size": "30",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

ACCEPT = "application/json,text/plain,*/*"

_RATE_LIMIT_INTERVAL = 1.0
_last_request_time = 0.0
_rate_lock = asyncio.Lock()


def set_rate_limit_interval(interval: float) -> None:
    global _RATE_LIMIT_INTERVAL
    _RATE_LIMIT_INTERVAL = interval


async def _rate_limit():
    global _last_request_time
    async with _rate_lock:
        now = time.monotonic()
        wait = _RATE_LIMIT_INTERVAL - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()


def _clean_params(params: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = {**DEFAULT_PARAMS}
    for key, value in params.items():
        if value is None or value == "":
            continue
        cleaned[key] = value
    return cleaned


_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _rotate_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": ACCEPT,
    }


async def search_ads(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    request_params = _clean_params(params)

    await _rate_limit()

    for attempt in range(3):
        try:
            client = await get_client()
            response = await client.get(SEARCH_URL, params=request_params, headers=_rotate_headers())

            if response.status_code in (429, 403):
                logger.warning("Kufar API returned %s (attempt %s/3): %s", response.status_code, attempt + 1, response.text[:300])
                if attempt < 2:
                    backoff = 2 ** (attempt + 2)
                    await asyncio.sleep(backoff)
                    continue
                return []

            response.raise_for_status()
            data = response.json()
            break
        except httpx.TimeoutException as exc:
            logger.warning("Kufar API timeout (attempt %s/3): %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("Kufar API returned status %s (attempt %s/3): %s", exc.response.status_code, attempt + 1, exc.response.text[:300])
            if attempt < 2 and exc.response.status_code >= 500:
                await asyncio.sleep(2 ** attempt)
                continue
            return []
        except httpx.RequestError as exc:
            logger.warning("Kufar API request failed (attempt %s/3): %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return []
        except ValueError as exc:
            logger.warning("Kufar API returned invalid JSON: %s", exc)
            return []

    ads = data.get("ads") if isinstance(data, dict) else None
    if not isinstance(ads, list):
        logger.warning("Unexpected Kufar response structure: ads list is missing")
        return []

    return [ad for ad in ads if isinstance(ad, dict)]


def extract_next_cursor(response_data: Mapping[str, Any]) -> str | None:
    pagination = response_data.get("pagination")
    if not isinstance(pagination, Mapping):
        return None

    pages = pagination.get("pages")
    if not isinstance(pages, list):
        return None

    for page in pages:
        if isinstance(page, Mapping) and page.get("label") == "next":
            token = page.get("token")
            return token if isinstance(token, str) and token else None

    return None


def build_image_url(image: Mapping[str, Any] | None) -> str | None:
    if not image:
        return None

    path = image.get("path")
    if not isinstance(path, str) or not path:
        return None

    if path.startswith(("http://", "https://")):
        return path

    safe_path = quote(path.lstrip("/"), safe="/")
    return f"{RMS_IMAGE_BASE_URL}/{safe_path}"

