"""Shared subscription usage calculations."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Appointment, Barbershop
from app.utils.datetime import local_month_window_utc_naive, utc_now_naive


def count_monthly_appointments(db: Session, shop: Barbershop, now: datetime | None = None) -> int:
    """Count tenant appointments created in the current business-calendar month."""
    month_start, next_month_start = local_month_window_utc_naive(
        now or utc_now_naive(), ZoneInfo(shop.timezone),
    )
    return int(db.query(func.count(Appointment.id)).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.created_at >= month_start,
        Appointment.created_at < next_month_start,
        Appointment.is_deleted == False,
    ).scalar() or 0)
