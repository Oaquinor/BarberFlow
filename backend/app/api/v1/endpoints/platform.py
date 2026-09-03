"""
Endpoints productivos para:
- Autenticación real
- Portal cliente público (sin registro)
- Compartir link de cliente para barbero
- Vista admin de tenants/suscripciones
"""

from datetime import datetime, timedelta
from typing import Optional
from urllib import request as urlrequest
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.core import get_db
from app.core.security.jwt import create_access_token, create_refresh_token, verify_token
from app.core.security.password import verify_password, hash_password
from app.models.user import User
from app.models.barbershop import Barbershop
from app.models.service import Service
from app.models.appointment import Appointment
from app.models.subscription import Subscription
from app.models.barber_availability import BarberAvailability
from app.models.user import UserFeatureFlag
from app.schemas.platform import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthUserResponse,
    PublicBarbershopResponse,
    PublicServiceResponse,
    PublicCreateAppointmentRequest,
    PublicCreateAppointmentResponse,
    PublicAvailableSlotResponse,
    BarberCreateSlotsRequest,
    PublicTrackAppointmentRequest,
    PublicTrackAppointmentResponse,
    PublicTrackAppointmentItem,
    BarberShareLinkResponse,
    AdminTenantItem,
    AdminTenantsResponse,
    AdminUserItem,
    AdminUsersResponse,
    SupportRequest,
    AdminUserSupportToggleRequest,
    AdminUserFeatureFlagRequest,
    BarberAppointmentStatusUpdateRequest,
)

router = APIRouter(tags=["platform"])


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _build_client_link(slug: str) -> str:
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    return f"{frontend_base}/client.html?shop={slug}"


def _parse_date_time(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def _send_whatsapp(phone: str, message: str) -> None:
    whatsapp_url = os.getenv("WHATSAPP_API_URL", "http://127.0.0.1:3001/send")
    payload = json.dumps({"phone": phone, "message": message}).encode("utf-8")
    req = urlrequest.Request(
        url=whatsapp_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urlrequest.urlopen(req, timeout=4)
    except Exception:
        # No bloquea el flujo de negocio si WhatsApp está temporalmente fuera.
        pass


def _send_email(to_email: str, subject: str, body: str) -> None:
    # Placeholder no bloqueante para integración SMTP real.
    # Aquí puedes integrar SMTP/SendGrid según entorno.
    try:
        print(f"[SUPPORT EMAIL] to={to_email} subject={subject} body={body[:120]}")
    except Exception:
        pass


def _get_current_user(db: Session, authorization: Optional[str]) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = verify_token(token, token_type="access")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = db.query(User).filter(User.id == int(user_id), User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    return user


@router.post("/auth/login", response_model=AuthLoginResponse)
def auth_login(data: AuthLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email, User.is_deleted == False).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return AuthLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=AuthUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            barbershop_id=user.barbershop_id,
        ),
    )


@router.post("/support/contact")
def support_contact(data: SupportRequest, db: Session = Depends(get_db)):
    recipients = (
        db.query(User)
        .filter(
            User.role.in_(["super_admin", "barbershop_owner", "barber"]),
            User.support_contact_enabled == True,
            User.is_active == True,
            User.is_deleted == False,
        )
        .all()
    )

    if not recipients:
        raise HTTPException(status_code=400, detail="No hay usuarios configurados para soporte")

    subject = "Solicitud de soporte desde plataforma"
    body = (
        f"Nombre: {data.name}\n"
        f"Email: {data.email or '-'}\n"
        f"Teléfono: {data.phone or '-'}\n"
        f"Mensaje: {data.message}\n"
    )

    for user in recipients:
        if user.email:
            _send_email(user.email, subject, body)

    return {"success": True, "sent_to": len(recipients)}


@router.get("/auth/me", response_model=AuthUserResponse)
def auth_me(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    user = _get_current_user(db, authorization)
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        barbershop_id=user.barbershop_id,
    )


@router.get("/public/{slug}", response_model=PublicBarbershopResponse)
def public_barbershop(slug: str, db: Session = Depends(get_db)):
    shop = db.query(Barbershop).filter(Barbershop.slug == slug, Barbershop.is_deleted == False).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    return PublicBarbershopResponse(
        id=shop.id,
        name=shop.name,
        slug=shop.slug,
        logo_url=shop.logo_url,
        primary_color=shop.primary_color,
        secondary_color=shop.secondary_color,
        client_app_link=_build_client_link(shop.slug),
    )


@router.get("/public/{slug}/services", response_model=list[PublicServiceResponse])
def public_services(slug: str, db: Session = Depends(get_db)):
    shop = db.query(Barbershop).filter(Barbershop.slug == slug, Barbershop.is_deleted == False).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

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
        )
        for s in services
    ]


