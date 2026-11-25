"""Public waitlist intake and tenant-isolated owner follow-up."""

from datetime import datetime, time, timedelta, timezone as dt_timezone
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.constants.enums import MAX_ADVANCE_BOOKING_DAYS
from app.core.constants.enums import MAX_SERVICE_DURATION_MINUTES
from app.models.booking_waitlist_entry import BookingWaitlistEntry
from app.models.barbershop import Barbershop
from app.models.appointment import Appointment
from app.models.barber_availability import BarberAvailability
from app.models.barber_availability_block import BarberAvailabilityBlock
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
    _build_client_link,
    _consume_public_booking_quota,
    _get_public_shop,
    _public_booking_client_ip,
    _slot_available_for_duration,
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


@router.get("/owner/waitlist/{entry_id}/matches")
def owner_waitlist_matches(
    entry_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Find real, unbooked slots compatible with one active tenant request."""
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(
            status_code=403, detail="Solo el propietario puede consultar coincidencias"
        )
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    entry = db.query(BookingWaitlistEntry).filter(
        BookingWaitlistEntry.id == entry_id,
        BookingWaitlistEntry.barbershop_id == shop.id,
        BookingWaitlistEntry.is_deleted == False,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if entry.status != "new":
        raise HTTPException(status_code=409, detail="La solicitud ya no está pendiente")
    service = db.query(Service).filter(
        Service.id == entry.service_id,
        Service.barbershop_id == shop.id,
        Service.is_active == True,
        Service.is_deleted == False,
    ).first()
    if not service:
        return {"items": [], "service_name": entry.service_name_snapshot}

    now = utc_now_naive()
    timezone = _get_timezone(shop)
    local_today = _utc_aware(now).astimezone(timezone).date()
    min_date = max(entry.preferred_date_start or local_today, local_today)
    max_date = min(
        entry.preferred_date_end or local_today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS),
        local_today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS),
    )
    if max_date < min_date:
        return {"items": [], "service_name": entry.service_name_snapshot}
    local_start = datetime.combine(min_date, time.min, tzinfo=timezone)
    local_end = datetime.combine(max_date + timedelta(days=1), time.min, tzinfo=timezone)
    range_start = max(now, local_start.astimezone(dt_timezone.utc).replace(tzinfo=None))
    range_end = local_end.astimezone(dt_timezone.utc).replace(tzinfo=None)

    slots_query = db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.is_active == True,
        BarberAvailability.is_booked == False,
        BarberAvailability.is_deleted == False,
        BarberAvailability.slot_start >= range_start,
        BarberAvailability.slot_start < range_end,
    )
    if entry.barber_id:
        slots_query = slots_query.filter(BarberAvailability.barber_id == entry.barber_id)
    slots = slots_query.order_by(BarberAvailability.slot_start, BarberAvailability.id).limit(300).all()
    if not slots:
        return {"items": [], "service_name": service.name}

    barber_ids = {slot.barber_id for slot in slots}
    first_start = min(slot.slot_start for slot in slots)
    last_end = max(slot.slot_end for slot in slots)
    appointments = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.barber_id.in_(barber_ids),
        Appointment.status.in_(("pending", "confirmed", "in_progress")),
        Appointment.is_deleted == False,
        Appointment.scheduled_time >= first_start - timedelta(minutes=MAX_SERVICE_DURATION_MINUTES),
        Appointment.scheduled_time < last_end,
    ).all()
    blocks = db.query(BarberAvailabilityBlock).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.barber_id.in_(barber_ids),
        BarberAvailabilityBlock.is_deleted == False,
        BarberAvailabilityBlock.starts_at < last_end,
        BarberAvailabilityBlock.ends_at > first_start,
    ).all()
    appointments_by_barber: dict[int, list[Appointment]] = {}
    blocks_by_barber: dict[int, list[BarberAvailabilityBlock]] = {}
    for appointment in appointments:
        appointments_by_barber.setdefault(appointment.barber_id, []).append(appointment)
    for block in blocks:
        blocks_by_barber.setdefault(block.barber_id, []).append(block)
    barbers = {
        barber.id: barber.full_name
        for barber in db.query(User).filter(User.id.in_(barber_ids)).all()
    }
    booking_base = _build_client_link(shop.slug)
    matches = []
    for slot in slots:
        if not _slot_available_for_duration(
            slot,
            blocks_by_barber.get(slot.barber_id, []),
            appointments_by_barber.get(slot.barber_id, []),
            service.duration_minutes,
        ):
            continue
        matches.append({
            "availability_id": slot.id,
            "slot_start": _utc_aware(slot.slot_start),
            "barber_id": slot.barber_id,
            "barber_name": barbers.get(slot.barber_id),
            "booking_url": (
                f"{booking_base}&service_id={service.id}&barber_id={slot.barber_id}"
            ),
        })
        if len(matches) == 8:
            break
    return {"items": matches, "service_name": service.name}


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

