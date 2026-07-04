from __future__ import annotations

from collections.abc import Iterable
from typing import Any


CATEGORIES: dict[str, dict[str, Any]] = {
    "flat": {
        "label": "Квартиры",
        "cat": "1010",
        "deal_types": ("let", "sell"),
        "rooms_required": True,
    },
    "house": {
        "label": "Дома, агроусадьбы, коттеджи",
        "cat": "1020",
        "deal_types": ("sell",),
        "rooms_required": True,
    },
}

DEAL_TYPES = {
    "let": "Долгосрочная аренда",
    "sell": "Покупка",
}

CITIES = {
    "minsk": {
        "label": "Минск",
        "gtsy": "country-belarus~province-minsk~locality-minsk",
    },
    "brest": {
        "label": "Брест",
        "gtsy": "country-belarus~province-brest~locality-brest",
    },
}

ROOMS = {
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5 и более",
}

ROOM_OPTIONS: dict[str, str] = {
    "any": "Любые",
    "studio": "Студия",
    "1": "1",
    "2": "2",
    "3": "3",
    "4+": "4+",
}

ROOM_QUERY_VALUES: dict[str, str] = {
    "studio": "0",
    "1": "1",
    "2": "2",
    "3": "3",
    "4+": "4,5",
}


def get_allowed_deals(category_key: str) -> tuple[str, ...]:
    category = CATEGORIES[category_key]
    return tuple(category["deal_types"])


def build_query_params(data: dict[str, Any]) -> dict[str, str]:
    category = CATEGORIES[data["category"]]
    city = CITIES[data["city"]]

    params: dict[str, str] = {
        "cat": category["cat"],
        "cur": "USD",
        "gtsy": city["gtsy"],
        "lang": "ru",
        "size": "30",
        "typ": data["deal_type"],
    }

    price_from = data.get("price_from")
    price_to = data.get("price_to")
    if price_from is not None or price_to is not None:
        left = str(price_from if price_from is not None else 0)
        right = str(price_to) if price_to is not None else ""
        params["prc"] = f"r:{left},{right}"

    rooms = data.get("rooms")
    room_values: list[str] = []
    if isinstance(rooms, str):
        rooms = [rooms]
    if isinstance(rooms, Iterable):
        for room in rooms:
            if not isinstance(room, str) or room == "any":
                continue
            mapped = ROOM_QUERY_VALUES.get(room)
            if mapped:
                room_values.append(mapped)
    if room_values:
        params["rms"] = f"v.or:{','.join(room_values)}"

    return params


def room_label(room_key: str) -> str:
    return ROOM_OPTIONS.get(room_key, room_key)


def describe_rooms(raw_rooms: Any) -> str:
    if raw_rooms is None:
        return "любые комнаты"

    if isinstance(raw_rooms, str):
        if raw_rooms == "any":
            return "любые комнаты"
        raw_rooms = [raw_rooms]

    if isinstance(raw_rooms, Iterable):
        labels = [room_label(room) for room in raw_rooms if isinstance(room, str) and room != "any"]
        labels = [label for label in labels if label]
        if not labels:
            return "любые комнаты"
        if len(labels) == 1:
            return f"{labels[0]} комн."
        if len(labels) == 2:
            return f"{labels[0]} или {labels[1]} комн."
        return f"{', '.join(labels[:-1])} или {labels[-1]} комн."

    return "любые комнаты"


def describe_filter(data: dict[str, Any]) -> str:
    category = CATEGORIES[data["category"]]["label"]
    deal_type = DEAL_TYPES[data["deal_type"]]
    city = CITIES[data["city"]]["label"]
    rooms = describe_rooms(data.get("rooms"))

    price_from = data.get("price_from")
    price_to = data.get("price_to")
    if price_from is None and price_to is None:
        price = "любая цена"
    elif price_to is None:
        price = f"от {price_from} USD"
    elif price_from is None:
        price = f"до {price_to} USD"
    else:
        price = f"{price_from}-{price_to} USD"

    return f"{category}, {deal_type}, {city}, {rooms}, {price}"
