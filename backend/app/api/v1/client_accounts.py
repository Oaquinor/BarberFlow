"""Verified global customer accounts and capability-based CRM linking."""

from datetime import timedelta
from hashlib import sha256
from html import escape
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.api.v1.endpoints.common import _normalize_phone
from app.api.v1.endpoints.platform import _consume_public_token_quota, _public_booking_client_ip
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security.password import hash_password
from app.models import (
    Appointment, Barbershop, ClientAccountShopLink, ClientAccountVerification,
    Subscription, User,
)
from app.schemas.client_account import (
    ClientAccountRegisterRequest, ClientAccountResendRequest, ClientAccountVerifyRequest,
    ClientAppointmentClaimRequest,
)
from app.services.audit_service import record_audit
from app.services.client_account_service import get_or_create_shop_client
from app.services.notification_service import NotificationService
from app.utils.datetime import utc_now_naive


router = APIRouter(prefix="/client-account", tags=["Client account"])
VERIFICATION_TTL = timedelta(minutes=30)
RATE_LIMIT = 5
GENERIC_ACCOUNT_MESSAGE = "Si el correo puede registrarse, enviaremos un enlace de verificación."


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _deliver_verification_email(recipient: str, first_name: str, verification_url: str) -> None:
    body = (
        f"<p>Hola {escape(first_name)},</p>"
        "<p>Confirma tu correo para activar tu cuenta de cliente de KingFlow Barber.</p>"
        f'<p><a href="{escape(verification_url, quote=True)}">Verificar mi correo</a></p>'
        "<p>El enlace vence en 30 minutos y solo se puede usar una vez. "
        "Si no solicitaste la cuenta, ignora este mensaje.</p>"
    )
    NotificationService(None)._send_email(recipient, "Verifica tu cuenta de KingFlow Barber", body)


def _smtp_ready() -> bool:
    settings = get_settings()
    return all((settings.SMTP_HOST.strip(), settings.SMTP_USER.strip(),
                settings.SMTP_PASSWORD, settings.EMAIL_FROM.strip()))