@router.get("/public/{slug}/slots", response_model=list[PublicAvailableSlotResponse])
def public_slots(slug: str, db: Session = Depends(get_db)):
    shop = db.query(Barbershop).filter(Barbershop.slug == slug, Barbershop.is_deleted == False).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    now = datetime.utcnow()
    rows = (
        db.query(BarberAvailability)
        .join(User, User.id == BarberAvailability.barber_id)
        .filter(
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_active == True,
            BarberAvailability.is_booked == False,
            BarberAvailability.slot_start >= now,
            BarberAvailability.is_deleted == False,
            User.is_active == True,
            User.is_deleted == False,
        )
        .order_by(BarberAvailability.slot_start.asc())
        .all()
    )

    return [
        PublicAvailableSlotResponse(
            availability_id=r.id,
            barber_id=r.barber_id,
            barber_name=r.barber.full_name if r.barber else f"Barbero {r.barber_id}",
            slot_start=r.slot_start,
            slot_end=r.slot_end,
        )
        for r in rows
    ]


@router.post("/public/{slug}/appointments", response_model=PublicCreateAppointmentResponse)
def public_create_appointment(slug: str, data: PublicCreateAppointmentRequest, db: Session = Depends(get_db)):
    shop = db.query(Barbershop).filter(Barbershop.slug == slug, Barbershop.is_deleted == False).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

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

    # El cliente solo puede reservar turnos configurados por el barbero y no vencidos.
    slot = (
        db.query(BarberAvailability)
        .filter(
            BarberAvailability.barbershop_id == shop.id,
            BarberAvailability.is_active == True,
            BarberAvailability.is_booked == False,
            BarberAvailability.slot_start == data.scheduled_time,
            BarberAvailability.slot_start >= datetime.utcnow(),
            BarberAvailability.is_deleted == False,
        )
        .order_by(BarberAvailability.id.asc())
        .first()
    )

    if not slot:
        raise HTTPException(status_code=400, detail="Ese turno no está disponible")

    barber = db.query(User).filter(User.id == slot.barber_id, User.is_active == True, User.is_deleted == False).first()
    if not barber:
        raise HTTPException(status_code=400, detail="El barbero del turno no está disponible")

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

    if not client:
        name_parts = data.client_name.strip().split(" ")
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]).strip() or "Cliente"
        synthetic_email = f"{phone}@client.local"

        existing_email_user = db.query(User).filter(User.email == synthetic_email).first()
        if existing_email_user:
            synthetic_email = f"{phone}.{shop.id}@client.local"

        client = User(
            email=synthetic_email,
            password_hash=hash_password("Client123A"),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role="client",
            is_active=True,
            is_verified=True,
            barbershop_id=shop.id,
        )
        db.add(client)
        db.flush()

    appointment = Appointment(
        barbershop_id=shop.id,
        client_id=client.id,
        barber_id=barber.id,
        scheduled_time=data.scheduled_time,
        estimated_duration=service.duration_minutes,
        service_type=service.name,
        service_price=service.price,
        status="pending",
        client_notes=data.notes,
    )
    db.add(appointment)
    slot.is_booked = True
    db.commit()
    db.refresh(appointment)

    tracking_link = f"{_build_client_link(shop.slug)}&track={appointment.id}&phone={phone}"

    wa_message = (
        f"💈 *{shop.name}*\n"
        f"Hola {client.full_name}, tu cita fue registrada.\n"
        f"📅 {appointment.scheduled_time}\n"
        f"✂️ {service.name}\n"
        f"🔎 Seguimiento: {tracking_link}"
    )
    _send_whatsapp(phone, wa_message)

    # Notificación al barbero (WhatsApp)
    barber_phone = barber.phone or ""
    if barber_phone:
        barber_msg = (
            f"🔔 *Nueva cita registrada*\n"
            f"Barbería: {shop.name}\n"
            f"Cliente: {client.full_name} ({phone})\n"
            f"Servicio: {service.name}\n"
            f"Hora: {appointment.scheduled_time}\n"
            f"Estado: {appointment.status}"
        )
        _send_whatsapp(barber_phone, barber_msg)

    return PublicCreateAppointmentResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        tracking_link=tracking_link,
        message="Cita agendada correctamente",
    )


