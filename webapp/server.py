from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import threading
import time
from collections.abc import Iterable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from sqlalchemy.orm import Session, sessionmaker

from bot.filter_config import (
    CATEGORIES,
    CITIES,
    DEAL_TYPES,
    ROOM_OPTIONS,
    build_query_params,
    describe_filter,
    describe_rooms,
    get_allowed_deals,
    room_label,
)
from db import crud
from parser.ad_utils import extract_ad_id
from parser.kufar_client import search_ads

logger = logging.getLogger(__name__)

AUTH_MAX_AGE_SECONDS = 24 * 60 * 60


class MiniAppError(RuntimeError):
    pass


class AuthError(MiniAppError):
    pass


class ValidationError(MiniAppError):
    def __init__(self, fields: dict[str, str], message: str = "Некорректные данные формы") -> None:
        super().__init__(message)
        self.fields = fields


def _json_response(status: int, payload: dict[str, Any]) -> tuple[bytes, str]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return body, f"application/json; charset=utf-8"


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or "0")
    if content_length <= 0:
        return {}

    raw = handler.rfile.read(content_length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError({"body": "Неверный JSON в теле запроса"}) from exc
    if not isinstance(payload, dict):
        raise ValidationError({"body": "Тело запроса должно быть JSON-объектом"})
    return payload


def _parse_optional_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValidationError({field_name: "Ожидается целое число"})
    if isinstance(value, int):
        if value < 0:
            raise ValidationError({field_name: "Число должно быть не меньше 0"})
        return value
    if isinstance(value, str):
        normalized = value.strip().replace(" ", "")
        if normalized == "":
            return None
        try:
            parsed = int(normalized)
        except ValueError as exc:
            raise ValidationError({field_name: "Ожидается целое число"}) from exc
        if parsed < 0:
            raise ValidationError({field_name: "Число должно быть не меньше 0"})
        return parsed
    raise ValidationError({field_name: "Ожидается целое число"})


def _normalize_rooms(raw_rooms: Any) -> list[str]:
    if raw_rooms in (None, "", [], "any"):
        return []

    if isinstance(raw_rooms, str):
        values = [part.strip() for part in raw_rooms.split(",") if part.strip()]
    elif isinstance(raw_rooms, Iterable):
        values = []
        for item in raw_rooms:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                values.append(text)
    else:
        raise ValidationError({"rooms": "Выберите хотя бы один вариант"})

    allowed = set(ROOM_OPTIONS) - {"any"}
    normalized: list[str] = []
    for room in values:
        if room == "any":
            return []
        if room not in allowed:
            raise ValidationError({"rooms": "Выберите допустимый вариант комнат"})
        if room not in normalized:
            normalized.append(room)
    return normalized


def _normalize_form_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, str] = {}

    category = payload.get("category")
    if not isinstance(category, str) or category not in CATEGORIES:
        fields["category"] = "Выберите категорию"

    deal_type = payload.get("deal_type")
    if not isinstance(deal_type, str):
        fields["deal_type"] = "Выберите тип сделки"
    elif isinstance(category, str) and category in CATEGORIES:
        if deal_type not in get_allowed_deals(category):
            fields["deal_type"] = "Этот тип сделки недоступен для категории"

    city = payload.get("city")
    if not isinstance(city, str) or city not in CITIES:
        fields["city"] = "Выберите город"

    rooms = _normalize_rooms(payload.get("rooms"))

    price_from = _parse_optional_int(payload.get("price_from"), "price_from")
    price_to = _parse_optional_int(payload.get("price_to"), "price_to")
    if price_from is not None and price_to is not None and price_from > price_to:
        fields["price_to"] = "Максимальная цена не может быть меньше минимальной"

    if fields:
        raise ValidationError(fields)

    normalized: dict[str, Any] = {
        "category": category,
        "deal_type": deal_type,
        "city": city,
        "rooms": rooms,
        "price_from": price_from,
        "price_to": price_to,
    }
    return normalized


def _query_params_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    normalized = _normalize_form_payload(payload)
    return build_query_params(normalized)


