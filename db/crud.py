from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from db.models import SentAd, Subscription, User

logger = logging.getLogger(__name__)


def create_user(session: Session, telegram_id: int) -> User:
    user = get_user_by_telegram_id(session, telegram_id)
    if user is not None:
        return user

    user = User(telegram_id=telegram_id)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing_user = get_user_by_telegram_id(session, telegram_id)
        if existing_user is None:
            raise
        return existing_user

    session.refresh(user)
    return user


def get_user_by_telegram_id(session: Session, telegram_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_id == telegram_id))


def add_subscription(
    session: Session,
    telegram_id: int,
    title: str,
    query_params: dict[str, Any],
) -> Subscription:
    user = create_user(session, telegram_id)
    subscription = Subscription(
        user_id=user.id,
        title=title,
        query_params=json.dumps(query_params, ensure_ascii=False),
        is_active=True,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return subscription


def get_active_subscriptions(session: Session) -> list[Subscription]:
    statement = (
        select(Subscription)
        .options(selectinload(Subscription.user))
        .where(Subscription.is_active.is_(True))
        .order_by(Subscription.created_at.asc())
    )
    return list(session.scalars(statement).all())


def get_user_active_subscriptions(session: Session, telegram_id: int) -> list[Subscription]:
    statement = (
        select(Subscription)
        .join(Subscription.user)
        .where(User.telegram_id == telegram_id, Subscription.is_active.is_(True))
        .order_by(Subscription.created_at.desc())
    )
    return list(session.scalars(statement).all())


def get_user_subscriptions(session: Session, telegram_id: int) -> list[Subscription]:
    statement = (
        select(Subscription)
        .join(Subscription.user)
        .where(User.telegram_id == telegram_id)
        .order_by(Subscription.created_at.desc())
    )
    return list(session.scalars(statement).all())


def get_subscription_for_user(session: Session, telegram_id: int, subscription_id: int) -> Subscription | None:
    statement = (
        select(Subscription)
        .join(Subscription.user)
        .where(
            Subscription.id == subscription_id,
            User.telegram_id == telegram_id,
        )
    )
    return session.scalar(statement)


def is_ad_sent(session: Session, subscription_id: int, ad_id: int) -> bool:
    statement = select(SentAd.id).where(
        SentAd.subscription_id == subscription_id,
        SentAd.ad_id == ad_id,
    )
    return session.scalar(statement) is not None


def mark_ad_sent(session: Session, subscription_id: int, ad_id: int) -> bool:
    if is_ad_sent(session, subscription_id, ad_id):
        return False

    sent_ad = SentAd(subscription_id=subscription_id, ad_id=ad_id)
    session.add(sent_ad)
    try:
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        logger.debug("Ad %s for subscription %s was already marked as sent", ad_id, subscription_id)
        return False


def deactivate_subscription(session: Session, telegram_id: int, subscription_id: int) -> bool:
    statement = (
        select(Subscription)
        .join(Subscription.user)
        .where(
            Subscription.id == subscription_id,
            User.telegram_id == telegram_id,
            Subscription.is_active.is_(True),
        )
    )
    subscription = session.scalar(statement)
    if subscription is None:
        return False

    subscription.is_active = False
    session.commit()
    return True


def toggle_subscription(session: Session, telegram_id: int, subscription_id: int) -> Subscription | None:
    subscription = get_subscription_for_user(session, telegram_id, subscription_id)
    if subscription is None:
        return None

    subscription.is_active = not subscription.is_active
    session.commit()
    session.refresh(subscription)
    return subscription


def update_subscription(
    session: Session,
    telegram_id: int,
    subscription_id: int,
    title: str,
    query_params: dict[str, Any],
) -> Subscription | None:
    subscription = get_subscription_for_user(session, telegram_id, subscription_id)
    if subscription is None:
        return None

    subscription.title = title
    subscription.query_params = json.dumps(query_params, ensure_ascii=False)
    session.commit()
    session.refresh(subscription)
    return subscription


def delete_subscription(session: Session, telegram_id: int, subscription_id: int) -> bool:
    subscription = get_subscription_for_user(session, telegram_id, subscription_id)
    if subscription is None:
        return False

    session.delete(subscription)
    session.commit()
    return True