@router.post("/barber/slots")
def barber_create_slots(
    data: BarberCreateSlotsRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner"]:
        raise HTTPException(status_code=403, detail="Solo barbero/owner puede crear turnos")
    if not user.barbershop_id:
        raise HTTPException(status_code=400, detail="Usuario sin barbería asignada")

    start_dt = _parse_date_time(data.date, data.start_time)
    end_dt = _parse_date_time(data.date, data.end_time)

    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="Rango de horario inválido")

    created = 0
    cursor = start_dt
    while cursor < end_dt:
        slot_end = cursor + timedelta(minutes=data.slot_minutes)
        if slot_end > end_dt:
            break

        exists = (
            db.query(BarberAvailability)
            .filter(
                BarberAvailability.barber_id == user.id,
                BarberAvailability.slot_start == cursor,
                BarberAvailability.is_deleted == False,
            )
            .first()
        )
        if not exists:
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

    db.commit()
    return {"success": True, "created_slots": created}


@router.post("/public/{slug}/track", response_model=PublicTrackAppointmentResponse)
def public_track_appointments(slug: str, data: PublicTrackAppointmentRequest, db: Session = Depends(get_db)):
    shop = db.query(Barbershop).filter(Barbershop.slug == slug, Barbershop.is_deleted == False).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

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
    if not client:
        return PublicTrackAppointmentResponse(items=[])

    query = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop.id,
            Appointment.client_id == client.id,
            Appointment.is_deleted == False,
        )
        .order_by(Appointment.scheduled_time.desc())
    )

    if data.appointment_id:
        query = query.filter(Appointment.id == data.appointment_id)

    appointments = query.limit(20).all()

    items = []
    for ap in appointments:
        barber_name = ap.barber.full_name if ap.barber else None
        items.append(
            PublicTrackAppointmentItem(
                appointment_id=ap.id,
                status=ap.status,
                scheduled_time=ap.scheduled_time,
                service_type=ap.service_type,
                barber_name=barber_name,
            )
        )

    return PublicTrackAppointmentResponse(items=items)


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


@router.put("/barber/appointments/{appointment_id}/status")
def barber_update_appointment_status(
    appointment_id: int,
    data: BarberAppointmentStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner", "super_admin"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    if not user.barbershop_id:
        raise HTTPException(status_code=400, detail="Usuario sin barbería asignada")

    valid_statuses = {"pending", "confirmed", "in_progress", "completed", "cancelled", "no_show"}
    status = (data.status or "").strip().lower()
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Estado no válido")

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.barbershop_id == user.barbershop_id,
            Appointment.is_deleted == False,
        )
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    appointment.status = status
    now = datetime.utcnow()
    if status == "in_progress" and not appointment.actual_start_time:
        appointment.actual_start_time = now
    if status == "completed" and not appointment.actual_end_time:
        appointment.actual_end_time = now

    db.commit()
    return {
        "success": True,
        "appointment_id": appointment.id,
        "status": appointment.status,
    }


