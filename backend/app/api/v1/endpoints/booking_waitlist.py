"""Public waitlist intake and tenant-isolated owner follow-up."""

from datetime import datetime, time, timedelta, timezone as dt_timezone
import hashlib
import secrets
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.constants.enums import MAX_ADVANCE_BOOKING_DAYS
from app.core.constants.enums import MAX_SERVICE_DURATION_MINUTES
from app.models.booking_waitlist_entry import BookingWaitlistEntry
from app.models.booking_waitlist_offer import BookingWaitlistOffer
from app.models.barbershop import Barbershop
from app.models.appointment import Appointment
from app.models.barber_availability import BarberAvailability
from app.models.barber_availability_block import BarberAvailabilityBlock
from app.models.service import Service
from app.models.user import User
from app.schemas.booking_waitlist import (
    PublicWaitlistRequest,
    WaitlistOfferCreate,
    WaitlistStatusUpdate,
)
from app.core.security.password import hash_password
from app.services.subscription_service import count_monthly_appointments
from app.services.waitlist_offer_service import create_waitlist_offer
from app.utils.datetime import utc_now_naive
from app.api.v1.endpoints.common import (
    _audit,
    _get_current_user,
    _get_timezone,
    _normalize_phone,
    _cash_register_closed_for_user,
    _require_active_subscription,
    _utc_aware,
)
from app.api.v1.endpoints.platform import (
    _build_client_link,
    _consume_public_booking_quota,
    _consume_public_token_quota,
    _get_public_shop,
    _notify_appointment_staff,
    _public_booking_client_ip,
    _queue_appointment_email,
    _queue_appointment_whatsapp,
    _slot_available_for_duration,
    PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT,
)

router = APIRouter(tags=["booking-waitlist"])


def _offer_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _waitlist_owner(
    db: Session,
    authorization: Optional[str],
    owner: User | None = None,
) -> tuple[User, Barbershop]:
    owner = owner or _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(
            status_code=403, detail="Solo el propietario puede gestionar la lista de espera"
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
    return owner, shop


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
    active_offers = (
        db.query(BookingWaitlistOffer)
        .filter(
            BookingWaitlistOffer.waitlist_entry_id.in_([row.id for row in rows] or [-1]),
            BookingWaitlistOffer.is_deleted == False,
            BookingWaitlistOffer.status == "pending",
        )
        .order_by(BookingWaitlistOffer.created_at.desc())
        .all()
    )
    offers_by_entry = {}
    now = utc_now_naive()
    for offer in active_offers:
        if offer.waitlist_entry_id not in offers_by_entry:
            offers_by_entry[offer.waitlist_entry_id] = {
                "status": "expired" if offer.expires_at <= now else offer.status,
                "expires_at": offer.expires_at,
            }
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
                "offer": offers_by_entry.get(entry.id),
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
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if entry.status not in {"new", "contacted"}:
        raise HTTPException(status_code=409, detail="La solicitud ya no está pendiente")
    service = (
        db.query(Service)
        .filter(
            Service.id == entry.service_id,
            Service.barbershop_id == shop.id,
            Service.is_active == True,
            Service.is_deleted == False,
        )
        .first()
    )
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
    slots = (
        slots_query.order_by(BarberAvailability.slot_start, BarberAvailability.id).limit(300).all()
    )
    if not slots:
        return {"items": [], "service_name": service.name}

    barber_ids = {slot.barber_id for slot in slots}
    first_start = min(slot.slot_start for slot in slots)
    last_end = max(slot.slot_end for slot in slots)
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop.id,
            Appointment.barber_id.in_(barber_ids),
            Appointment.status.in_(("pending", "confirmed", "in_progress")),
            Appointment.is_deleted == False,
            Appointment.scheduled_time
            >= first_start - timedelta(minutes=MAX_SERVICE_DURATION_MINUTES),
            Appointment.scheduled_time < last_end,
        )
        .all()
    )
    blocks = (
        db.query(BarberAvailabilityBlock)
        .filter(
            BarberAvailabilityBlock.barbershop_id == shop.id,
            BarberAvailabilityBlock.barber_id.in_(barber_ids),
            BarberAvailabilityBlock.is_deleted == False,
            BarberAvailabilityBlock.starts_at < last_end,
            BarberAvailabilityBlock.ends_at > first_start,
        )
        .all()
    )
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
        matches.append(
            {
                "availability_id": slot.id,
                "slot_start": _utc_aware(slot.slot_start),
                "barber_id": slot.barber_id,
                "barber_name": barbers.get(slot.barber_id),
                "booking_url": (
                    f"{booking_base}&service_id={service.id}&barber_id={slot.barber_id}"
                ),
            }
        )
        if len(matches) == 8:
            break
    return {"items": matches, "service_name": service.name}


