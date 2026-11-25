"""Public booking, availability, and barber absence endpoints."""

from datetime import datetime, time, timedelta
import hashlib
import secrets
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.constants.enums import (
    MAX_ADVANCE_BOOKING_DAYS,
    MAX_SERVICE_DURATION_MINUTES,
)
from app.core.security.password import hash_password
from app.models.appointment import Appointment
from app.models.barber_availability import BarberAvailability
from app.models.barber_availability_block import BarberAvailabilityBlock
from app.models.barber_live_state import BarberLiveState
from app.models.barbershop import Barbershop
from app.models.client_account import ClientAccountShopLink
from app.models.payment import CashRegisterClose
from app.models.service import Service
from app.models.user import User
from app.schemas.platform import (
    BarberAbsenceRequest,
    BarberCreateSlotsRequest,
    BarberLiveStateUpdate,
    BarberShareLinkResponse,
    PublicAvailableSlotResponse,
    PublicBarbershopResponse,
    PublicCancelAppointmentRequest,
    PublicCreateAppointmentRequest,
    PublicCreateAppointmentResponse,
    PublicRescheduleAppointmentRequest,
    PublicServiceResponse,
    PublicTrackAppointmentItem,
    PublicTrackAppointmentRequest,
    PublicTrackAppointmentResponse,
    WalkInAppointmentRequest,
)
from app.services.subscription_service import count_monthly_appointments
from app.services.booking_policy import enforce_public_change_window
from app.services.customer_appointment_service import cancel_customer_appointment
from app.services.client_account_service import get_or_create_shop_client
from app.utils.datetime import local_day_start_utc_naive, utc_now_naive
from app.api.v1.endpoints.common import (
    _audit, _cash_register_closed_for_user, _ensure_barber_not_on_break, _get_current_user, _get_timezone,
    _normalize_phone, _require_active_subscription, _utc_aware,
)
from app.api.v1.endpoints.platform import (
    PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT, PUBLIC_TRACK_IP_LIMIT,
    _build_client_link, _consume_public_booking_quota,
    _consume_public_token_quota, _get_public_shop, _notify_appointment_staff,
    _parse_date_time, _public_booking_client_ip, _queue_appointment_email,
    _queue_appointment_whatsapp, _slot_available_for_duration, _to_utc_naive,
)

router = APIRouter(tags=["platform"])