@router.get("/barber/dashboard")
def barber_dashboard(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner", "super_admin"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    if not user.barbershop_id:
        raise HTTPException(status_code=400, detail="Usuario sin barbería asignada")

    shop_id = user.barbershop_id

    services = (
        db.query(Service)
        .filter(
            Service.barbershop_id == shop_id,
            Service.is_active == True,
            Service.is_deleted == False,
        )
        .order_by(Service.display_order.asc(), Service.id.asc())
        .all()
    )

    now = datetime.utcnow()
    day_start = datetime(now.year, now.month, now.day)
    day_end = day_start + timedelta(days=1)

    week_start = day_start - timedelta(days=6)
    appointments_week = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop_id,
            Appointment.scheduled_time >= week_start,
            Appointment.scheduled_time < day_end,
            Appointment.is_deleted == False,
        )
        .all()
    )

    completed_all_time = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop_id,
            Appointment.status == "completed",
            Appointment.is_deleted == False,
        )
        .count()
    )

    appointments_today = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop_id,
            Appointment.scheduled_time >= day_start,
            Appointment.scheduled_time < day_end,
            Appointment.is_deleted == False,
        )
        .order_by(Appointment.scheduled_time.asc())
        .all()
    )

    completed_count = len([a for a in appointments_today if a.status == "completed"])
    in_progress_count = len([a for a in appointments_today if a.status == "in_progress"])
    pending_count = len([a for a in appointments_today if a.status in ["pending", "confirmed"]])
    total_count = len(appointments_today)
    revenue_cents = sum((a.service_price or 0) for a in appointments_today if a.status in ["completed", "in_progress"])
    efficiency_percent = int((completed_count / total_count) * 100) if total_count else 0

    yesterday_start = day_start - timedelta(days=1)
    yesterday_end = day_start
    appointments_yesterday = (
        db.query(Appointment)
        .filter(
            Appointment.barbershop_id == shop_id,
            Appointment.scheduled_time >= yesterday_start,
            Appointment.scheduled_time < yesterday_end,
            Appointment.is_deleted == False,
        )
        .all()
    )
    completed_yesterday = len([a for a in appointments_yesterday if a.status == "completed"])
    revenue_yesterday = sum((a.service_price or 0) for a in appointments_yesterday if a.status in ["completed", "in_progress"])
    total_yesterday = len(appointments_yesterday)
    efficiency_yesterday = int((completed_yesterday / total_yesterday) * 100) if total_yesterday else 0

    completed_delta = completed_count - completed_yesterday
    revenue_delta = revenue_cents - revenue_yesterday
    efficiency_delta = efficiency_percent - efficiency_yesterday

    next_appointment = next((a for a in appointments_today if a.scheduled_time >= now), None)

    weekday_labels = ["L", "M", "X", "J", "V", "S", "D"]
    week_counts_by_day = {i: 0 for i in range(7)}
    for ap in appointments_week:
        week_counts_by_day[ap.scheduled_time.weekday()] += 1

    max_count = max(week_counts_by_day.values()) if week_counts_by_day else 0
    weekly_counts = [
        {
            "label": weekday_labels[day_idx],
            "count": week_counts_by_day[day_idx],
            "height_percent": int((week_counts_by_day[day_idx] / max_count) * 100) if max_count else 0,
        }
        for day_idx in range(7)
    ]

    achievements = {
        "unlocked": min(20, completed_all_time // 10),
        "points": (completed_all_time * 2) + (completed_count * 5),
        "progress_percent": min(100, int((completed_all_time / 200) * 100)),
        "items": [
            {
                "title": "Primeros 10 servicios",
                "description": "Completa 10 citas terminadas.",
                "target": 10,
                "current": completed_all_time,
                "points": 50,
            },
            {
                "title": "Constancia semanal",
                "description": "Completa al menos 15 citas en 7 días.",
                "target": 15,
                "current": sum(1 for a in appointments_week if a.status == "completed"),
                "points": 80,
            },
            {
                "title": "Maestría",
                "description": "Alcanza 100 citas completadas.",
                "target": 100,
                "current": completed_all_time,
                "points": 200,
            },
        ],
    }

    return {
        "summary": {
            "total": total_count,
            "completed": completed_count,
            "pending": pending_count,
            "in_progress": in_progress_count,
            "revenue_cents": revenue_cents,
            "efficiency_percent": efficiency_percent,
            "completed_delta": completed_delta,
            "revenue_delta_cents": revenue_delta,
            "efficiency_delta": efficiency_delta,
        },
        "next_appointment": (
            {
                "id": next_appointment.id,
                "client_name": next_appointment.client.full_name if next_appointment.client else "Cliente",
                "service_type": next_appointment.service_type,
                "scheduled_time": next_appointment.scheduled_time,
                "estimated_duration": next_appointment.estimated_duration,
            }
            if next_appointment
            else None
        ),
        "appointments": [
            {
                "id": a.id,
                "client_name": a.client.full_name if a.client else "Cliente",
                "service_type": a.service_type,
                "scheduled_time": a.scheduled_time,
                "estimated_duration": a.estimated_duration,
                "service_price": a.service_price,
                "status": a.status,
            }
            for a in appointments_today
        ],
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "duration_minutes": s.duration_minutes,
                "price_cents": s.price,
                "category": s.category,
            }
            for s in services
        ],
        "weekly_counts": weekly_counts,
        "achievements": achievements,
    }


