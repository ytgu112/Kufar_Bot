from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from parser.kufar_client import build_image_url, search_ads


TEST_PARAMS = {
    "cat": "1010",
    "cur": "USD",
    "gtsy": "country-belarus~province-minsk~locality-minsk",
    "lang": "ru",
    "prc": "r:0,450",
    "rms": "v.or:2",
    "size": "3",
    "typ": "let",
}


async def main() -> None:
    ads = await search_ads(TEST_PARAMS)
    print(f"ads_count={len(ads)}")

    for ad in ads[:3]:
        images = ad.get("images") or []
        image_url = build_image_url(images[0]) if images else None
        print(
            {
                "ad_id": ad.get("ad_id"),
                "subject": ad.get("subject"),
                "price_usd": ad.get("price_usd"),
                "ad_link": ad.get("ad_link"),
                "image_url": image_url,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())