@router.post("/owner/waitlist/{entry_id}/offers", status_code=201)
def owner_create_waitlist_offer(
    entry_id: int,
    data: WaitlistOfferCreate,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Issue a private, expiring offer and queue its WhatsApp delivery."""
    owner = _get_current_user(db, authorization)
    owner, shop = _waitlist_owner(db, authorization, owner)
    _require_active_subscription(db, shop)
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
    if entry.status not in {"new", "contacted"}:
        raise HTTPException(status_code=409, detail="La solicitud está cerrada")
    now = utc_now_naive()
    slot = (
        db.query(BarberAvailability)
        .filter(
            BarberAvailability.id == data.availability_id,
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_active == True,
            BarberAvailability.is_booked == False,
            BarberAvailability.is_deleted == False,
            BarberAvailability.slot_start >= now,
        )
        .with_for_update()
        .first()
    )
    service = (
        db.query(Service)
        .filter(
            Service.id == entry.service_id,
            Service.barbershop_id == shop.id,
            Service.is_active == True,
            Service.is_deleted == False,
        )
        .first()
    )
    if not slot or not service or (entry.barber_id and entry.barber_id != slot.barber_id):
        raise HTTPException(
            status_code=409, detail="El turno ya no está disponible para esta solicitud"
        )
    if slot.slot_end - slot.slot_start < timedelta(minutes=service.duration_minutes):
        raise HTTPException(
            status_code=409, detail="El turno no tiene duración suficiente para el servicio"
        )
    local_today = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    local_slot_date = _utc_aware(slot.slot_start).astimezone(_get_timezone(shop)).date()
    if (
        slot.slot_start > now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
        or local_slot_date < (entry.preferred_date_start or local_today)
        or local_slot_date
        > (entry.preferred_date_end or local_today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS))
    ):
        raise HTTPException(
            status_code=409, detail="El turno no coincide con las fechas solicitadas"
        )
    active_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop.id,
            Appointment.barber_id == slot.barber_id,
            Appointment.status.in_(("pending", "confirmed", "in_progress")),
            Appointment.is_deleted == False,
        )
        .with_for_update()
        .all()
    )
    blocks = (
        db.query(BarberAvailabilityBlock)
        .filter(
            BarberAvailabilityBlock.barbershop_id == shop.id,
            BarberAvailabilityBlock.barber_id == slot.barber_id,
            BarberAvailabilityBlock.is_deleted == False,
            BarberAvailabilityBlock.starts_at < slot.slot_end,
            BarberAvailabilityBlock.ends_at > slot.slot_start,
        )
        .all()
    )
    if not _slot_available_for_duration(
        slot, blocks, active_appointments, service.duration_minutes
    ):
        raise HTTPException(status_code=409, detail="El turno dejó de estar disponible")

    try:
        offer = create_waitlist_offer(
            db,
            shop=shop,
            entry=entry,
            slot=slot,
            expires_in_minutes=data.expires_in_minutes,
            actor=owner,
            source="owner",
            now=now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    expires_at = offer.expires_at
    return {
        "id": offer.id,
        "status": offer.status,
        "expires_at": expires_at,
        "delivery_queued": True,
    }


@router.get("/public/{slug}/waitlist-offers/{token}")
def public_waitlist_offer_preview(
    slug: str,
    token: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return only the offer details needed by its token holder."""
    response.headers["Cache-Control"] = "no-store"
    shop = _get_public_shop(db, slug)
    if not shop or len(token) < 32 or len(token) > 128:
        raise HTTPException(status_code=404, detail="La oferta no está disponible")
    offer = (
        db.query(BookingWaitlistOffer)
        .filter(
            BookingWaitlistOffer.barbershop_id == shop.id,
            BookingWaitlistOffer.token_hash == _offer_hash(token),
            BookingWaitlistOffer.is_deleted == False,
        )
        .first()
    )
    if not offer:
        raise HTTPException(status_code=404, detail="La oferta no está disponible")
    if offer.status == "pending" and offer.expires_at <= utc_now_naive():
        offer.status = "expired"
        db.commit()
    entry = (
        db.query(BookingWaitlistEntry)
        .filter(
            BookingWaitlistEntry.id == offer.waitlist_entry_id,
            BookingWaitlistEntry.barbershop_id == shop.id,
            BookingWaitlistEntry.is_deleted == False,
        )
        .first()
    )
    slot = (
        db.query(BarberAvailability)
        .filter(
            BarberAvailability.id == offer.availability_id,
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_deleted == False,
        )
        .first()
    )
    if not entry or not slot:
        raise HTTPException(status_code=404, detail="La oferta no está disponible")
    return {
        "status": offer.status,
        "expires_at": offer.expires_at,
        "barbershop_name": shop.name,
        "service_name": entry.service_name_snapshot,
        "barber_name": slot.barber.full_name if slot.barber else "Barbero",
        "slot_start": _utc_aware(slot.slot_start),
        "currency": shop.currency,
    }


@router.post("/public/{slug}/waitlist-offers/{token}/accept")
def public_accept_waitlist_offer(
    slug: str,
    token: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Accept once, atomically claim the slot and create its real appointment."""
    response.headers["Cache-Control"] = "no-store"
    shop = _get_public_shop(db, slug)
    if not shop or len(token) < 32 or len(token) > 128:
        raise HTTPException(status_code=404, detail="La oferta no está disponible")
    _consume_public_token_quota(
        db,
        "waitlist-offer",
        _public_booking_client_ip(request),
        utc_now_naive(),
        PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT,
    )
    offer_identity = (
        db.query(BookingWaitlistOffer)
        .filter(
            BookingWaitlistOffer.barbershop_id == shop.id,
            BookingWaitlistOffer.token_hash == _offer_hash(token),
            BookingWaitlistOffer.is_deleted == False,
        )
        .first()
    )
    if not offer_identity:
        raise HTTPException(status_code=404, detail="La oferta no está disponible")
    entry = (
        db.query(BookingWaitlistEntry)
        .filter(
            BookingWaitlistEntry.id == offer_identity.waitlist_entry_id,
            BookingWaitlistEntry.barbershop_id == shop.id,
            BookingWaitlistEntry.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    offer = (
        db.query(BookingWaitlistOffer)
        .filter(
            BookingWaitlistOffer.id == offer_identity.id,
            BookingWaitlistOffer.barbershop_id == shop.id,
            BookingWaitlistOffer.token_hash == _offer_hash(token),
            BookingWaitlistOffer.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    if not offer:
        raise HTTPException(status_code=404, detail="La oferta no está disponible")
    now = utc_now_naive()
    if offer.status == "accepted" and offer.appointment_id:
        appointment = db.query(Appointment).filter(Appointment.id == offer.appointment_id).first()
        return {
            "accepted": True,
            "already_accepted": True,
            "appointment_id": offer.appointment_id,
            "status": appointment.status if appointment else "pending",
        }
    if offer.status != "pending":
        raise HTTPException(status_code=410, detail="La oferta ya no está vigente")
    if offer.expires_at <= now:
        offer.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="La oferta venció")

    if not entry or entry.status == "closed":
        offer.status = "cancelled"
        db.commit()
        raise HTTPException(status_code=410, detail="La solicitud de espera ya se cerró")
    shop = (
        db.query(Barbershop)
        .filter(
            Barbershop.id == shop.id,
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    subscription = _require_active_subscription(db, shop, lock=True)
    if (
        subscription.max_appointments_per_month is not None
        and count_monthly_appointments(db, shop) >= subscription.max_appointments_per_month
    ):
        raise HTTPException(
            status_code=402, detail="La barbería alcanzó el límite de citas de su plan"
        )
    service = (
        db.query(Service)
        .filter(
            Service.id == entry.service_id,
            Service.barbershop_id == shop.id,
            Service.is_active == True,
            Service.is_deleted == False,
        )
        .first()
    )
    slot = (
        db.query(BarberAvailability)
        .filter(
            BarberAvailability.id == offer.availability_id,
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_active == True,
            BarberAvailability.is_booked == False,
            BarberAvailability.is_deleted == False,
            BarberAvailability.slot_start >= now,
        )
        .with_for_update()
        .first()
    )
    if not service or not slot or (entry.barber_id and entry.barber_id != slot.barber_id):
        offer.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="El horario ya no está disponible")
    local_today = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    local_slot_date = _utc_aware(slot.slot_start).astimezone(_get_timezone(shop)).date()
    if (
        slot.slot_start > now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
        or local_slot_date < (entry.preferred_date_start or local_today)
        or local_slot_date
        > (entry.preferred_date_end or local_today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS))
    ):
        offer.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="El horario ya no coincide con la solicitud")
    barber = (
        db.query(User)
        .filter(
            User.id == slot.barber_id,
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_active == True,
            User.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    if not barber or slot.slot_end - slot.slot_start < timedelta(minutes=service.duration_minutes):
        raise HTTPException(status_code=409, detail="El horario ya no permite este servicio")
    appointment_end = slot.slot_start + timedelta(minutes=service.duration_minutes)
    blocks = (
        db.query(BarberAvailabilityBlock)
        .filter(
            BarberAvailabilityBlock.barbershop_id == shop.id,
            BarberAvailabilityBlock.barber_id == barber.id,
            BarberAvailabilityBlock.is_deleted == False,
            BarberAvailabilityBlock.starts_at < appointment_end,
            BarberAvailabilityBlock.ends_at > slot.slot_start,
        )
        .all()
    )
    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop.id,
            Appointment.barber_id == barber.id,
            Appointment.status.in_(("pending", "confirmed", "in_progress")),
            Appointment.is_deleted == False,
        )
        .with_for_update()
        .all()
    )
    if not _slot_available_for_duration(slot, blocks, appointments, service.duration_minutes):
        offer.status = "expired"
        db.commit()
        raise HTTPException(status_code=409, detail="El horario dejó de estar disponible")
    local_day = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    if _utc_aware(slot.slot_start).astimezone(
        _get_timezone(shop)
    ).date() == local_day and _cash_register_closed_for_user(
        db,
        barber,
        shop.id,
        datetime.combine(local_day, time.min),
    ):
        raise HTTPException(status_code=409, detail="La barbería no acepta reservas para hoy")
    phone = _normalize_phone(entry.phone)
    client = (
        db.query(User)
        .filter(
            User.phone == phone,
            User.barbershop_id == shop.id,
            User.role == "client",
            User.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    if client and not client.is_active:
        raise HTTPException(status_code=409, detail="El perfil de cliente está desactivado")
    if not client:
        if (
            subscription.max_clients is not None
            and db.query(User.id)
            .filter(
                User.barbershop_id == shop.id,
                User.role == "client",
                User.is_deleted == False,
            )
            .count()
            >= subscription.max_clients
        ):
            raise HTTPException(
                status_code=402, detail="La barbería alcanzó el límite de clientes del plan"
            )
        parts = entry.client_name.split()
        client = User(
            email=f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            first_name=parts[0],
            last_name=" ".join(parts[1:]) or "Cliente",
            phone=phone,
            role="client",
            is_active=True,
            is_verified=False,
            barbershop_id=shop.id,
        )
        db.add(client)
        db.flush()
    tracking_token = secrets.token_urlsafe(32)
    appointment = Appointment(
        barbershop_id=shop.id,
        client_id=client.id,
        barber_id=barber.id,
        scheduled_time=slot.slot_start,
        estimated_duration=service.duration_minutes,
        service_type=service.name,
        service_price=service.price,
        status="pending",
        client_notes=entry.notes,
        tracking_token_hash=hashlib.sha256(tracking_token.encode("utf-8")).hexdigest(),
    )
    db.add(appointment)
    claimed = db.execute(
        update(BarberAvailability)
        .where(
            BarberAvailability.id == slot.id,
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_booked == False,
            BarberAvailability.is_active == True,
            BarberAvailability.is_deleted == False,
        )
        .values(is_booked=True)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Este horario acaba de ser reservado")
    db.flush()
    offer.status = "accepted"
    offer.accepted_at = now
    offer.appointment_id = appointment.id
    entry.status = "closed"
    db.query(BookingWaitlistOffer).filter(
        BookingWaitlistOffer.waitlist_entry_id == entry.id,
        BookingWaitlistOffer.id != offer.id,
        BookingWaitlistOffer.status == "pending",
        BookingWaitlistOffer.is_deleted == False,
    ).update({BookingWaitlistOffer.status: "cancelled"}, synchronize_session=False)
    local_time = _utc_aware(slot.slot_start).astimezone(_get_timezone(shop))
    _notify_appointment_staff(
        db,
        appointment,
        "appointment_booked",
        "Nueva cita desde lista de espera",
        f"{client.full_name} · {service.name} · {local_time.strftime('%d/%m/%Y %H:%M')}",
    )
    _audit(
        db,
        None,
        "booking.waitlist_offer_accepted",
        "booking_waitlist_offer",
        offer.id,
        shop.id,
        {"entry_id": entry.id, "appointment_id": appointment.id, "availability_id": slot.id},
    )
    _audit(
        db,
        None,
        "appointment.booked_from_waitlist",
        "appointment",
        appointment.id,
        shop.id,
        {"barber_id": barber.id, "service_id": service.id, "availability_id": slot.id},
    )
    tracking_url = f"{_build_client_link(shop.slug)}&{urlencode({'track_token': tracking_token})}"
    _queue_appointment_email(db, appointment, "booking_received")
    _queue_appointment_whatsapp(
        db,
        appointment,
        phone,
        f"💈 {shop.name}: tu cita quedó reservada para {local_time.strftime('%d/%m/%Y %H:%M')} "
        f"con {barber.full_name}. Seguimiento: {tracking_url}",
        "confirmation:client",
        recipient_user_id=client.id,
    )
    db.commit()
    return {
        "accepted": True,
        "appointment_id": appointment.id,
        "status": appointment.status,
        "tracking_url": tracking_url,
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
    if data.status in {"new", "closed"}:
        db.query(BookingWaitlistOffer).filter(
            BookingWaitlistOffer.waitlist_entry_id == entry.id,
            BookingWaitlistOffer.status == "pending",
            BookingWaitlistOffer.is_deleted == False,
        ).update({BookingWaitlistOffer.status: "cancelled"}, synchronize_session=False)
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