@router.get("/admin/tenants", response_model=AdminTenantsResponse)
def admin_tenants(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    shops = db.query(Barbershop).filter(Barbershop.is_deleted == False).order_by(Barbershop.id.asc()).all()
    items = []

    for shop in shops:
        owner = (
            db.query(User)
            .filter(
                User.barbershop_id == shop.id,
                User.role == "barbershop_owner",
                User.is_deleted == False,
            )
            .first()
        )

        plan = None
        sub_status = None
        if shop.subscription_id:
            sub = db.query(Subscription).filter(Subscription.id == shop.subscription_id).first()
            if sub:
                plan = sub.plan
                sub_status = sub.status

        items.append(
            AdminTenantItem(
                barbershop_id=shop.id,
                barbershop_name=shop.name,
                slug=shop.slug,
                owner_email=owner.email if owner else None,
                plan=plan,
                subscription_status=sub_status,
                active=shop.is_active,
            )
        )

    return AdminTenantsResponse(items=items)


@router.get("/admin/users", response_model=AdminUsersResponse)
def admin_users(
    barbershop_id: Optional[int] = None,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    query = db.query(User).filter(User.is_deleted == False)
    if barbershop_id is not None:
        query = query.filter(User.barbershop_id == barbershop_id)

    users = query.order_by(User.id.asc()).all()
    items = [
        AdminUserItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            barbershop_id=u.barbershop_id,
            is_active=u.is_active,
            support_contact_enabled=u.support_contact_enabled,
        )
        for u in users
    ]
    return AdminUsersResponse(items=items)


@router.put("/admin/users/{user_id}/support")
def admin_toggle_user_support(
    user_id: int,
    data: AdminUserSupportToggleRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.role not in ["super_admin", "barbershop_owner", "barber"]:
        raise HTTPException(status_code=400, detail="Solo roles administrativos/barbero pueden recibir soporte")

    user.support_contact_enabled = data.support_contact_enabled
    db.commit()
    return {"success": True, "user_id": user.id, "support_contact_enabled": user.support_contact_enabled}


@router.put("/admin/users/{user_id}/features")
def admin_set_user_feature(
    user_id: int,
    data: AdminUserFeatureFlagRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Regla solicitada: customización automática aplica solo a barberos/owner con onboarding.
    if data.feature_key == "branding_auto" and data.enabled:
        if user.role not in ["barber", "barbershop_owner"]:
            raise HTTPException(status_code=400, detail="branding_auto solo aplica a barbero/owner")

        if not user.barbershop_id:
            raise HTTPException(status_code=400, detail="Usuario sin barbería asignada")

        shop = db.query(Barbershop).filter(Barbershop.id == user.barbershop_id).first()
        if not shop or not shop.onboarding_completed:
            raise HTTPException(status_code=400, detail="El barbero debe completar onboarding para branding_auto")

    feature = (
        db.query(UserFeatureFlag)
        .filter(
            UserFeatureFlag.user_id == user.id,
            UserFeatureFlag.feature_key == data.feature_key,
            UserFeatureFlag.is_deleted == False,
        )
        .first()
    )

    if not feature:
        feature = UserFeatureFlag(user_id=user.id, feature_key=data.feature_key, enabled=data.enabled)
        db.add(feature)
    else:
        feature.enabled = data.enabled

    db.commit()
    return {"success": True, "user_id": user.id, "feature_key": data.feature_key, "enabled": data.enabled}