def _validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = AUTH_MAX_AGE_SECONDS) -> dict[str, Any]:
    if not bot_token:
        raise AuthError("BOT_TOKEN is required for Telegram auth")

    params = dict(parse_qsl(init_data, keep_blank_values=True))
    provided_hash = params.pop("hash", None)
    if not provided_hash:
        raise AuthError("Missing hash in initData")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash):
        raise AuthError("Invalid initData signature")

    auth_date_raw = params.get("auth_date")
    try:
        auth_date = int(auth_date_raw or "0")
    except ValueError as exc:
        raise AuthError("Invalid auth_date") from exc

    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise AuthError("initData is too old")

    user_raw = params.get("user")
    if not user_raw:
        raise AuthError("Missing user in initData")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise AuthError("Invalid user payload") from exc

    if not isinstance(user, dict) or "id" not in user:
        raise AuthError("Invalid user payload")

    try:
        telegram_id = int(user["id"])
    except (TypeError, ValueError) as exc:
        raise AuthError("Invalid user id") from exc

    return {
        "telegram_id": telegram_id,
        "user": user,
        "auth_date": auth_date,
    }


def _serialize_subscription(subscription: Any) -> dict[str, Any]:
    try:
        query_params = json.loads(subscription.query_params)
    except json.JSONDecodeError:
        query_params = {}

    if not isinstance(query_params, dict):
        query_params = {}

    # Try to use normalized_params if available, otherwise use query_params
    normalized_data = query_params
    if subscription.normalized_params:
        try:
            normalized_data = json.loads(subscription.normalized_params)
            if not isinstance(normalized_data, dict):
                normalized_data = query_params
        except json.JSONDecodeError:
            normalized_data = query_params

    summary = describe_filter(normalized_data)
    rooms = normalized_data.get("rooms")
    if isinstance(rooms, str):
        rooms = [rooms]

    return {
        "id": subscription.id,
        "title": subscription.title,
        "query_params": query_params,
        "summary": summary,
        "category": normalized_data.get("category"),
        "category_label": CATEGORIES.get(normalized_data.get("category"), {}).get("label", normalized_data.get("category")),
        "deal_type": normalized_data.get("deal_type"),
        "deal_type_label": DEAL_TYPES.get(normalized_data.get("deal_type"), normalized_data.get("deal_type")),
        "city": normalized_data.get("city"),
        "city_label": CITIES.get(normalized_data.get("city"), {}).get("label", normalized_data.get("city")),
        "rooms": rooms or [],
        "rooms_label": describe_rooms(rooms),
        "price_from": normalized_data.get("price_from"),
        "price_to": normalized_data.get("price_to"),
        "is_active": subscription.is_active,
        "created_at": subscription.created_at.isoformat() if getattr(subscription, "created_at", None) else None,
    }


def _serialize_meta() -> dict[str, Any]:
    category_items = []
    for key, value in CATEGORIES.items():
        category_items.append(
            {
                "key": key,
                "label": value["label"],
                "deal_types": [
                    {
                        "key": deal_key,
                        "label": DEAL_TYPES[deal_key],
                    }
                    for deal_key in value["deal_types"]
                ],
            }
        )

    return {
        "categories": category_items,
        "cities": [
            {
                "key": key,
                "label": value["label"],
            }
            for key, value in CITIES.items()
        ],
        "rooms": [
            {
                "key": key,
                "label": label,
            }
            for key, label in ROOM_OPTIONS.items()
        ],
    }


async def _backfill_existing_ads(session_factory: sessionmaker[Session], subscription_id: int, query_params: dict[str, str]) -> None:
    ads = await search_ads(query_params)
    if not ads:
        return

    with session_factory() as session:
        for ad in ads:
            ad_id = extract_ad_id(ad)
            if ad_id is None:
                continue
            crud.mark_ad_sent(session, subscription_id, ad_id)