def _issue_verification(db: Session, user: User, now) -> tuple[str, str]:
    db.query(ClientAccountVerification).filter(
        ClientAccountVerification.user_id == user.id,
        ClientAccountVerification.consumed_at.is_(None),
        ClientAccountVerification.revoked_at.is_(None),
    ).update({ClientAccountVerification.revoked_at: now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(32)
    db.add(ClientAccountVerification(
        user_id=user.id,
        token_hash=_token_hash(raw_token),
        expires_at=now + VERIFICATION_TTL,
    ))
    frontend = get_settings().FRONTEND_BASE_URL.rstrip("/")
    return raw_token, f"{frontend}/client-account.html?verify={raw_token}"


@router.post("/register", status_code=202)
def register_client_account(
    data: ClientAccountRegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not _smtp_ready():
        raise HTTPException(status_code=503, detail="La verificación por correo no está configurada")
    now = utc_now_naive()
    _consume_public_token_quota(
        db, "client-account-register", _public_booking_client_ip(request), now, RATE_LIMIT,
    )
    email = str(data.email).strip().lower()
    existing = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    if existing:
        db.commit()
        return {"message": GENERIC_ACCOUNT_MESSAGE}

    user = User(
        email=email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        phone=_normalize_phone(data.phone),
        role="client",
        is_active=False,
        is_verified=False,
        barbershop_id=None,
    )
    db.add(user)
    try:
        db.flush()
        raw_token, verification_url = _issue_verification(db, user, now)
        record_audit(db, None, "client_account.verification_requested", "user", user.id,
                     details={"channel": "email"})
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"message": GENERIC_ACCOUNT_MESSAGE}
    background_tasks.add_task(_deliver_verification_email, user.email, user.first_name, verification_url)
    return {"message": GENERIC_ACCOUNT_MESSAGE}


@router.post("/resend-verification", status_code=202)
def resend_client_verification(
    data: ClientAccountResendRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not _smtp_ready():
        raise HTTPException(status_code=503, detail="La verificación por correo no está configurada")
    email = str(data.email).strip().lower()
    now = utc_now_naive()
    _consume_public_token_quota(
        db, "client-account-resend", _public_booking_client_ip(request), now, RATE_LIMIT,
    )
    user = db.query(User).filter(
        User.email == email,
        User.role == "client",
        User.barbershop_id.is_(None),
        User.is_active == False,
        User.is_verified == False,
        User.is_deleted == False,
    ).with_for_update().first()
    if user:
        _raw_token, verification_url = _issue_verification(db, user, now)
        db.commit()
        background_tasks.add_task(_deliver_verification_email, user.email, user.first_name, verification_url)
    else:
        db.commit()
    return {"message": GENERIC_ACCOUNT_MESSAGE}


@router.post("/verify")
def verify_client_account(data: ClientAccountVerifyRequest, db: Session = Depends(get_db)):
    now = utc_now_naive()
    verification = db.query(ClientAccountVerification).filter(
        ClientAccountVerification.token_hash == _token_hash(data.token),
        ClientAccountVerification.consumed_at.is_(None),
        ClientAccountVerification.revoked_at.is_(None),
        ClientAccountVerification.expires_at > now,
        ClientAccountVerification.is_deleted == False,
    ).with_for_update().first()
    if not verification:
        raise HTTPException(status_code=400, detail="El enlace no es válido o ya venció")
    user = db.query(User).filter(
        User.id == verification.user_id,
        User.role == "client",
        User.barbershop_id.is_(None),
        User.is_deleted == False,
    ).with_for_update().first()
    if not user:
        verification.revoked_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="El enlace no es válido o ya venció")
    user.is_active = True
    user.is_verified = True
    verification.consumed_at = now
    record_audit(db, user, "client_account.email_verified", "user", user.id,
                 details={"channel": "email"})
    db.commit()
    return {"success": True, "message": "Correo verificado. Ya puedes iniciar sesión."}


def _require_client_account(user: User) -> None:
    if user.role != "client" or user.barbershop_id is not None or not user.is_verified:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta de cliente verificada")


@router.get("/appointments")
def list_client_appointments(user: CurrentUser, db: Session = Depends(get_db)):
    _require_client_account(user)
    links = db.query(ClientAccountShopLink).filter(
        ClientAccountShopLink.account_user_id == user.id,
        ClientAccountShopLink.is_deleted == False,
    ).all()
    client_ids = [link.crm_client_user_id for link in links]
    if not client_ids:
        return {"items": []}
    appointments = db.query(Appointment).filter(
        Appointment.client_id.in_(client_ids),
        Appointment.is_deleted == False,
    ).order_by(Appointment.scheduled_time.desc()).limit(100).all()
    return {"items": [{
        "appointment_id": appointment.id,
        "barbershop": appointment.barbershop.name if appointment.barbershop else "Barbería",
        "barbershop_slug": appointment.barbershop.slug if appointment.barbershop else None,
        "status": appointment.status,
        "scheduled_time": appointment.scheduled_time,
        "service": appointment.service_type,
        "price_cents": appointment.service_price,
        "duration_minutes": appointment.estimated_duration,
        "barber": appointment.barber.full_name if appointment.barber else "Equipo",
        "notes": appointment.client_notes,
    } for appointment in appointments]}


@router.post("/appointments/claim")
def claim_client_appointment(
    data: ClientAppointmentClaimRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _require_client_account(user)
    appointment = db.query(Appointment).filter(
        Appointment.tracking_token_hash == _token_hash(data.tracking_token),
        Appointment.is_deleted == False,
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="No encontramos una cita con ese código privado")
    shop = db.query(Barbershop).filter(
        Barbershop.id == appointment.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    subscription = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    ).with_for_update().first() if shop.subscription_id else None
    if not subscription:
        raise HTTPException(status_code=404, detail="No se puede vincular esta barbería")
    appointment = db.query(Appointment).filter(
        Appointment.tracking_token_hash == _token_hash(data.tracking_token),
        Appointment.barbershop_id == shop.id,
        Appointment.is_deleted == False,
    ).with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="No encontramos una cita con ese código privado")
    current_link = db.query(ClientAccountShopLink).filter(
        ClientAccountShopLink.crm_client_user_id == appointment.client_id,
        ClientAccountShopLink.is_deleted == False,
    ).with_for_update().first()
    if current_link and current_link.account_user_id != user.id:
        raise HTTPException(status_code=409, detail="Esta cita ya está vinculada a otra cuenta")
    crm_client = get_or_create_shop_client(db, user, shop, subscription)
    appointment.client_id = crm_client.id
    record_audit(db, user, "client_account.appointment_claimed", "appointment", appointment.id,
                 shop.id, {"method": "tracking_token"})
    db.commit()
    return {"success": True, "appointment_id": appointment.id,
            "message": "La cita se añadió a tu historial."}
