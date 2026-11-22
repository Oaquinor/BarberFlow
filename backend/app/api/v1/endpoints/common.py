"""Shared request and tenant helpers for API v1 endpoints."""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user as authenticate_user
from app.core.constants.enums import SUBSCRIPTION_LIMITS
from app.models.barbershop import Barbershop
from app.models.payment import CashRegisterClose
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit
from app.utils.datetime import utc_now_naive

def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())

def _require_active_subscription(db: Session, shop: Barbershop, lock: bool = False) -> Subscription:
    if not shop.subscription_id:
        raise HTTPException(status_code=402, detail="La barbería no tiene una suscripción activa")
    query = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    )
    if lock:
        query = query.with_for_update()
    subscription = query.first()
    if (
        not subscription
        or subscription.status != "active"
        or subscription.current_period_end <= utc_now_naive()
    ):
        raise HTTPException(status_code=402, detail="La suscripción de esta barbería no está activa")
    return subscription

def _get_timezone(shop: Barbershop) -> ZoneInfo:
    try:
        return ZoneInfo(shop.timezone)
    except (ZoneInfoNotFoundError, TypeError):
        raise HTTPException(status_code=500, detail="La zona horaria de la barbería no es válida")

def _utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def _cash_register_closed_for_user(
    db: Session, user: User, barbershop_id: int, business_date: datetime,
) -> bool:
    query = db.query(CashRegisterClose.id).join(
        User, User.id == CashRegisterClose.closed_by_user_id,
    ).filter(
        CashRegisterClose.barbershop_id == barbershop_id,
        CashRegisterClose.business_date == business_date,
        CashRegisterClose.is_deleted == False,
    )
    if user.role == "barber":
        query = query.filter(or_(
            CashRegisterClose.closed_by_user_id == user.id,
            (User.role == "barbershop_owner") & (User.barbershop_id == barbershop_id),
        ))
    else:
        query = query.filter(CashRegisterClose.closed_by_user_id == user.id)
    # A locking read uses current committed state after waiting on the shared
    # barbershop mutex; a repeatable-read snapshot could miss a close that just won.
    return query.with_for_update().first() is not None

def _audit(db: Session, actor: Optional[User], action: str, entity_type: str, entity_id: int | None,
           barbershop_id: int | None = None, details: dict | None = None) -> None:
    """Add a minimal audit event to the current transaction without credentials or secrets."""
    record_audit(db, actor, action, entity_type, entity_id, barbershop_id, details)

def _get_current_user(db: Session, authorization: Optional[str]) -> User:
    """Use the shared authentication checks for every platform route."""
    return authenticate_user(authorization, db)

def _apply_plan_limits(sub: Subscription, plan: str) -> None:
    """Sync subscription limits with the selected plan defaults."""
    limits = SUBSCRIPTION_LIMITS.get(plan)
    if limits is None:
        return
    sub.max_barbers = limits["max_barbers"]
    sub.max_appointments_per_month = limits["max_appointments_per_month"]
    sub.max_clients = limits["max_clients"]