@router.get("/barber/live-status")
def barber_live_status(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Return the authenticated barber's explicit operational presence."""
    barber = _get_current_user(db, authorization)
    if barber.role != "barber" or not barber.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el barbero puede consultar su estado")
    state = db.query(BarberLiveState).filter(
        BarberLiveState.barber_id == barber.id,
        BarberLiveState.barbershop_id == barber.barbershop_id,
        BarberLiveState.is_deleted == False,
    ).first()
    return {
        "state": state.state if state else "available",
        "expected_return_at": state.expected_return_at if state else None,
    }


@router.put("/barber/live-status")
def update_barber_live_status(
    data: BarberLiveStateUpdate,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Allow a barber to pause/resume availability without altering bookings."""
    barber = _get_current_user(db, authorization)
    if barber.role != "barber" or not barber.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el barbero puede cambiar su estado")
    locked_barber = db.query(User).filter(
        User.id == barber.id,
        User.barbershop_id == barber.barbershop_id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not locked_barber:
        raise HTTPException(status_code=403, detail="El perfil de barbero no está activo")
    shop = db.query(Barbershop).filter(
        Barbershop.id == locked_barber.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)

    if data.state == "on_break":
        active_appointment = db.query(Appointment.id).filter(
            Appointment.barbershop_id == shop.id,
            Appointment.barber_id == locked_barber.id,
            Appointment.status == "in_progress",
            Appointment.is_deleted == False,
        ).with_for_update().first()
        if active_appointment:
            raise HTTPException(
                status_code=409,
                detail="Finaliza el servicio en curso antes de iniciar un descanso",
            )

    live_state = db.query(BarberLiveState).filter(
        BarberLiveState.barber_id == locked_barber.id,
    ).with_for_update().first()
    if live_state:
        live_state.barbershop_id = shop.id
        live_state.state = data.state
        live_state.expected_return_at = (
            utc_now_naive() + timedelta(minutes=data.break_duration_minutes)
            if data.state == "on_break" else None
        )
        live_state.is_deleted = False
        live_state.deleted_at = None
    else:
        live_state = BarberLiveState(
            barbershop_id=shop.id, barber_id=locked_barber.id, state=data.state,
            expected_return_at=(
                utc_now_naive() + timedelta(minutes=data.break_duration_minutes)
                if data.state == "on_break" else None
            ),
        )
        db.add(live_state)
    db.flush()
    _audit(
        db, locked_barber, "barber.live_state_updated", "barber_live_state",
        live_state.id, shop.id, {
            "state": data.state,
            "expected_return_at": live_state.expected_return_at.isoformat()
            if live_state.expected_return_at else None,
        },
    )
    db.commit()
    return {"state": data.state, "expected_return_at": live_state.expected_return_at}

@router.get("/public/{slug}", response_model=PublicBarbershopResponse)
def public_barbershop(slug: str, db: Session = Depends(get_db)):
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)

    return PublicBarbershopResponse(
        id=shop.id,
        name=shop.name,
        slug=shop.slug,
        currency=shop.currency,
        timezone=shop.timezone,
        phone=shop.phone,
        address_line1=shop.address_line1,
        city=shop.city,
        state=shop.state,
        opening_time=shop.opening_time,
        closing_time=shop.closing_time,
        logo_url=shop.logo_url,
        cover_image_url=shop.cover_image_url,
        description=shop.description,
        gallery_images=shop.gallery_images or [],
        booking_questions=shop.booking_questions or [],
        team=[
            {"id": barber.id, "name": barber.full_name,
             "bio": barber.bio, "avatar_url": barber.avatar_url}
            for barber in db.query(User).filter(
                User.barbershop_id == shop.id,
                User.role == "barber",
                User.is_active == True,
                User.is_deleted == False,
            ).order_by(User.first_name.asc(), User.last_name.asc())
        ],
        primary_color=shop.primary_color,
        secondary_color=shop.secondary_color,
        public_theme=shop.public_theme or "light",
        cancellation_window_hours=shop.cancellation_window_hours or 0,
        client_app_link=_build_client_link(shop.slug),
    )

@router.get("/public/{slug}/services", response_model=list[PublicServiceResponse])
def public_services(slug: str, db: Session = Depends(get_db)):
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)

    services = (
        db.query(Service)
        .filter(Service.barbershop_id == shop.id, Service.is_active == True, Service.is_deleted == False)
        .order_by(Service.display_order.asc(), Service.id.asc())
        .all()
    )

    return [
        PublicServiceResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            duration_minutes=s.duration_minutes,
            price_cents=s.price,
            category=s.category,
            image_url=s.image_url,
        )
        for s in services
    ]

@router.get("/public/{slug}/slots", response_model=list[PublicAvailableSlotResponse])
def public_slots(
    slug: str,
    duration_minutes: Optional[int] = Query(
        default=None, ge=10, le=MAX_SERVICE_DURATION_MINUTES,
    ),
    db: Session = Depends(get_db),
):
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)

    if duration_minutes is None:
        duration_minutes = db.query(func.min(Service.duration_minutes)).filter(
            Service.barbershop_id == shop.id,
            Service.is_active == True,
            Service.is_deleted == False,
        ).scalar()
    if duration_minutes is None:
        return []

    now = utc_now_naive()
    horizon = now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
    rows = (
        db.query(BarberAvailability)
        .join(User, User.id == BarberAvailability.barber_id)
        .filter(
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_active == True,
            BarberAvailability.is_booked == False,
            BarberAvailability.slot_start >= now,
            BarberAvailability.slot_start <= horizon,
            BarberAvailability.is_deleted == False,
            User.is_active == True,
            User.is_deleted == False,
            User.role == "barber",
            User.barbershop_id == shop.id,
        )
        .order_by(BarberAvailability.slot_start.asc())
        .all()
    )

    business_date = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    business_date_key = datetime.combine(business_date, time.min)
    business_timezone = _get_timezone(shop)
    business_day_start = local_day_start_utc_naive(business_date, business_timezone)
    business_day_end = local_day_start_utc_naive(business_date + timedelta(days=1), business_timezone)
    closing_rows = db.query(CashRegisterClose.closed_by_user_id, User.role).join(
        User, User.id == CashRegisterClose.closed_by_user_id,
    ).filter(
        CashRegisterClose.barbershop_id == shop.id,
        CashRegisterClose.business_date == business_date_key,
        CashRegisterClose.is_deleted == False,
        User.is_deleted == False,
    ).all()
    owner_closed = any(role == "barbershop_owner" for _, role in closing_rows)
    closed_barbers = {
        user_id for user_id, role in closing_rows if role == "barber"
    }
    if owner_closed or closed_barbers:
        rows = [
            slot for slot in rows
            if not (
                business_day_start <= slot.slot_start < business_day_end
                and (owner_closed or slot.barber_id in closed_barbers)
            )
        ]

    blocks = db.query(BarberAvailabilityBlock).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.starts_at < horizon,
        BarberAvailabilityBlock.ends_at > now,
        BarberAvailabilityBlock.is_deleted == False,
    ).all()
    blocks_by_barber: dict[int, list[BarberAvailabilityBlock]] = {}
    for block in blocks:
        blocks_by_barber.setdefault(block.barber_id, []).append(block)

    appointments = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.status.in_(["pending", "confirmed", "in_progress"]),
        Appointment.scheduled_time >= now - timedelta(minutes=MAX_SERVICE_DURATION_MINUTES),
        Appointment.scheduled_time < horizon,
        Appointment.is_deleted == False,
    ).all()
    appointments_by_barber: dict[int, list[Appointment]] = {}
    for appointment in appointments:
        appointments_by_barber.setdefault(appointment.barber_id, []).append(appointment)

    rows = [
        slot for slot in rows
        if _slot_available_for_duration(
            slot,
            blocks_by_barber.get(slot.barber_id, []),
            appointments_by_barber.get(slot.barber_id, []),
            duration_minutes,
        )
    ]

    return [
        PublicAvailableSlotResponse(
            availability_id=r.id,
            barber_id=r.barber_id,
            barber_name=r.barber.full_name if r.barber else f"Barbero {r.barber_id}",
            slot_start=_utc_aware(r.slot_start),
            slot_end=_utc_aware(r.slot_end),
        )
        for r in rows
    ]

@router.post("/public/{slug}/appointments", response_model=PublicCreateAppointmentResponse)
def public_create_appointment(
    slug: str,
    data: PublicCreateAppointmentRequest,
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)
    source_ip = _public_booking_client_ip(request)
    _consume_public_booking_quota(db, shop.id, source_ip, utc_now_naive())
    shop = db.query(Barbershop).filter(
        Barbershop.id == shop.id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    subscription = _require_active_subscription(db, shop, lock=True)
    supported_booking_questions = {
        "Estilo buscado", "Largo actual", "Acabado preferido", "Referencia del cliente",
    }
    supported_booking_questions.update(
        question.strip() for question in (shop.booking_questions or [])
        if isinstance(question, str) and question.strip()
    )
    if set(data.booking_answers) - supported_booking_questions:
        raise HTTPException(
            status_code=422,
            detail="Las preguntas de reserva cambiaron; actualiza la página e inténtalo de nuevo",
        )
    if subscription.max_appointments_per_month is not None:
        used = count_monthly_appointments(db, shop)
        if used >= subscription.max_appointments_per_month:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de citas de su plan")

    account_user = None
    if authorization:
        account_user = _get_current_user(db, authorization)
        if account_user.role != "client" or account_user.barbershop_id is not None or not account_user.is_verified:
            raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")
    elif not data.client_name or not data.phone:
        raise HTTPException(status_code=422, detail="El nombre y el teléfono son necesarios para reservar como invitado")

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
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    scheduled_time = _to_utc_naive(data.scheduled_time, shop)
    if scheduled_time > utc_now_naive() + timedelta(days=MAX_ADVANCE_BOOKING_DAYS):
        raise HTTPException(status_code=422, detail="La reserva supera el plazo máximo permitido")

    # El cliente solo puede reservar turnos configurados por el barbero y no vencidos.
    slot_query = db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.is_active == True,
        BarberAvailability.is_booked == False,
        BarberAvailability.slot_start == scheduled_time,
        BarberAvailability.slot_start >= utc_now_naive(),
        BarberAvailability.is_deleted == False,
    )
    if data.barber_id is not None:
        slot_query = slot_query.filter(BarberAvailability.barber_id == data.barber_id)
    slot = slot_query.order_by(BarberAvailability.barber_id.asc(), BarberAvailability.id.asc()).first()

    if not slot:
        raise HTTPException(status_code=400, detail="Ese turno no está disponible")

    slot_duration = slot.slot_end - slot.slot_start
    if slot_duration < timedelta(minutes=service.duration_minutes):
        raise HTTPException(status_code=409, detail="El turno no tiene duración suficiente para este servicio")

    booking_business_date = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    scheduled_business_date = _utc_aware(scheduled_time).astimezone(_get_timezone(shop)).date()
    barber = db.query(User).filter(
        User.id == slot.barber_id,
        User.barbershop_id == shop.id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=400, detail="El barbero del turno no está disponible")

    if scheduled_business_date == booking_business_date:
        shop = db.query(Barbershop).filter(
            Barbershop.id == shop.id,
            Barbershop.is_deleted == False,
        ).with_for_update().first()
        if not shop:
            raise HTTPException(status_code=404, detail="Barbería no encontrada")
        if _cash_register_closed_for_user(
            db, barber, shop.id, datetime.combine(booking_business_date, time.min),
        ):
            raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se aceptan reservas para hoy")

    blocked_range = db.query(BarberAvailabilityBlock.id).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.barber_id == barber.id,
        BarberAvailabilityBlock.starts_at < scheduled_time + timedelta(minutes=service.duration_minutes),
        BarberAvailabilityBlock.ends_at > scheduled_time,
        BarberAvailabilityBlock.is_deleted == False,
    ).first()
    if blocked_range:
        raise HTTPException(status_code=409, detail="El turno coincide con una ausencia del barbero")

    appointment_start = slot.slot_start
    appointment_end = appointment_start + timedelta(minutes=service.duration_minutes)
    existing_appointments = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.barber_id == barber.id,
        Appointment.status.in_(["pending", "confirmed", "in_progress"]),
        Appointment.is_deleted == False,
    ).with_for_update().all()
    if any(
        existing.scheduled_time < appointment_end
        and existing.scheduled_time + timedelta(minutes=existing.estimated_duration) > appointment_start
        for existing in existing_appointments
    ):
        raise HTTPException(status_code=409, detail="El barbero ya tiene una cita en ese horario")

    if account_user:
        client = get_or_create_shop_client(db, account_user, shop, subscription)
        phone = client.phone or ""
    else:
        # The request schema allows identity-free bookings for authenticated customers;
        # the guest branch is guarded above and keeps both values mandatory.
        assert data.client_name is not None and data.phone is not None
        phone = _normalize_phone(data.phone)
        client = (
            db.query(User)
            .filter(
                User.phone == phone,
                User.barbershop_id == shop.id,
                User.role == "client",
                User.is_deleted == False,
            )
            .first()
        )
        if client and not client.is_active:
            raise HTTPException(status_code=409, detail="El cliente está desactivado en esta barbería")

        if not client:
            if subscription.max_clients is not None:
                client_count = db.query(User.id).filter(
                    User.barbershop_id == shop.id,
                    User.role == "client",
                    User.is_deleted == False,
                ).count()
                if client_count >= subscription.max_clients:
                    raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de clientes de su plan")
            name_parts = data.client_name.strip().split(" ")
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:]).strip() or "Cliente"
            # Guest bookings use an undeliverable address and never claim email verification.
            synthetic_email = f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid"

            client = User(
                email=synthetic_email,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                first_name=first_name,
                last_name=last_name,
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
        scheduled_time=appointment_start,
        estimated_duration=service.duration_minutes,
        service_type=service.name,
        service_price=service.price,
        status="pending",
        client_notes=data.notes,
        booking_answers=data.booking_answers or None,
        tracking_token_hash=hashlib.sha256(tracking_token.encode("utf-8")).hexdigest(),
    )
    db.add(appointment)
    # Claim the slot with compare-and-set so simultaneous requests cannot both book it.
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
        raise HTTPException(status_code=409, detail="Ese turno acaba de ser reservado")
    local_appointment_time = _utc_aware(appointment_start).astimezone(_get_timezone(shop))
    db.flush()
    _notify_appointment_staff(
        db, appointment, "appointment_booked", "Nueva cita reservada",
        f"{client.full_name} · {service.name} · {local_appointment_time.strftime('%d/%m/%Y %H:%M')}",
    )
    _audit(
        db, None, "appointment.booked", "appointment", appointment.id, shop.id,
        {"barber_id": barber.id, "service_id": service.id,
         "scheduled_time": appointment_start.isoformat()},
    )
    tracking_link = f"{_build_client_link(shop.slug)}&{urlencode({'track_token': tracking_token})}"

    local_appointment_time = _utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop))
    wa_message = (
        f"💈 *{shop.name}*\n"
        f"Hola {client.full_name}, tu cita fue registrada.\n"
        f"📅 {local_appointment_time.strftime('%d/%m/%Y %H:%M')}\n"
        f"✂️ {service.name}\n"
        f"🔎 Seguimiento: {tracking_link}"
    )
    _queue_appointment_email(db, appointment, "booking_received")
    _queue_appointment_whatsapp(db, appointment, phone, wa_message, "confirmation:client", recipient_user_id=client.id)

    # Notificación al barbero (WhatsApp)
    barber_phone = barber.phone or ""
    if barber_phone:
        barber_msg = (
            f"🔔 *Nueva cita registrada*\n"
            f"Barbería: {shop.name}\n"
            f"Cliente: {client.full_name} ({phone})\n"
            f"Servicio: {service.name}\n"
            f"Hora: {local_appointment_time.strftime('%d/%m/%Y %H:%M')}\n"
            f"Estado: {appointment.status}"
        )
        _queue_appointment_whatsapp(db, appointment, barber_phone, barber_msg, "confirmation:barber", recipient_user_id=barber.id)

    db.commit()
    db.refresh(appointment)

    return PublicCreateAppointmentResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        tracking_link=tracking_link,
        message="Cita agendada correctamente",
        saved_to_account=account_user is not None,
    )

@router.post("/barber/appointments/walk-in", status_code=201)
def create_walk_in_appointment(
    data: WalkInAppointmentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Start an in-person appointment without requiring a prior availability slot."""
    user = _get_current_user(db, authorization)
    if user.role not in {"barber", "barbershop_owner"} or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado para registrar turnos presenciales")

    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    subscription = _require_active_subscription(db, shop, lock=True)
    if subscription.max_appointments_per_month is not None:
        used = count_monthly_appointments(db, shop)
        if used >= subscription.max_appointments_per_month:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite mensual de citas")

    if user.role == "barber":
        if data.barber_id is not None and data.barber_id != user.id:
            raise HTTPException(status_code=403, detail="Solo puedes iniciar turnos presenciales para ti")
        barber_id = user.id
    else:
        if data.barber_id is None:
            raise HTTPException(status_code=422, detail="Selecciona el barbero que atenderá al cliente")
        barber_id = data.barber_id

    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == shop.id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado o inactivo")
    _ensure_barber_not_on_break(db, barber.id, shop.id)
    shop = db.query(Barbershop).filter(
        Barbershop.id == shop.id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    business_day = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    if _cash_register_closed_for_user(
        db, barber, shop.id, datetime.combine(business_day, time.min),
    ):
        raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se pueden iniciar servicios nuevos")
    if subscription.max_barbers is not None:
        active_barbers = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_active == True,
            User.is_deleted == False,
        ).count()
        if active_barbers > subscription.max_barbers:
            raise HTTPException(status_code=402, detail="La barbería superó el límite de barberos del plan")

    service = db.query(Service).filter(
        Service.id == data.service_id,
        Service.barbershop_id == shop.id,
        Service.is_active == True,
        Service.is_deleted == False,
    ).with_for_update().first()
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    now = utc_now_naive()
    service_end = now + timedelta(minutes=service.duration_minutes)
    existing = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.barber_id == barber.id,
        Appointment.status.in_({"pending", "confirmed", "in_progress"}),
        Appointment.scheduled_time < service_end,
        Appointment.is_deleted == False,
    ).with_for_update().all()
    if any(
        appointment.scheduled_time + timedelta(minutes=appointment.estimated_duration) > now
        for appointment in existing
    ):
        raise HTTPException(status_code=409, detail="El barbero ya tiene una cita activa en este horario")

    phone = _normalize_phone(data.phone)
    client = db.query(User).filter(
        User.phone == phone,
        User.barbershop_id == shop.id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if client and not client.is_active:
        raise HTTPException(status_code=409, detail="El cliente está desactivado en esta barbería")
    if not client:
        if subscription.max_clients is not None:
            client_count = db.query(User.id).filter(
                User.barbershop_id == shop.id,
                User.role == "client",
                User.is_deleted == False,
            ).count()
            if client_count >= subscription.max_clients:
                raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de clientes del plan")
        name_parts = data.client_name.split()
        client = User(
            email=f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            first_name=name_parts[0],
            last_name=" ".join(name_parts[1:]) or "Cliente",
            phone=phone,
            role="client",
            is_active=True,
            is_verified=False,
            barbershop_id=shop.id,
        )
        db.add(client)
        db.flush()

    appointment = Appointment(
        barbershop_id=shop.id,
        client_id=client.id,
        barber_id=barber.id,
        scheduled_time=now,
        estimated_duration=service.duration_minutes,
        service_type=service.name,
        service_price=service.price,
        status="in_progress",
        actual_start_time=now,
        client_notes="Turno presencial",
    )
    db.add(appointment)
    db.flush()
    _notify_appointment_staff(
        db, appointment, "appointment_walk_in", "Turno presencial iniciado",
        f"{client.full_name} · {service.name}", exclude_user_id=user.id,
    )
    _audit(db, user, "appointment.walk_in_started", "appointment", appointment.id, shop.id,
           {"barber_id": barber.id, "service_id": service.id, "client_id": client.id})
    if phone:
        _queue_appointment_whatsapp(
            db, appointment, phone,
            f"💈 {shop.name}: comenzamos tu servicio de {service.name} con {barber.full_name}.",
            "walk_in_started:client",
            recipient_user_id=client.id,
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo registrar el turno presencial") from exc

    return {
        "success": True,
        "appointment_id": appointment.id,
        "status": appointment.status,
        "client_name": client.full_name,
        "barber_name": barber.full_name,
        "service_type": service.name,
        "service_price_cents": service.price,
        "currency": shop.currency,
    }

@router.post("/barber/slots")
def barber_create_slots(
    data: BarberCreateSlotsRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role != "barber":
        raise HTTPException(status_code=403, detail="Solo cada barbero puede administrar su disponibilidad")
    if not user.barbershop_id:
        raise HTTPException(status_code=400, detail="Usuario sin barbería asignada")

    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    subscription = _require_active_subscription(db, shop)
    if subscription.max_barbers is not None:
        barber_count = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_active == True,
            User.is_deleted == False,
        ).count()
        if barber_count > subscription.max_barbers:
            raise HTTPException(status_code=402, detail="La barbería superó el límite de barberos del plan")

    # Serialize slot creation with itself and with public booking, both of which
    # lock this barber row before changing availability for the barber.
    barber_lock = db.query(User.id).filter(
        User.id == user.id,
        User.barbershop_id == shop.id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber_lock:
        raise HTTPException(status_code=403, detail="El barbero no está activo")

    local_start = _parse_date_time(data.date, data.start_time)
    local_end = _parse_date_time(data.date, data.end_time)

    if local_end <= local_start:
        raise HTTPException(status_code=400, detail="Rango de horario inválido")
    if shop.opening_time and local_start.time() < shop.opening_time:
        raise HTTPException(status_code=422, detail="El turno comienza antes de la apertura de la barbería")
    if shop.closing_time and local_end.time() > shop.closing_time:
        raise HTTPException(status_code=422, detail="El turno termina después del cierre de la barbería")
    start_dt = _to_utc_naive(local_start, shop)
    end_dt = _to_utc_naive(local_end, shop)
    now = utc_now_naive()
    business_date = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    if local_start.date() == business_date:
        locked_shop = db.query(Barbershop).filter(
            Barbershop.id == shop.id,
            Barbershop.is_deleted == False,
        ).with_for_update().first()
        if not locked_shop:
            raise HTTPException(status_code=404, detail="Barbería no encontrada")
        if _cash_register_closed_for_user(
            db, user, shop.id, datetime.combine(business_date, time.min),
        ):
            raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se puede agregar disponibilidad para hoy")
    if (
        start_dt <= now
        or start_dt > now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
        or end_dt > now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS + 1)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"La disponibilidad debe estar dentro de los próximos {MAX_ADVANCE_BOOKING_DAYS} días",
        )

    overlapping_absence = db.query(BarberAvailabilityBlock.id).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.barber_id == user.id,
        BarberAvailabilityBlock.starts_at < end_dt,
        BarberAvailabilityBlock.ends_at > start_dt,
        BarberAvailabilityBlock.is_deleted == False,
    ).first()
    if overlapping_absence:
        raise HTTPException(status_code=409, detail="No se pueden crear turnos dentro de una ausencia registrada")

    created = 0
    cursor = start_dt
    while cursor < end_dt:
        slot_end = cursor + timedelta(minutes=data.slot_minutes)
        if slot_end > end_dt:
            break

        overlap = (
            db.query(BarberAvailability)
            .filter(
                BarberAvailability.barber_id == user.id,
                BarberAvailability.barbershop_id == shop.id,
                BarberAvailability.slot_start < slot_end,
                BarberAvailability.slot_end > cursor,
                BarberAvailability.is_active == True,
                BarberAvailability.is_deleted == False,
            )
            .first()
        )
        if overlap and (overlap.slot_start != cursor or overlap.slot_end != slot_end):
            raise HTTPException(status_code=409, detail="El horario se cruza con una disponibilidad existente")
        if not overlap:
            db.add(
                BarberAvailability(
                    barbershop_id=user.barbershop_id,
                    barber_id=user.id,
                    slot_start=cursor,
                    slot_end=slot_end,
                    is_active=True,
                    is_booked=False,
                )
            )
            created += 1

        cursor = slot_end

    if created:
        _audit(
            db, user, "availability.slots_created", "barber_availability", None,
            user.barbershop_id,
            {"date": data.date, "start_time": data.start_time, "end_time": data.end_time,
             "slot_minutes": data.slot_minutes, "created_slots": created},
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El horario acaba de cambiar; vuelve a consultar tu agenda") from exc
    return {"success": True, "created_slots": created}

@router.get("/barber/absences")
def barber_list_absences(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role != "barber" or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo un barbero puede consultar sus ausencias")
    rows = db.query(BarberAvailabilityBlock).filter(
        BarberAvailabilityBlock.barbershop_id == user.barbershop_id,
        BarberAvailabilityBlock.barber_id == user.id,
        BarberAvailabilityBlock.ends_at > utc_now_naive(),
        BarberAvailabilityBlock.is_deleted == False,
    ).order_by(BarberAvailabilityBlock.starts_at.asc()).limit(100).all()
    return [{
        "id": row.id,
        "starts_at": _utc_aware(row.starts_at),
        "ends_at": _utc_aware(row.ends_at),
        "reason": row.reason,
    } for row in rows]

@router.post("/barber/absences", status_code=201)
def barber_create_absence(
    data: BarberAbsenceRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Block a barber's future range without silently canceling existing appointments."""
    user = _get_current_user(db, authorization)
    if user.role != "barber" or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo un barbero puede registrar su propia ausencia")

    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)

    barber = db.query(User).filter(
        User.id == user.id,
        User.barbershop_id == shop.id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=403, detail="El barbero no está activo")

    local_start = _parse_date_time(data.date, data.start_time)
    local_end = _parse_date_time(data.date, data.end_time)
    if local_end <= local_start:
        raise HTTPException(status_code=422, detail="El fin de la ausencia debe ser posterior al inicio")
    start_dt = _to_utc_naive(local_start, shop)
    end_dt = _to_utc_naive(local_end, shop)
    now = utc_now_naive()
    if start_dt <= now or end_dt > now + timedelta(days=MAX_ADVANCE_BOOKING_DAYS + 1):
        raise HTTPException(
            status_code=422,
            detail=f"La ausencia debe estar dentro de los próximos {MAX_ADVANCE_BOOKING_DAYS} días",
        )

    duplicate = db.query(BarberAvailabilityBlock.id).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.barber_id == barber.id,
        BarberAvailabilityBlock.starts_at < end_dt,
        BarberAvailabilityBlock.ends_at > start_dt,
        BarberAvailabilityBlock.is_deleted == False,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="El rango coincide con una ausencia ya registrada")

    active_appointments = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.barber_id == barber.id,
        Appointment.status.in_(["pending", "confirmed", "in_progress"]),
        Appointment.scheduled_time >= start_dt - timedelta(days=1),
        Appointment.scheduled_time < end_dt,
        Appointment.is_deleted == False,
    ).with_for_update().all()
    conflicts = [appointment for appointment in active_appointments if (
        appointment.scheduled_time + timedelta(minutes=appointment.estimated_duration) > start_dt
    )]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=f"Hay {len(conflicts)} cita(s) en ese rango. Reprográmalas o cancélalas antes de registrar la ausencia.",
        )

    slots = db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.barber_id == barber.id,
        BarberAvailability.slot_start < end_dt,
        BarberAvailability.slot_end > start_dt,
        BarberAvailability.is_active == True,
        BarberAvailability.is_deleted == False,
    ).with_for_update().all()
    if any(slot.is_booked for slot in slots):
        raise HTTPException(status_code=409, detail="Hay turnos reservados en ese rango; gestiona esas citas primero")

    block = BarberAvailabilityBlock(
        barbershop_id=shop.id,
        barber_id=barber.id,
        starts_at=start_dt,
        ends_at=end_dt,
        reason=data.reason,
    )
    db.add(block)
    db.flush()
    _audit(db, barber, "availability.absence_registered", "barber_availability_block", block.id,
           shop.id, {"starts_at": start_dt.isoformat(), "ends_at": end_dt.isoformat(),
                     "affected_slots": len(slots)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="La disponibilidad cambió; vuelve a consultar tu agenda") from exc
    return {"success": True, "absence_id": block.id, "affected_slots": len(slots)}

@router.delete("/barber/absences/{absence_id}")
def barber_cancel_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role != "barber" or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo un barbero puede cancelar sus ausencias")
    barber = db.query(User).filter(
        User.id == user.id,
        User.barbershop_id == user.barbershop_id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=403, detail="El barbero no está activo")
    block = db.query(BarberAvailabilityBlock).filter(
        BarberAvailabilityBlock.id == absence_id,
        BarberAvailabilityBlock.barbershop_id == barber.barbershop_id,
        BarberAvailabilityBlock.barber_id == barber.id,
        BarberAvailabilityBlock.is_deleted == False,
    ).with_for_update().first()
    if not block:
        raise HTTPException(status_code=404, detail="Ausencia no encontrada")
    block.soft_delete()
    _audit(db, barber, "availability.absence_cancelled", "barber_availability_block", block.id,
           barber.barbershop_id, {"starts_at": block.starts_at.isoformat(), "ends_at": block.ends_at.isoformat()})
    db.commit()
    return {"success": True, "absence_id": block.id, "cancelled": True}

@router.post("/public/{slug}/track", response_model=PublicTrackAppointmentResponse)
def public_track_appointments(
    slug: str,
    data: PublicTrackAppointmentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _consume_public_token_quota(
        db, "track", _public_booking_client_ip(request), utc_now_naive(), PUBLIC_TRACK_IP_LIMIT,
    )

    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop.id,
            Appointment.tracking_token_hash == token_hash,
            Appointment.is_deleted == False,
        )
        .first()
    )
    if not appointment:
        return PublicTrackAppointmentResponse(items=[])

    now = utc_now_naive()
    return PublicTrackAppointmentResponse(items=[
        PublicTrackAppointmentItem(
            appointment_id=appointment.id,
            status=appointment.status,
            scheduled_time=_utc_aware(appointment.scheduled_time),
            service_type=appointment.service_type,
            barber_name=appointment.barber.full_name if appointment.barber else None,
            estimated_duration=appointment.estimated_duration,
            checked_in_at=_utc_aware(appointment.checked_in_at) if appointment.checked_in_at else None,
            check_in_available=(
                appointment.status == "confirmed"
                and now >= appointment.scheduled_time - timedelta(minutes=60)
                and now <= appointment.scheduled_time + timedelta(minutes=30)
            ),
            **_public_queue_estimate(db, appointment, now),
        )
    ])


