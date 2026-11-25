"""Manual and automatic dispatch of time-limited waitlist offers."""

import hashlib
import os
import secrets
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.constants.enums import MAX_ADVANCE_BOOKING_DAYS, MAX_SERVICE_DURATION_MINUTES
from app.models.appointment import Appointment
from app.models.barber_availability import BarberAvailability
from app.models.barber_availability_block import BarberAvailabilityBlock
from app.models.barbershop import Barbershop
from app.models.booking_waitlist_entry import BookingWaitlistEntry
from app.models.booking_waitlist_offer import BookingWaitlistOffer
from app.models.payment import CashRegisterClose
from app.models.service import Service
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.booking_availability import slot_available_for_duration
from app.services.notification_outbox import enqueue_delivery
from app.services.subscription_service import count_monthly_appointments
from app.utils.datetime import utc_now_naive

DEFAULT_OFFER_MINUTES = 120
MAX_AUTOMATIC_OFFERS_PER_CYCLE = 10
AUTOMATIC_SLOT_BATCH = 100


def _as_utc_aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _client_link(slug: str) -> str:
    base = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/client.html?shop={slug}"


def create_waitlist_offer(
    db: Session,
    *,
    shop: Barbershop,
    entry: BookingWaitlistEntry,
    slot: BarberAvailability,
    expires_in_minutes: int = DEFAULT_OFFER_MINUTES,
    actor: User | None = None,
    source: str = "owner",
    now: datetime | None = None,
) -> BookingWaitlistOffer:
    """Persist an offer, its audit event and WhatsApp delivery in one transaction."""
    now = (now or utc_now_naive()).replace(microsecond=0)
    existing = (
        db.query(BookingWaitlistOffer)
        .filter(
            BookingWaitlistOffer.barbershop_id == shop.id,
            BookingWaitlistOffer.availability_id == slot.id,
            BookingWaitlistOffer.status == "pending",
            BookingWaitlistOffer.is_deleted == False,
        )
        .with_for_update()
        .all()
    )
    for prior in existing:
        if prior.expires_at > now:
            raise ValueError("Este turno ya tiene una oferta vigente")
        prior.status = "expired"

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
    barber = (
        db.query(User)
        .filter(
            User.id == slot.barber_id,
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_active == True,
            User.is_deleted == False,
        )
        .first()
    )
    if not service or not barber:
        raise ValueError("No se encontraron el servicio o el barbero de la oferta")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = now + timedelta(minutes=expires_in_minutes)
    offer = BookingWaitlistOffer(
        barbershop_id=shop.id,
        waitlist_entry_id=entry.id,
        availability_id=slot.id,
        token_hash=token_hash,
        status="pending",
        expires_at=expires_at,
    )
    db.add(offer)
    db.flush()

    entry.status = "contacted"
    entry.contacted_at = now
    zone = ZoneInfo(shop.timezone)
    slot_local = _as_utc_aware(slot.slot_start).astimezone(zone)
    expires_local = _as_utc_aware(expires_at).astimezone(zone)
    offer_url = f"{_client_link(shop.slug)}&{urlencode({'waitlist_offer': token})}"
    body = (
        f"💈 {shop.name}: Hola {entry.client_name}, se liberó un horario para {service.name}: "
        f"{slot_local.strftime('%d/%m/%Y %H:%M')} con {barber.full_name}. "
        f"Puedes aceptarlo hasta {expires_local.strftime('%d/%m/%Y %H:%M')} "
        f"(hora de la barbería) aquí: {offer_url}. "
        "El horario se confirma solo cuando completes la aceptación."
    )
    enqueue_delivery(
        db,
        barbershop_id=shop.id,
        dedupe_key=f"waitlist-offer:{token_hash}:whatsapp",
        channel="whatsapp",
        event_type="waitlist_offer",
        recipient=entry.phone,
        body=body,
    )
    record_audit(
        db,
        actor,
        "booking.waitlist_offer_created",
        "booking_waitlist_offer",
        offer.id,
        shop.id,
        {
            "entry_id": entry.id,
            "availability_id": slot.id,
            "expires_at": expires_at.isoformat(),
            "source": source,
        },
    )
    return offer


def _business_date(value: datetime, shop: Barbershop) -> date:
    return _as_utc_aware(value).astimezone(ZoneInfo(shop.timezone)).date()


def _cash_closed_for_slot(
    db: Session, shop: Barbershop, barber: User, slot: BarberAvailability, today: date
) -> bool:
    if _business_date(slot.slot_start, shop) != today:
        return False
    rows = (
        db.query(CashRegisterClose.closed_by_user_id, User.role)
        .join(
            User,
            User.id == CashRegisterClose.closed_by_user_id,
        )
        .filter(
            CashRegisterClose.barbershop_id == shop.id,
            CashRegisterClose.business_date == datetime.combine(today, time.min),
            CashRegisterClose.is_deleted == False,
            User.is_deleted == False,
        )
        .all()
    )
    return any(
        closed_by_id == barber.id or role == "barbershop_owner" for closed_by_id, role in rows
    )


