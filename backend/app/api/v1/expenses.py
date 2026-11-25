"""Owner-only, tenant-scoped operating expense ledger."""

import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.common import (
    _audit,
    _cash_register_closed_for_user,
    _get_timezone,
    _utc_aware,
)
from app.core.database import get_db
from app.models import Barbershop, OperatingExpense, User
from app.schemas.expenses import OperatingExpenseCreate
from app.utils.datetime import local_day_start_utc_naive, utc_now_naive

router = APIRouter(prefix="/owner/expenses", tags=["Operating expenses"])


def _owner_shop(user: User, db: Session, *, lock: bool = False) -> Barbershop:
    if user.role != "barbershop_owner" or not user.barbershop_id:
        raise HTTPException(
            status_code=403,
            detail="Solo el propietario puede gestionar gastos",
        )
    query = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_active.is_(True),
        Barbershop.is_deleted.is_(False),
    )
    if lock:
        query = query.with_for_update()
    shop = query.first()
    if not shop:
        raise HTTPException(
            status_code=404,
            detail="Barbería no encontrada o inactiva",
        )
    if not shop.currency:
        raise HTTPException(
            status_code=409,
            detail="Configura la moneda antes de registrar gastos",
        )
    return shop


def _serialize(expense: OperatingExpense) -> dict:
    return {
        "id": expense.id,
        "category": expense.category,
        "description": expense.description,
        "amount_cents": expense.amount_cents,
        "payment_method": expense.payment_method,
        "currency": expense.currency,
        "spent_at": expense.spent_at,
        "created_by_user_id": expense.created_by_user_id,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_operating_expense(
    data: OperatingExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a current-date expense; repeat submissions are idempotent."""
    shop = _owner_shop(current_user, db, lock=True)
    payload = {
        "category": data.category,
        "description": data.description,
        "amount_cents": data.amount_cents,
        "payment_method": data.payment_method,
        "created_by_user_id": current_user.id,
    }
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload_hash = hashlib.sha256(canonical_payload).hexdigest()
    idempotency_key = str(data.idempotency_key).encode("ascii")
    key_hash = hashlib.sha256(idempotency_key).hexdigest()
    existing = (
        db.query(OperatingExpense)
        .filter(
            OperatingExpense.barbershop_id == shop.id,
            OperatingExpense.request_key_hash == key_hash,
            OperatingExpense.is_deleted.is_(False),
        )
        .first()
    )
    if existing:
        if existing.request_payload_hash != payload_hash:
            raise HTTPException(
                status_code=409,
                detail="La clave ya se usó con otros datos",
            )
        return _serialize(existing)

    now = utc_now_naive()
    business_date = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    close_key = datetime.combine(business_date, time.min)
    if _cash_register_closed_for_user(db, current_user, shop.id, close_key):
        raise HTTPException(
            status_code=409,
            detail="La caja de hoy ya está cerrada",
        )

    expense = OperatingExpense(
        barbershop_id=shop.id,
        created_by_user_id=current_user.id,
        category=data.category,
        description=data.description,
        amount_cents=data.amount_cents,
        payment_method=data.payment_method,
        currency=shop.currency,
        spent_at=now,
        request_key_hash=key_hash,
        request_payload_hash=payload_hash,
    )
    db.add(expense)
    db.flush()
    _audit(
        db,
        current_user,
        "operating_expense.recorded",
        "operating_expense",
        expense.id,
        shop.id,
        {
            "category": expense.category,
            "amount_cents": expense.amount_cents,
            "payment_method": expense.payment_method,
            "currency": expense.currency,
        },
    )
    return _serialize(expense)


@router.get("")
def list_operating_expenses(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List only the owner's tenant expenses, newest first."""
    shop = _owner_shop(current_user, db)
    query = db.query(OperatingExpense).filter(
        OperatingExpense.barbershop_id == shop.id,
        OperatingExpense.is_deleted.is_(False),
    )
    if start_date is not None or end_date is not None:
        if start_date is None or end_date is None or end_date < start_date:
            raise HTTPException(
                status_code=422,
                detail="Indica un rango de fechas válido",
            )
        if end_date - start_date > timedelta(days=365):
            raise HTTPException(
                status_code=422,
                detail="El rango no puede superar 366 días",
            )
        timezone = ZoneInfo(shop.timezone)
        start = local_day_start_utc_naive(start_date, timezone)
        end = local_day_start_utc_naive(end_date + timedelta(days=1), timezone)
        query = query.filter(
            OperatingExpense.spent_at >= start,
            OperatingExpense.spent_at < end,
        )
    expenses = (
        query.order_by(
            OperatingExpense.spent_at.desc(),
            OperatingExpense.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize(expense) for expense in expenses],
        "limit": limit,
    }