def _public_queue_estimate(db: Session, appointment: Appointment, now: datetime) -> dict:
    """Return an approximate private queue position without exposing other clients."""
    if not appointment.checked_in_at and appointment.status != "in_progress":
        return {"queue_position": None, "estimated_wait_minutes": None}
    ahead = db.query(Appointment).filter(
        Appointment.barbershop_id == appointment.barbershop_id,
        Appointment.barber_id == appointment.barber_id,
        Appointment.is_deleted == False,
        Appointment.id != appointment.id,
        Appointment.status.in_(("confirmed", "in_progress")),
        Appointment.scheduled_time <= appointment.scheduled_time,
    ).all()
    ahead = [row for row in ahead if row.status == "in_progress" or row.checked_in_at is not None]
    ahead.sort(key=lambda row: (row.scheduled_time, row.id))
    ahead = [row for row in ahead if (row.scheduled_time, row.id) < (appointment.scheduled_time, appointment.id)]
    live_state = db.query(BarberLiveState).filter(
        BarberLiveState.barbershop_id == appointment.barbershop_id,
        BarberLiveState.barber_id == appointment.barber_id,
        BarberLiveState.is_deleted == False,
    ).first()
    if live_state and live_state.state == "on_break" and appointment.status != "in_progress":
        expected_return_at = live_state.expected_return_at
        if expected_return_at:
            if expected_return_at <= now:
                return {
                    "queue_position": len(ahead) + 1,
                    "estimated_wait_minutes": None,
                    "queue_estimate_note": "La hora prevista de regreso ya pasó; la barbería debe confirmar el retorno.",
                }
            break_remaining = max(0, int((expected_return_at - now).total_seconds() // 60))
            cursor = max(now, expected_return_at)
            for row in ahead:
                if row.status == "in_progress" and row.actual_start_time:
                    cursor = max(
                        cursor,
                        row.actual_start_time + timedelta(minutes=row.estimated_duration),
                    )
                else:
                    cursor = max(cursor, row.scheduled_time) + timedelta(
                        minutes=max(0, row.estimated_duration or 0)
                    )
            wait = max(0, int((max(cursor, appointment.scheduled_time) - now).total_seconds() // 60))
            return {
                "queue_position": len(ahead) + 1,
                "estimated_wait_minutes": wait,
                "queue_estimate_note": "Espera aproximada; el barbero indicó su hora estimada de regreso.",
            }
        return {
            "queue_position": len(ahead) + 1,
            "estimated_wait_minutes": None,
            "queue_estimate_note": "El barbero está en descanso; actualizaremos la espera cuando vuelva.",
        }
    wait = 0
    for row in ahead:
        if row.status == "in_progress" and row.actual_start_time:
            remaining = max(0, int((row.actual_start_time + timedelta(minutes=row.estimated_duration) - now).total_seconds() // 60))
            wait += remaining
        else:
            wait += max(0, int(row.estimated_duration or 0))
    wait = max(wait, max(0, int((appointment.scheduled_time - now).total_seconds() // 60)))
    return {"queue_position": len(ahead) + 1, "estimated_wait_minutes": wait}


@router.post("/public/{slug}/appointments/check-in")
def public_check_in_appointment(
    slug: str,
    data: PublicTrackAppointmentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Let a customer privately confirm arrival near their appointment time."""
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _consume_public_token_quota(
        db, "appointment-change", _public_booking_client_ip(request),
        utc_now_naive(), PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT,
    )
    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    appointment = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.tracking_token_hash == token_hash,
        Appointment.is_deleted == False,
    ).with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.status != "confirmed":
        raise HTTPException(status_code=409, detail="El check-in está disponible para citas confirmadas")
    now = utc_now_naive()
    if now < appointment.scheduled_time - timedelta(minutes=60) or now > appointment.scheduled_time + timedelta(minutes=30):
        raise HTTPException(status_code=409, detail="El check-in está disponible desde 60 minutos antes hasta 30 minutos después de la cita")
    if appointment.checked_in_at is None:
        appointment.checked_in_at = now
        _notify_appointment_staff(
            db, appointment, "appointment_checked_in", "Cliente llegó",
            f"El cliente confirmó su llegada para {appointment.service_type}.",
        )
        _audit(db, None, "appointment.checked_in_by_client", "appointment", appointment.id, shop.id, {})
    db.commit()
    return {"success": True, "checked_in_at": _utc_aware(appointment.checked_in_at)}

@router.post("/public/{slug}/appointments/cancel")
def public_cancel_appointment(
    slug: str,
    data: PublicCancelAppointmentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cancel a future booking by its private tracking token and release its slot."""
    shop = db.query(Barbershop).filter(
        Barbershop.slug == slug,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _consume_public_token_quota(
        db, "appointment-change", _public_booking_client_ip(request),
        utc_now_naive(), PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT,
    )

    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    appointment = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.tracking_token_hash == token_hash,
        Appointment.is_deleted == False,
    ).with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    now = utc_now_naive()
    cancel_customer_appointment(db, shop, appointment, data.reason, now)
    _notify_appointment_staff(
        db, appointment, "appointment_cancelled", "Cita cancelada por el cliente",
        f"{appointment.service_type} · {_utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')}",
    )
    _audit(db, None, "appointment.cancelled_by_client", "appointment", appointment.id,
           shop.id, {"reason": data.reason})
    _queue_appointment_email(db, appointment, "cancellation", data.reason)
    if appointment.client and not appointment.client.is_deleted and appointment.client.phone:
        _queue_appointment_whatsapp(
            db, appointment, appointment.client.phone,
            f"La cita en {shop.name} para {_utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')} fue cancelada.",
            "cancellation:client",
            recipient_user_id=appointment.client_id,
        )
    db.commit()
    return {"success": True, "appointment_id": appointment.id, "status": appointment.status}

@router.post("/public/{slug}/appointments/reschedule")
def public_reschedule_appointment(
    slug: str,
    data: PublicRescheduleAppointmentRequest,
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Move an appointment with its private token or verified account session."""
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _consume_public_token_quota(
        db, "appointment-change", _public_booking_client_ip(request),
        utc_now_naive(), PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT,
    )
    _require_active_subscription(db, shop, lock=True)

    account_user = None
    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest() if data.token else None
    if data.appointment_id is not None:
        account_user = _get_current_user(db, authorization)
        if (
            account_user.role != "client"
            or account_user.barbershop_id is not None
            or not account_user.is_verified
        ):
            raise HTTPException(
                status_code=403,
                detail="Se requiere una cuenta de cliente verificada",
            )
        appointment_ref_query = db.query(
            Appointment.id, Appointment.barber_id, Appointment.scheduled_time,
        ).join(
            ClientAccountShopLink,
            ClientAccountShopLink.crm_client_user_id == Appointment.client_id,
        ).filter(
            ClientAccountShopLink.account_user_id == account_user.id,
            ClientAccountShopLink.is_deleted == False,
            Appointment.id == data.appointment_id,
        )
    else:
        appointment_ref_query = db.query(
            Appointment.id, Appointment.barber_id, Appointment.scheduled_time,
        ).filter(
            Appointment.barbershop_id == shop.id,
            Appointment.tracking_token_hash == token_hash,
            Appointment.is_deleted == False,
        )
    appointment_ref = appointment_ref_query.filter(
        Appointment.barbershop_id == shop.id,
        Appointment.is_deleted == False,
    ).first()
    if not appointment_ref:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    slot_ref = db.query(BarberAvailability.barber_id, BarberAvailability.slot_start).filter(
        BarberAvailability.id == data.availability_id,
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.is_deleted == False,
    ).first()
    if not slot_ref:
        raise HTTPException(status_code=409, detail="El nuevo turno ya no está disponible")

    reschedule_business_date = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    changes_business_day = (
        _utc_aware(appointment_ref.scheduled_time).astimezone(_get_timezone(shop)).date()
        == reschedule_business_date
        or _utc_aware(slot_ref.slot_start).astimezone(_get_timezone(shop)).date()
        == reschedule_business_date
    )
    # Public bookings, service transitions, and cash close take locks in this
    # order: barber rows (when needed), shop mutex, then appointment rows.
    # Lock both barber rows in primary-key order before the appointment lock.
    barber_ids = sorted({appointment_ref.barber_id, slot_ref.barber_id})
    barbers_by_id = {}
    for barber_id in barber_ids:
        barber = db.query(User).filter(
            User.id == barber_id,
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_deleted == False,
        ).with_for_update().first()
        if barber:
            barbers_by_id[barber.id] = barber
    if len(barbers_by_id) != len(barber_ids):
        raise HTTPException(status_code=409, detail="El barbero asignado ya no está disponible")

    if changes_business_day:
        shop = db.query(Barbershop).filter(
            Barbershop.id == shop.id,
            Barbershop.is_deleted == False,
        ).with_for_update().first()
        if not shop:
            raise HTTPException(status_code=404, detail="Barbería no encontrada")

    appointment_query = db.query(Appointment).filter(
        Appointment.id == appointment_ref.id,
        Appointment.barbershop_id == shop.id,
        Appointment.is_deleted == False,
    )
    if token_hash:
        appointment_query = appointment_query.filter(Appointment.tracking_token_hash == token_hash)
    else:
        appointment_query = appointment_query.join(
            ClientAccountShopLink,
            ClientAccountShopLink.crm_client_user_id == Appointment.client_id,
        ).filter(
            ClientAccountShopLink.account_user_id == account_user.id,
            ClientAccountShopLink.is_deleted == False,
        )
    appointment = appointment_query.with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.barber_id != appointment_ref.barber_id:
        raise HTTPException(status_code=409, detail="La asignación de la cita cambió; vuelve a consultar")
    if appointment.status not in {"pending", "confirmed"} or appointment.scheduled_time <= utc_now_naive():
        raise HTTPException(status_code=409, detail="La cita ya no se puede reprogramar")
    enforce_public_change_window(shop, appointment.scheduled_time, utc_now_naive())

    new_slot = db.query(BarberAvailability).filter(
        BarberAvailability.id == data.availability_id,
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.is_active == True,
        BarberAvailability.is_booked == False,
        BarberAvailability.slot_start >= utc_now_naive(),
        BarberAvailability.slot_start <= utc_now_naive() + timedelta(days=MAX_ADVANCE_BOOKING_DAYS),
        BarberAvailability.is_deleted == False,
    ).with_for_update().first()
    if not new_slot:
        raise HTTPException(status_code=409, detail="El nuevo turno ya no está disponible")
    if new_slot.barber_id != slot_ref.barber_id:
        raise HTTPException(status_code=409, detail="El nuevo turno cambió; vuelve a consultar")
    if new_slot.slot_end - new_slot.slot_start < timedelta(minutes=appointment.estimated_duration):
        raise HTTPException(status_code=409, detail="El nuevo turno no tiene duración suficiente")

    barber = barbers_by_id[new_slot.barber_id]
    if not barber.is_active:
        raise HTTPException(status_code=409, detail="El nuevo barbero no está disponible")

    new_start = new_slot.slot_start
    new_end = new_start + timedelta(minutes=appointment.estimated_duration)
    if _utc_aware(new_start).astimezone(_get_timezone(shop)).date() == reschedule_business_date:
        if _cash_register_closed_for_user(
            db, barber, shop.id, datetime.combine(reschedule_business_date, time.min),
        ):
            raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se aceptan cambios de cita para hoy")
    blocked_range = db.query(BarberAvailabilityBlock.id).filter(
        BarberAvailabilityBlock.barbershop_id == shop.id,
        BarberAvailabilityBlock.barber_id == barber.id,
        BarberAvailabilityBlock.starts_at < new_end,
        BarberAvailabilityBlock.ends_at > new_start,
        BarberAvailabilityBlock.is_deleted == False,
    ).first()
    if blocked_range:
        raise HTTPException(status_code=409, detail="El nuevo turno coincide con una ausencia del barbero")

    other_appointments = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.barber_id == barber.id,
        Appointment.id != appointment.id,
        Appointment.status.in_(["pending", "confirmed", "in_progress"]),
        Appointment.is_deleted == False,
    ).with_for_update().all()
    if any(item.scheduled_time < new_end and
           item.scheduled_time + timedelta(minutes=item.estimated_duration) > new_start
           for item in other_appointments):
        raise HTTPException(status_code=409, detail="El barbero ya tiene una cita en ese horario")

    claimed = db.execute(update(BarberAvailability).where(
        BarberAvailability.id == new_slot.id,
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.is_booked == False,
        BarberAvailability.is_deleted == False,
    ).values(is_booked=True))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="El nuevo turno acaba de ser reservado")

    old_start = appointment.scheduled_time
    old_barber_id = appointment.barber_id
    reschedule_event_id = secrets.token_hex(12)
    db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.barber_id == old_barber_id,
        BarberAvailability.slot_start == old_start,
        BarberAvailability.is_booked == True,
        BarberAvailability.is_deleted == False,
    ).update({BarberAvailability.is_booked: False}, synchronize_session=False)
    appointment.scheduled_time = new_start
    appointment.checked_in_at = None
    appointment.barber_id = barber.id
    _notify_appointment_staff(
        db, appointment, "appointment_rescheduled", "Cita reprogramada",
        f"{appointment.service_type} · {_utc_aware(new_start).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')}",
        additional_barber_ids=(old_barber_id,),
        dedupe_suffix=reschedule_event_id,
    )
    _audit(db, account_user, "appointment.rescheduled_by_client", "appointment", appointment.id, shop.id,
           {"previous_time": old_start.isoformat(), "new_time": new_start.isoformat(),
            "previous_barber_id": old_barber_id, "new_barber_id": barber.id})
    if appointment.client and not appointment.client.is_deleted and appointment.client.phone:
        _queue_appointment_whatsapp(
            db, appointment, appointment.client.phone,
            f"Tu cita en {shop.name} fue reprogramada para "
            f"{_utc_aware(new_start).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')}.",
            "rescheduled:client",
            dedupe_suffix=reschedule_event_id,
            recipient_user_id=appointment.client_id,
        )
    _queue_appointment_email(db, appointment, "reschedule", dedupe_suffix=reschedule_event_id)
    db.commit()
    return {"success": True, "appointment_id": appointment.id, "status": appointment.status,
            "scheduled_time": _utc_aware(new_start), "barber_name": barber.full_name}

@router.get("/barber/share-link", response_model=BarberShareLinkResponse)
def barber_share_link(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner", "super_admin"]:
        raise HTTPException(status_code=403, detail="No autorizado")

    if not user.barbershop_id:
        raise HTTPException(status_code=400, detail="Usuario no tiene barbería asignada")

    shop = db.query(Barbershop).filter(Barbershop.id == user.barbershop_id, Barbershop.is_deleted == False).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    link = _build_client_link(shop.slug)
    wa_share = f"https://wa.me/?text={link}"

    return BarberShareLinkResponse(
        barbershop_name=shop.name,
        client_link=link,
        whatsapp_share_link=wa_share,
    )
