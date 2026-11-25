"""Verified global customer accounts and capability-based CRM linking."""

from datetime import timedelta
from hashlib import sha256
from html import escape
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser
from app.api.v1.endpoints.common import _get_timezone, _normalize_phone, _utc_aware
from app.api.v1.endpoints.platform import (
    _consume_public_token_quota, _notify_appointment_staff, _public_booking_client_ip,
    _queue_appointment_email, _queue_appointment_whatsapp,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security.password import hash_password
from app.models import (
    Appointment, Barbershop, ClientAccountFavorite, ClientAccountShopLink,
    ClientAccountVerification, Service, Subscription, User,
)
from app.schemas.client_account import (
    ClientAccountRegisterRequest, ClientAccountResendRequest, ClientAccountVerifyRequest,
    ClientAccountFavoriteRequest, ClientAccountProfileUpdateRequest, ClientAppointmentCancelRequest,
    ClientAppointmentClaimRequest,
)
from app.services.audit_service import record_audit
from app.services.client_account_service import get_or_create_shop_client
from app.services.customer_appointment_service import cancel_customer_appointment
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


@router.get("/favorites")
def list_client_favorites(response: Response, user: CurrentUser, db: Session = Depends(get_db)):
    _require_client_account(user)
    response.headers["Cache-Control"] = "no-store"
    favorites = db.query(ClientAccountFavorite, Barbershop).join(
        Barbershop, Barbershop.id == ClientAccountFavorite.barbershop_id,
    ).filter(
        ClientAccountFavorite.account_user_id == user.id,
        ClientAccountFavorite.is_deleted == False,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).order_by(ClientAccountFavorite.created_at.desc()).all()
    items = []
    for favorite, shop in favorites:
        if favorite.target_type == "barbershop":
            target = shop
            name = shop.name
            image_url = shop.logo_url or shop.cover_image_url
            details = {}
        elif favorite.target_type == "service":
            target = db.query(Service).filter(
                Service.id == favorite.target_id,
                Service.barbershop_id == shop.id,
                Service.is_active == True,
                Service.is_deleted == False,
            ).first()
            details = {"price_cents": target.price, "duration_minutes": target.duration_minutes} if target else {}
            name = target.name if target else None
            image_url = target.image_url if target else None
        else:
            target = db.query(User).filter(
                User.id == favorite.target_id,
                User.barbershop_id == shop.id,
                User.role == "barber",
                User.is_active == True,
                User.is_deleted == False,
            ).first()
            details = {}
            name = target.full_name if target else None
            image_url = target.avatar_url if target else None
        if not target:
            continue
        items.append({
            "favorite_id": favorite.id, "barbershop": shop.name,
            "barbershop_slug": shop.slug, "target_type": favorite.target_type,
            "target_id": target.id,
            "name": name,
            "image_url": image_url,
            **details,
        })
    return {"items": items}


@router.post("/favorites")
def save_client_favorite(
    data: ClientAccountFavoriteRequest, user: CurrentUser, db: Session = Depends(get_db),
):
    _require_client_account(user)
    shop = db.query(Barbershop).filter(
        Barbershop.slug == data.barbershop_slug,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no disponible")
    target_id = shop.id if data.target_type == "barbershop" else data.target_id
    if data.target_type == "barbershop":
        target = shop
    elif data.target_type == "service":
        target = db.query(Service).filter(
            Service.id == data.target_id, Service.barbershop_id == shop.id,
            Service.is_active == True, Service.is_deleted == False,
        ).first()
    else:
        target = db.query(User).filter(
            User.id == data.target_id, User.barbershop_id == shop.id,
            User.role == "barber", User.is_active == True, User.is_deleted == False,
        ).first()
    if not target:
        raise HTTPException(status_code=404, detail="La barbería, servicio o barbero no está disponible")
    favorite = db.query(ClientAccountFavorite).filter(
        ClientAccountFavorite.account_user_id == user.id,
        ClientAccountFavorite.barbershop_id == shop.id,
        ClientAccountFavorite.target_type == data.target_type,
        ClientAccountFavorite.target_id == target_id,
    ).with_for_update().first()
    changed = False
    if favorite and favorite.is_deleted:
        favorite.is_deleted = False
        favorite.deleted_at = None
        changed = True
    elif not favorite:
        favorite = ClientAccountFavorite(
            account_user_id=user.id, barbershop_id=shop.id,
            target_type=data.target_type, target_id=target_id,
        )
        db.add(favorite)
        changed = True
    if changed:
        db.flush()
        record_audit(db, user, "client_account.favorite_saved", "client_account_favorite",
                     favorite.id, shop.id,
                     {"target_type": data.target_type, "target_id": target_id})
    db.commit()
    return {"success": True, "favorite_id": favorite.id}


@router.delete("/favorites/{favorite_id}")
def remove_client_favorite(favorite_id: int, user: CurrentUser, db: Session = Depends(get_db)):
    _require_client_account(user)
    favorite = db.query(ClientAccountFavorite).filter(
        ClientAccountFavorite.id == favorite_id,
        ClientAccountFavorite.account_user_id == user.id,
        ClientAccountFavorite.is_deleted == False,
    ).with_for_update().first()
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorito no encontrado")
    favorite.soft_delete()
    record_audit(db, user, "client_account.favorite_removed", "client_account_favorite",
                 favorite.id, favorite.barbershop_id,
                 {"target_type": favorite.target_type, "target_id": favorite.target_id})
    db.commit()
    return {"success": True}


@router.get("/profile")
def get_client_profile(response: Response, user: CurrentUser):
    _require_client_account(user)
    response.headers["Cache-Control"] = "no-store"
    return {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone or "",
    }


@router.patch("/profile")
def update_client_profile(
    data: ClientAccountProfileUpdateRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _require_client_account(user)
    changed_fields = []
    for field in ("first_name", "last_name", "phone"):
        value = getattr(data, field)
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed_fields.append(field)
    if changed_fields:
        record_audit(
            db, user, "client_account.profile_updated", "user", user.id,
            details={"changed_fields": changed_fields},
        )
    db.commit()
    return {
        "success": True,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone or "",
    }


@router.get("/appointments")
def list_client_appointments(
    response: Response, user: CurrentUser, db: Session = Depends(get_db),
):
    _require_client_account(user)
    response.headers["Cache-Control"] = "no-store"
    appointments = db.query(Appointment).filter(
        Appointment.client_id.in_(
            db.query(ClientAccountShopLink.crm_client_user_id).filter(
                ClientAccountShopLink.account_user_id == user.id,
                ClientAccountShopLink.is_deleted == False,
            )
        ),
        Appointment.is_deleted == False,
    ).options(
        joinedload(Appointment.barbershop), joinedload(Appointment.barber),
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


@router.get("/export")
def export_client_data(
    response: Response, user: CurrentUser, db: Session = Depends(get_db),
):
    """Return the authenticated customer's profile and linked appointment data."""
    _require_client_account(user)
    response.headers["Cache-Control"] = "no-store"
    appointments = db.query(Appointment).join(
        ClientAccountShopLink,
        ClientAccountShopLink.crm_client_user_id == Appointment.client_id,
    ).filter(
        ClientAccountShopLink.account_user_id == user.id,
        ClientAccountShopLink.is_deleted == False,
        Appointment.is_deleted == False,
    ).options(
        joinedload(Appointment.barbershop), joinedload(Appointment.barber),
    ).order_by(Appointment.scheduled_time.desc()).all()
    record_audit(
        db, user, "client_account.data_exported", "user", user.id,
        details={"appointment_count": len(appointments)},
    )
    db.commit()
    return {
        "exported_at": utc_now_naive(),
        "account": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
        },
        "appointments": [{
            "appointment_id": appointment.id,
            "barbershop": appointment.barbershop.name if appointment.barbershop else None,
            "scheduled_time": appointment.scheduled_time,
            "status": appointment.status,
            "service": appointment.service_type,
            "price_cents": appointment.service_price,
            "duration_minutes": appointment.estimated_duration,
            "barber": appointment.barber.full_name if appointment.barber else None,
            "notes": appointment.client_notes,
        } for appointment in appointments],
    }


@router.post("/appointments/{appointment_id}/cancel")
def cancel_client_appointment(
    appointment_id: int,
    data: ClientAppointmentCancelRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    _require_client_account(user)
    appointment_ref = db.query(Appointment.barbershop_id).join(
        ClientAccountShopLink,
        ClientAccountShopLink.crm_client_user_id == Appointment.client_id,
    ).filter(
        Appointment.id == appointment_id,
        ClientAccountShopLink.account_user_id == user.id,
        ClientAccountShopLink.is_deleted == False,
        Appointment.is_deleted == False,
    ).first()
    if not appointment_ref:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    shop = db.query(Barbershop).filter(
        Barbershop.id == appointment_ref.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    appointment = db.query(Appointment).join(
        ClientAccountShopLink,
        ClientAccountShopLink.crm_client_user_id == Appointment.client_id,
    ).filter(
        Appointment.id == appointment_id,
        Appointment.barbershop_id == shop.id,
        ClientAccountShopLink.account_user_id == user.id,
        ClientAccountShopLink.is_deleted == False,
        Appointment.is_deleted == False,
    ).with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    now = utc_now_naive()
    cancel_customer_appointment(db, shop, appointment, data.reason, now)
    local_time = _utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop))
    _notify_appointment_staff(
        db, appointment, "appointment_cancelled", "Cita cancelada por el cliente",
        f"{appointment.service_type} · {local_time.strftime('%d/%m/%Y %H:%M')}",
    )
    record_audit(
        db, user, "appointment.cancelled_by_client", "appointment", appointment.id,
        shop.id, {"reason": data.reason, "channel": "client_account"},
    )
    _queue_appointment_email(db, appointment, "cancellation", data.reason)
    if appointment.client and not appointment.client.is_deleted and appointment.client.phone:
        _queue_appointment_whatsapp(
            db, appointment, appointment.client.phone,
            f"La cita en {shop.name} para {local_time.strftime('%d/%m/%Y %H:%M')} fue cancelada.",
            "cancellation:client", recipient_user_id=appointment.client_id,
        )
    db.commit()
    return {"success": True, "appointment_id": appointment.id, "status": appointment.status}


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
