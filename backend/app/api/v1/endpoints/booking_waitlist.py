"""Public waitlist intake and tenant-isolated owner follow-up."""

from datetime import timedelta
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.constants.enums import MAX_ADVANCE_BOOKING_DAYS
from app.models.booking_waitlist_entry import BookingWaitlistEntry
from app.models.barbershop import Barbershop
from app.models.service import Service
from app.models.user import User
from app.schemas.booking_waitlist import PublicWaitlistRequest, WaitlistStatusUpdate
from app.utils.datetime import utc_now_naive
from app.api.v1.endpoints.common import (
    _audit,
    _get_current_user,
    _get_timezone,
    _normalize_phone,
    _require_active_subscription,
    _utc_aware,
)
from app.api.v1.endpoints.platform import (
    _consume_public_booking_quota,
    _get_public_shop,
    _public_booking_client_ip,
)

router = APIRouter(tags=["booking-waitlist"])


@router.post("/public/{slug}/waitlist", status_code=202)
def create_public_waitlist_request(
    slug: str,
    data: PublicWaitlistRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Record a non-binding request to be contacted when availability changes."""
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)
    key_hash = hashlib.sha256(str(data.idempotency_key).encode("ascii")).hexdigest()
    existing = (
        db.query(BookingWaitlistEntry.id)
        .filter(
            BookingWaitlistEntry.barbershop_id == shop.id,
            BookingWaitlistEntry.request_key_hash == key_hash,
        )
        .first()
    )
    if existing:
        return {
            "accepted": True,
            "message": "Tu solicitud quedó registrada. No garantiza una cita; la barbería te contactará si encuentra un horario adecuado.",
        }
    _consume_public_booking_quota(db, shop.id, _public_booking_client_ip(request), utc_now_naive())

    service = (
        db.query(Service)
        .filter(
            Service.id == data.service_id,
            Service.barbershop_id == shop.id,
            Service.is_active == True,
            Service.is_deleted == False,
        )
        .first()
    )
    if not service:
        raise HTTPException(
            status_code=422, detail="El servicio no está disponible en esta barbería"
        )

    barber = None
    if data.barber_id is not None:
        barber = (
            db.query(User)
            .filter(
                User.id == data.barber_id,
                User.barbershop_id == shop.id,
                User.role == "barber",
                User.is_active == True,
                User.is_deleted == False,
            )
            .first()
        )
        if not barber:
            raise HTTPException(
                status_code=422, detail="El barbero preferido no pertenece a esta barbería"
            )

    phone = _normalize_phone(data.phone)
    if not 6 <= len(phone) <= 20:
        raise HTTPException(status_code=422, detail="El teléfono debe tener entre 6 y 20 dígitos")

    local_today = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    latest_date = local_today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
    for preferred_date in (data.preferred_date_start, data.preferred_date_end):
        if preferred_date and not local_today <= preferred_date <= latest_date:
            raise HTTPException(
                status_code=422,
                detail="El rango de fechas debe estar entre hoy y los próximos 90 días",
            )

    entry = BookingWaitlistEntry(
        barbershop_id=shop.id,
        service_id=service.id,
        request_key_hash=key_hash,
        service_name_snapshot=service.name,
        barber_id=barber.id if barber else None,
        barber_name_snapshot=barber.full_name if barber else None,
        client_name=data.client_name,
        phone=phone,
        preferred_date_start=data.preferred_date_start,
        preferred_date_end=data.preferred_date_end,
        notes=data.notes,
        status="new",
    )
    db.add(entry)
    db.flush()
    _audit(
        db,
        None,
        "booking.waitlist_requested",
        "booking_waitlist_entry",
        entry.id,
        shop.id,
        {"service_id": service.id, "barber_id": barber.id if barber else None},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = (
            db.query(BookingWaitlistEntry.id)
            .filter(
                BookingWaitlistEntry.barbershop_id == shop.id,
                BookingWaitlistEntry.request_key_hash == key_hash,
            )
            .first()
        )
        if not existing:
            raise HTTPException(
                status_code=409, detail="No se pudo registrar la solicitud"
            ) from exc
    return {
        "accepted": True,
        "message": "Tu solicitud quedó registrada. No garantiza una cita; la barbería te contactará si encuentra un horario adecuado.",
    }


@router.get("/owner/waitlist")
def owner_list_waitlist(
    status: Optional[str] = Query(default=None, pattern="^(new|contacted|closed)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """List only this owner's tenant requests, newest first."""
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(
            status_code=403, detail="Solo el propietario puede consultar su lista de espera"
        )
    shop = (
        db.query(Barbershop)
        .filter(
            Barbershop.id == owner.barbershop_id,
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        )
        .first()
    )
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    query = db.query(BookingWaitlistEntry).filter(
        BookingWaitlistEntry.barbershop_id == shop.id,
        BookingWaitlistEntry.is_deleted == False,
    )
    if status:
        query = query.filter(BookingWaitlistEntry.status == status)
    total = query.count()
    rows = (
        query.order_by(BookingWaitlistEntry.created_at.desc(), BookingWaitlistEntry.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": entry.id,
                "client_name": entry.client_name,
                "phone": entry.phone,
                "service_name": entry.service_name_snapshot,
                "barber_id": entry.barber_id,
                "barber_name": entry.barber_name_snapshot,
                "preferred_date_start": entry.preferred_date_start,
                "preferred_date_end": entry.preferred_date_end,
                "notes": entry.notes,
                "status": entry.status,
                "contacted_at": entry.contacted_at,
                "created_at": entry.created_at,
            }
            for entry in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.put("/owner/waitlist/{entry_id}/status")
def owner_update_waitlist_status(
    entry_id: int,
    data: WaitlistStatusUpdate,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Record owner follow-up without creating or changing an appointment."""
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(
            status_code=403, detail="Solo el propietario puede actualizar la lista de espera"
        )
    shop = (
        db.query(Barbershop)
        .filter(
            Barbershop.id == owner.barbershop_id,
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        )
        .first()
    )
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    entry = (
        db.query(BookingWaitlistEntry)
        .filter(
            BookingWaitlistEntry.id == entry_id,
            BookingWaitlistEntry.barbershop_id == shop.id,
            BookingWaitlistEntry.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    previous_status = entry.status
    entry.status = data.status
    if data.status == "contacted" and previous_status != "contacted":
        entry.contacted_at = utc_now_naive()
    elif data.status == "new":
        entry.contacted_at = None
    _audit(
        db,
        owner,
        "booking.waitlist_status_updated",
        "booking_waitlist_entry",
        entry.id,
        shop.id,
        {"from": previous_status, "to": data.status},
    )
    db.commit()
    return {"id": entry.id, "status": entry.status, "contacted_at": entry.contacted_at}

