from __future__ import annotations

import logging
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def _clean_params(params: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = {**DEFAULT_PARAMS}
    for key, value in params.items():
        if value is None or value == "":
            continue
        cleaned[key] = value
    return cleaned


async def search_ads(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    request_params = _clean_params(params)

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
            response = await client.get(SEARCH_URL, params=request_params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Kufar API returned status %s: %s", exc.response.status_code, exc.response.text[:300])
        return []
    except httpx.RequestError as exc:
        logger.warning("Kufar API request failed (%s): %s", type(exc).__name__, exc)
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