def enqueue_automatic_waitlist_offers(db: Session, now: datetime | None = None) -> int:
    """Offer newly available compatible slots to opted-in requests in FIFO order."""
    now = (now or utc_now_naive()).replace(microsecond=0)
    shops = (
        db.query(Barbershop)
        .join(
            Subscription,
            Subscription.id == Barbershop.subscription_id,
        )
        .filter(
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
            Subscription.status == "active",
            Subscription.current_period_end > now,
            Subscription.is_deleted == False,
        )
        .order_by(Barbershop.id)
        .all()
    )
    remaining = MAX_AUTOMATIC_OFFERS_PER_CYCLE
    issued = 0

    for shop in shops:
        if remaining <= 0:
            break
        subscription = (
            db.query(Subscription)
            .filter(
                Subscription.id == shop.subscription_id,
                Subscription.status == "active",
                Subscription.current_period_end > now,
                Subscription.is_deleted == False,
            )
            .first()
        )
        if not subscription:
            continue
        if (
            subscription.max_appointments_per_month is not None
            and count_monthly_appointments(db, shop, now) >= subscription.max_appointments_per_month
        ):
            continue

        entries = (
            db.query(BookingWaitlistEntry)
            .filter(
                BookingWaitlistEntry.barbershop_id == shop.id,
                BookingWaitlistEntry.status.in_(("new", "contacted")),
                BookingWaitlistEntry.is_deleted == False,
            )
            .order_by(BookingWaitlistEntry.created_at, BookingWaitlistEntry.id)
            .limit(200)
            .all()
        )
        if not entries:
            continue
        entry_ids = [entry.id for entry in entries]
        pending_offers = (
            db.query(BookingWaitlistOffer)
            .filter(
                BookingWaitlistOffer.waitlist_entry_id.in_(entry_ids),
                BookingWaitlistOffer.status == "pending",
                BookingWaitlistOffer.is_deleted == False,
            )
            .with_for_update()
            .all()
        )
        active_entry_ids = set()
        for offer in pending_offers:
            if offer.expires_at > now:
                active_entry_ids.add(offer.waitlist_entry_id)
            else:
                offer.status = "expired"
        offered_entry_ids = set(active_entry_ids)
        offered_slot_ids = {
            offer.availability_id for offer in pending_offers if offer.expires_at > now
        }
        services = {
            service.id: service
            for service in db.query(Service)
            .filter(
                Service.barbershop_id == shop.id,
                Service.is_active == True,
                Service.is_deleted == False,
            )
            .all()
        }
        today = _business_date(now, shop)
        slots = (
            db.query(BarberAvailability)
            .filter(
                BarberAvailability.barbershop_id == shop.id,
                BarberAvailability.is_active == True,
                BarberAvailability.is_booked == False,
                BarberAvailability.is_deleted == False,
                BarberAvailability.slot_start > now,
                BarberAvailability.slot_start <= now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS),
            )
            .order_by(BarberAvailability.slot_start, BarberAvailability.id)
            .limit(AUTOMATIC_SLOT_BATCH)
            .with_for_update(skip_locked=True)
            .all()
        )

        if not slots:
            continue
        barber_ids = {slot.barber_id for slot in slots}
        barbers = {
            barber.id: barber
            for barber in db.query(User)
            .filter(
                User.id.in_(barber_ids),
                User.barbershop_id == shop.id,
                User.role == "barber",
                User.is_active == True,
                User.is_deleted == False,
            )
            .all()
        }
        first_start = min(slot.slot_start for slot in slots)
        last_end = max(slot.slot_end for slot in slots)
        appointments_by_barber: dict[int, list[Appointment]] = {}
        for appointment in (
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
            .with_for_update()
            .all()
        ):
            appointments_by_barber.setdefault(appointment.barber_id, []).append(appointment)
        blocks_by_barber: dict[int, list[BarberAvailabilityBlock]] = {}
        for block in (
            db.query(BarberAvailabilityBlock)
            .filter(
                BarberAvailabilityBlock.barbershop_id == shop.id,
                BarberAvailabilityBlock.barber_id.in_(barber_ids),
                BarberAvailabilityBlock.is_deleted == False,
                BarberAvailabilityBlock.starts_at < last_end,
                BarberAvailabilityBlock.ends_at > first_start,
            )
            .all()
        ):
            blocks_by_barber.setdefault(block.barber_id, []).append(block)
        closed_today_by_barber = {}

        for slot in slots:
            if remaining <= 0:
                break
            if slot.id in offered_slot_ids:
                continue
            barber = barbers.get(slot.barber_id)
            if not barber:
                continue
            if _business_date(slot.slot_start, shop) == today:
                is_closed = closed_today_by_barber.get(barber.id)
                if is_closed is None:
                    is_closed = _cash_closed_for_slot(db, shop, barber, slot, today)
                    closed_today_by_barber[barber.id] = is_closed
                if is_closed:
                    continue
            active_appointments = appointments_by_barber.get(barber.id, [])
            active_blocks = blocks_by_barber.get(barber.id, [])
            slot_date = _business_date(slot.slot_start, shop)
            match = None
            for entry in entries:
                if entry.id in offered_entry_ids:
                    continue
                service = services.get(entry.service_id)
                if (
                    not service
                    or (entry.barber_id and entry.barber_id != barber.id)
                    or (entry.preferred_date_start and slot_date < entry.preferred_date_start)
                    or (entry.preferred_date_end and slot_date > entry.preferred_date_end)
                    or slot_date < today
                    or slot_date > today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
                ):
                    continue
                if slot_available_for_duration(
                    slot,
                    active_blocks,
                    active_appointments,
                    service.duration_minutes,
                ):
                    match = entry
                    break
            if not match:
                continue
            try:
                offer = create_waitlist_offer(
                    db,
                    shop=shop,
                    entry=match,
                    slot=slot,
                    expires_in_minutes=DEFAULT_OFFER_MINUTES,
                    source="automatic",
                    now=now,
                )
            except ValueError:
                continue
            offered_entry_ids.add(match.id)
            offered_slot_ids.add(slot.id)
            remaining -= 1
            issued += 1

    if issued or db.dirty or db.new:
        db.commit()
    return issued