class MiniAppServer:
    def __init__(
        self,
        host: str,
        port: int,
        session_factory: sessionmaker[Session],
        bot_token: str,
        public_url: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.session_factory = session_factory
        self.bot_token = bot_token
        self.public_url = public_url
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self.public_url:
            return self.public_url
        return f"http://{self.host}:{self.port}/miniapp"

    def start(self) -> None:
        if self._server is not None:
            return

        server = self._build_server()
        self._server = server

        thread = threading.Thread(target=server.serve_forever, name="miniapp-server", daemon=True)
        thread.start()
        self._thread = thread
        logger.info("Miniapp server started on http://%s:%s", self.host, server.server_address[1])

    def stop(self) -> None:
        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def _build_server(self) -> ThreadingHTTPServer:
        service = self
        static_dir = Path(__file__).resolve().parent

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                logger.info("%s - %s", self.address_string(), format % args)

            def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                body, content_type = _json_response(status, payload)
                self._send_bytes(status, content_type, body)

            def _send_error(self, status: int, message: str, fields: dict[str, str] | None = None) -> None:
                payload: dict[str, Any] = {"error": message}
                if fields:
                    payload["fields"] = fields
                self._send_json(status, payload)

            def _read_auth(self) -> dict[str, Any]:
                header = self.headers.get("Authorization", "")
                if not header.startswith("tma "):
                    raise AuthError("Missing Authorization: tma <initData>")
                init_data = header[4:]
                return _validate_telegram_init_data(init_data, service.bot_token)

            def _get_user(self) -> dict[str, Any]:
                auth = self._read_auth()
                telegram_id = auth["telegram_id"]
                with service.session_factory() as session:
                    crud.create_user(session, telegram_id)
                return auth

            def _subscription_or_404(self, telegram_id: int, subscription_id: int) -> Any:
                with service.session_factory() as session:
                    subscription = crud.get_subscription_for_user(session, telegram_id, subscription_id)
                    if subscription is None:
                        raise ValidationError({"subscription": "Фильтр не найден"})
                    return subscription

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path in {"/", "/miniapp"}:
                    file_name = "miniapp.html"
                    if parsed.path == "/":
                        file_name = "miniapp.html"
                    self._serve_static(file_name)
                    return
                if parsed.path == "/miniapp.css":
                    self._serve_static("miniapp.css", "text/css; charset=utf-8")
                    return
                if parsed.path == "/miniapp.js":
                    self._serve_static("miniapp.js", "application/javascript; charset=utf-8")
                    return
                if parsed.path == "/api/meta":
                    try:
                        self._read_auth()
                        self._send_json(HTTPStatus.OK, {"meta": _serialize_meta()})
                    except AuthError as exc:
                        self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
                    except Exception as exc:
                        logger.exception("Error loading meta")
                        self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Ошибка при загрузке данных")
                    return
                if parsed.path == "/api/filters":
                    try:
                        auth = self._read_auth()
                        with service.session_factory() as session:
                            subscriptions = crud.get_user_subscriptions(session, auth["telegram_id"])
                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "items": [_serialize_subscription(subscription) for subscription in subscriptions],
                            },
                        )
                    except AuthError as exc:
                        self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
                    except Exception as exc:
                        logger.exception("Error loading subscriptions")
                        self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Ошибка при загрузке фильтров")
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "Not found")

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/filters":
                    self._handle_create_filter()
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")

            def do_PATCH(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/filters/") and parsed.path.endswith("/toggle"):
                    self._handle_toggle_filter(parsed.path)
                    return
                if parsed.path.startswith("/api/filters/"):
                    self._handle_update_filter(parsed.path)
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")

            def do_DELETE(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/filters/"):
                    self._handle_delete_filter(parsed.path)
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")

            def _serve_static(self, file_name: str, content_type: str = "text/html; charset=utf-8") -> None:
                target = static_dir / file_name
                if not target.exists():
                    self._send_error(HTTPStatus.NOT_FOUND, "Asset not found")
                    return
                body = target.read_bytes()
                self._send_bytes(HTTPStatus.OK, content_type, body)

            def _handle_create_filter(self) -> None:
                try:
                    auth = self._read_auth()
                    payload = _read_json_body(self)
                    form = payload.get("form")
                    if not isinstance(form, dict):
                        raise ValidationError({"form": "Передайте объект form"})

                    normalized = _normalize_form_payload(form)
                    title = describe_filter(normalized)
                    query_params = build_query_params(normalized)

                    with service.session_factory() as session:
                        subscription = crud.add_subscription(
                            session, 
                            auth["telegram_id"], 
                            title, 
                            query_params,
                            normalized_params=normalized
                        )

                    try:
                        asyncio.run(_backfill_existing_ads(service.session_factory, subscription.id, query_params))
                    except Exception:
                        logger.exception("Could not backfill existing ads for subscription %s", subscription.id)

                    with service.session_factory() as session:
                        subscription = crud.get_subscription_for_user(session, auth["telegram_id"], subscription.id)

                    if subscription is None:
                        raise RuntimeError("Subscription disappeared after creation")

                    self._send_json(
                        HTTPStatus.CREATED,
                        {
                            "item": _serialize_subscription(subscription),
                        },
                    )
                except AuthError as exc:
                    self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
                except ValidationError as exc:
                    self._send_error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc), exc.fields)
                except Exception as exc:
                    logger.exception("Error creating filter")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Ошибка при создании фильтра")

            def _handle_update_filter(self, path: str) -> None:
                try:
                    auth = self._read_auth()
                    subscription_id = int(path.split("/")[3])
                    payload = _read_json_body(self)
                    form = payload.get("form")
                    if not isinstance(form, dict):
                        raise ValidationError({"form": "Передайте объект form"})

                    normalized = _normalize_form_payload(form)
                    title = describe_filter(normalized)
                    query_params = build_query_params(normalized)

                    with service.session_factory() as session:
                        subscription = crud.update_subscription(
                            session, 
                            auth["telegram_id"], 
                            subscription_id, 
                            title, 
                            query_params,
                            normalized_params=normalized
                        )

                    if subscription is None:
                        self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                        return

                    try:
                        asyncio.run(_backfill_existing_ads(service.session_factory, subscription.id, query_params))
                    except Exception:
                        logger.exception("Could not backfill existing ads for subscription %s", subscription.id)

                    with service.session_factory() as session:
                        subscription = crud.get_subscription_for_user(session, auth["telegram_id"], subscription_id)

                    if subscription is None:
                        self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                        return

                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "item": _serialize_subscription(subscription),
                        },
                    )
                except ValueError:
                    self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                except AuthError as exc:
                    self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
                except ValidationError as exc:
                    self._send_error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc), exc.fields)
                except Exception as exc:
                    logger.exception("Error updating filter")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Ошибка при обновлении фильтра")

            def _handle_toggle_filter(self, path: str) -> None:
                try:
                    auth = self._read_auth()
                    subscription_id = int(path.split("/")[3])

                    with service.session_factory() as session:
                        subscription = crud.toggle_subscription(session, auth["telegram_id"], subscription_id)

                    if subscription is None:
                        self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                        return

                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "item": _serialize_subscription(subscription),
                        },
                    )
                except ValueError:
                    self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                except AuthError as exc:
                    self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
                except Exception as exc:
                    logger.exception("Error toggling filter")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Ошибка при изменении статуса фильтра")

            def _handle_delete_filter(self, path: str) -> None:
                try:
                    auth = self._read_auth()
                    subscription_id = int(path.split("/")[3])

                    with service.session_factory() as session:
                        deleted = crud.delete_subscription(session, auth["telegram_id"], subscription_id)

                    if not deleted:
                        self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                        return

                    self._send_json(HTTPStatus.OK, {"ok": True})
                except ValueError:
                    self._send_error(HTTPStatus.NOT_FOUND, "Фильтр не найден")
                except AuthError as exc:
                    self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
                except Exception as exc:
                    logger.exception("Error deleting filter")
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Ошибка при удалении фильтра")

        return ThreadingHTTPServer((self.host, self.port), Handler)
