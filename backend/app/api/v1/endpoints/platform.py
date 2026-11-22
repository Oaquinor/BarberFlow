"""
Endpoints productivos para:
- Autenticación real
- Portal cliente público (sin registro)
- Compartir link de cliente para barbero
- Vista admin de tenants/suscripciones
"""

from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from html import escape as escape_html
import hashlib
import os
import re
import secrets
import smtplib
import unicodedata
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from time import sleep as sleep_seconds

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy import case, or_, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user as authenticate_user
from app.core import get_db
from app.core.constants.enums import (
    MAX_ADVANCE_BOOKING_DAYS,
    MAX_SERVICE_DURATION_MINUTES,
    SUBSCRIPTION_LIMITS,
)
from app.core.security.jwt import create_access_token, create_refresh_token, verify_token
from app.core.security.password import verify_password, hash_password
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.user import User
from app.models.barbershop import Barbershop
from app.models.service import Service
from app.models.appointment import Appointment
from app.models.subscription import Subscription
from app.models.barber_availability import BarberAvailability
from app.models.barber_availability_block import BarberAvailabilityBlock
from app.models.user import UserFeatureFlag
from app.models.refresh_session import RefreshSession
from app.models.payment import Payment, CashRegisterClose
from app.models.barber_commission import BarberCommission
from app.models.in_app_notification import InAppNotification
from app.models.login_attempt import LoginAttempt
from app.models.audit_log import AuditLog
from app.models.affiliate import Affiliate
from app.models.commission import Commission
from app.models.subscription_payment import SubscriptionPayment
from app.models.platform_settings import PlatformSettings
from app.models.support_ticket import SupportTicket
from app.core.constants import CommissionStatus
from app.models.achievement import Achievement, UserAchievement
from app.models.barber_performance import BarberPerformance
from app.services.subscription_service import count_monthly_appointments
from app.schemas.auth import PasswordChangeRequest, RefreshTokenRequest, RefreshTokenResponse
from app.schemas.platform import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthUserResponse,
    TenantRegistrationRequest,
    PublicBarbershopResponse,
    PublicServiceResponse,
    PublicCreateAppointmentRequest,
    PublicCreateAppointmentResponse,
    PublicAvailableSlotResponse,
    BarberCreateSlotsRequest,
    BarberAbsenceRequest,
    PublicTrackAppointmentRequest,
    PublicCancelAppointmentRequest,
    PublicRescheduleAppointmentRequest,
    WalkInAppointmentRequest,
    PublicTrackAppointmentResponse,
    PublicTrackAppointmentItem,
    BarberShareLinkResponse,
    AdminTenantItem,
    AdminTenantsResponse,
    AdminUserItem,
    AdminUsersResponse,
    AdminSubscriptionUpdateRequest,
    AdminSubscriptionResponse,
    SupportRequest,
    AdminUserSupportToggleRequest,
    AdminStatusUpdateRequest,
    AdminSupportTicketStatusRequest,
    OwnerCreateBarberRequest,
    OwnerBarberUpdateRequest,
    OwnerClientCreateRequest,
    OwnerClientUpdateRequest,
    AdminAffiliateCreateRequest,
    AdminCommissionPaymentRequest,
    BarberCommissionRateRequest,
    BarberCommissionPaymentRequest,
    AdminSubscriptionPaymentRequest,
    AdminUserFeatureFlagRequest,
    BarberAppointmentStatusUpdateRequest,
    AppointmentPaymentRequest,
    CashRegisterCloseRequest,
)
from app.services.affiliate_service import AffiliateService
from app.services.audit_service import record_audit
from app.utils.datetime import local_day_start_utc_naive, utc_now_naive
from app.utils.client_ip import get_client_ip
from app.services.notification_service import NotificationService
from app.services.notification_outbox import enqueue_delivery
from app.services.auth_record_retention import prune_expired_auth_records

router = APIRouter(tags=["platform"])
settings = get_settings()
logger = get_logger(__name__)
DUMMY_LOGIN_PASSWORD_HASH = hash_password("unusable-login-sentinel-value")


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _build_client_link(slug: str) -> str:
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{frontend_base}/client.html?shop={slug}"


def _get_public_shop(db: Session, slug: str) -> Optional[Barbershop]:
    return db.query(Barbershop).filter(
        Barbershop.slug == slug,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()


def _require_active_subscription(db: Session, shop: Barbershop, lock: bool = False) -> Subscription:
    if not shop.subscription_id:
        raise HTTPException(status_code=402, detail="La barbería no tiene una suscripción activa")
    query = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    )
    if lock:
        query = query.with_for_update()
    subscription = query.first()
    if (
        not subscription
        or subscription.status != "active"
        or subscription.current_period_end <= utc_now_naive()
    ):
        raise HTTPException(status_code=402, detail="La suscripción de esta barbería no está activa")
    return subscription


def _parse_date_time(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def _get_timezone(shop: Barbershop) -> ZoneInfo:
    try:
        return ZoneInfo(shop.timezone)
    except (ZoneInfoNotFoundError, TypeError):
        raise HTTPException(status_code=500, detail="La zona horaria de la barbería no es válida")


def _to_utc_naive(value: datetime, shop: Barbershop) -> datetime:
    """Convert a local business time or aware timestamp into UTC for MySQL storage."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    tz = _get_timezone(shop)
    local = value.replace(tzinfo=tz)
    round_trip = local.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    alternate = value.replace(tzinfo=tz, fold=1)
    if round_trip != value or local.utcoffset() != alternate.utcoffset():
        raise HTTPException(status_code=422, detail="La hora local es ambigua o no existe por cambio horario")
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _business_date_for_appointment(appointment: Appointment, shop: Barbershop):
    """Return the appointment's calendar date in its barbershop's timezone."""
    return _utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).date()


def _cash_register_closed_for_user(
    db: Session, user: User, barbershop_id: int, business_date: datetime,
) -> bool:
    query = db.query(CashRegisterClose.id).join(
        User, User.id == CashRegisterClose.closed_by_user_id,
    ).filter(
        CashRegisterClose.barbershop_id == barbershop_id,
        CashRegisterClose.business_date == business_date,
        CashRegisterClose.is_deleted == False,
    )
    if user.role == "barber":
        query = query.filter(or_(
            CashRegisterClose.closed_by_user_id == user.id,
            (User.role == "barbershop_owner") & (User.barbershop_id == barbershop_id),
        ))
    else:
        query = query.filter(CashRegisterClose.closed_by_user_id == user.id)
    # A locking read uses current committed state after waiting on the shared
    # barbershop mutex; a repeatable-read snapshot could miss a close that just won.
    return query.with_for_update().first() is not None


def _service_progress_percent(appointment: Appointment, now_utc: datetime) -> int:
    """Estimate elapsed service time from the persisted UTC start timestamp."""
    if not appointment.actual_start_time or appointment.estimated_duration <= 0:
        return 0
    elapsed_minutes = max(0, (now_utc - appointment.actual_start_time).total_seconds() / 60)
    return min(100, int(round(elapsed_minutes / appointment.estimated_duration * 100)))


def _audit(db: Session, actor: Optional[User], action: str, entity_type: str, entity_id: int | None,
           barbershop_id: int | None = None, details: dict | None = None) -> None:
    """Add a minimal audit event to the current transaction without credentials or secrets."""
    record_audit(db, actor, action, entity_type, entity_id, barbershop_id, details)


def _get_user_feature_flags(db: Session, user_id: int) -> dict[str, bool]:
    rows = db.query(UserFeatureFlag.feature_key, UserFeatureFlag.enabled).filter(
        UserFeatureFlag.user_id == user_id,
        UserFeatureFlag.is_deleted == False,
    ).all()
    return {key: bool(enabled) for key, enabled in rows}


def _notify_appointment_staff(
    db: Session,
    appointment: Appointment,
    event_type: str,
    title: str,
    message: str,
    additional_barber_ids: tuple[int, ...] = (),
    exclude_user_id: Optional[int] = None,
    dedupe_suffix: Optional[str] = None,
) -> None:
    """Add idempotent tenant staff inbox rows to the current business transaction."""
    recipient_ids = set(additional_barber_ids)
    if appointment.barber_id:
        recipient_ids.add(appointment.barber_id)
    recipient_ids.update(row[0] for row in db.query(User.id).filter(
        User.barbershop_id == appointment.barbershop_id,
        User.role == "barbershop_owner",
        User.is_active == True,
        User.is_deleted == False,
    ).all())
    suffix = f":{dedupe_suffix}" if dedupe_suffix else ""
    for recipient_id in recipient_ids:
        if recipient_id == exclude_user_id:
            continue
        dedupe_key = f"appointment:{appointment.id}:{event_type}{suffix}:user:{recipient_id}"
        exists = db.query(InAppNotification.id).filter(
            InAppNotification.recipient_user_id == recipient_id,
            InAppNotification.dedupe_key == dedupe_key,
        ).first()
        if exists:
            continue
        db.add(InAppNotification(
            barbershop_id=appointment.barbershop_id,
            recipient_user_id=recipient_id,
            dedupe_key=dedupe_key,
            event_type=event_type,
            title=title,
            message=message[:1000],
            entity_type="appointment",
            entity_id=appointment.id,
            created_at=utc_now_naive(),
        ))


@router.get("/notifications")
def list_in_app_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if not user.barbershop_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una barbería asignada")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="El límite debe estar entre 1 y 100")
    query = db.query(InAppNotification).filter(
        InAppNotification.barbershop_id == user.barbershop_id,
        InAppNotification.recipient_user_id == user.id,
        InAppNotification.is_deleted == False,
    )
    unread_count = query.filter(InAppNotification.read_at.is_(None)).count()
    if unread_only:
        query = query.filter(InAppNotification.read_at.is_(None))
    rows = query.order_by(InAppNotification.created_at.desc(), InAppNotification.id.desc()).limit(limit).all()
    return {
        "unread_count": unread_count,
        "items": [{
            "id": row.id,
            "event_type": row.event_type,
            "title": row.title,
            "message": row.message,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat(),
            "read_at": row.read_at.isoformat() if row.read_at else None,
        } for row in rows],
    }


@router.get("/notifications/unread-count")
def get_in_app_notification_unread_count(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Return only the authenticated user's tenant-scoped unread count."""
    user = _get_current_user(db, authorization)
    if not user.barbershop_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una barbería asignada")
    unread_count = db.query(func.count(InAppNotification.id)).filter(
        InAppNotification.barbershop_id == user.barbershop_id,
        InAppNotification.recipient_user_id == user.id,
        InAppNotification.read_at.is_(None),
        InAppNotification.is_deleted == False,
    ).scalar() or 0
    return {"unread_count": int(unread_count)}


@router.post("/notifications/{notification_id}/read")
def mark_in_app_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if not user.barbershop_id:
        raise HTTPException(status_code=403, detail="El usuario no tiene una barbería asignada")
    row = db.query(InAppNotification).filter(
        InAppNotification.id == notification_id,
        InAppNotification.barbershop_id == user.barbershop_id,
        InAppNotification.recipient_user_id == user.id,
        InAppNotification.is_deleted == False,
    ).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    if row.read_at is None:
        row.read_at = utc_now_naive()
        db.commit()
    return {"success": True, "notification_id": row.id,
            "read_at": row.read_at.isoformat()}


def _local_day_bounds(now_utc: datetime, shop: Barbershop):
    tz = _get_timezone(shop)
    today = _utc_aware(now_utc).astimezone(tz).date()

    def midnight(day):
        return local_day_start_utc_naive(day, tz)

    return midnight(today), midnight(today + timedelta(days=1)), midnight(today - timedelta(days=1)), midnight(today - timedelta(days=6))


def _prepare_appointment_email(
    db: Session, appointment: Appointment, event: str, reason: str | None = None
) -> tuple[str, str, str] | None:
    """Render an email while request data is available; deliver after the response."""
    client = db.query(User).filter(User.id == appointment.client_id).first()
    if not client or not client.email or client.email.endswith("@client.invalid"):
        return None
    barber = db.query(User).filter(User.id == appointment.barber_id).first()
    shop = db.query(Barbershop).filter(Barbershop.id == appointment.barbershop_id).first()
    if not barber or not shop:
        logger.error("Appointment email skipped because related records are missing",
                     extra={"appointment_id": appointment.id, "event": event})
        return None

    notifications = NotificationService(db)
    local_scheduled_time = _utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop))
    if event == "booking_received":
        body = _email_html_lines([
            f"Hola {client.full_name}",
            f"Recibimos tu solicitud de cita en {shop.name}.",
            f"Servicio: {appointment.service_type}",
            f"Barbero: {barber.full_name}",
            f"Fecha y hora solicitadas: {local_scheduled_time.strftime('%d/%m/%Y %H:%M')}",
            f"Duración estimada: {appointment.estimated_duration} minutos",
            "La cita está pendiente de confirmación por la barbería. Te avisaremos cuando se confirme.",
        ])
        subject = f"Solicitud de cita recibida - {shop.name}"
    elif event == "confirmation":
        body = notifications._get_confirmation_email_template(
            client_name=client.full_name,
            barber_name=barber.full_name,
            barbershop_name=shop.name,
            scheduled_time=local_scheduled_time,
            service_type=appointment.service_type,
            estimated_duration=appointment.estimated_duration,
            barbershop_address=shop.address_line1 or "N/A",
            barbershop_phone=shop.phone or "N/A",
        )
        subject = f"Cita confirmada - {shop.name}"
    elif event == "cancellation":
        body = notifications._get_cancellation_email_template(
            client_name=client.full_name,
            barbershop_name=shop.name,
            scheduled_time=local_scheduled_time,
            reason=reason or "No especificada",
        )
        subject = f"Cita cancelada - {shop.name}"
    elif event == "reschedule":
        body = _email_html_lines([
            f"Hola {client.full_name}",
            f"Tu cita en {shop.name} fue reprogramada.",
            f"Servicio: {appointment.service_type}",
            f"Barbero: {barber.full_name}",
            f"Nueva fecha y hora: {local_scheduled_time.strftime('%d/%m/%Y %H:%M')}",
            f"Duración estimada: {appointment.estimated_duration} minutos",
            "Si necesitas cambiarla, usa el enlace de seguimiento que recibiste al reservar.",
        ])
        subject = f"Cita reprogramada - {shop.name}"
    elif event == "completion":
        body = notifications._get_completion_email_template(
            client_name=client.full_name,
            barber_name=barber.full_name,
            barbershop_name=shop.name,
        )
        subject = f"Gracias por tu visita - {shop.name}"
    else:
        raise ValueError(f"Unsupported appointment email event: {event}")
    return client.email, subject, body


def _email_html_lines(lines: list[str]) -> str:
    """Render escaped, readable HTML for concise transactional email messages."""
    return "<html><body><p>" + "<br>".join(escape_html(line) for line in lines) + "</p></body></html>"


def _queue_appointment_email(
    db: Session,
    appointment: Appointment,
    event: str,
    reason: str | None = None,
    dedupe_suffix: str | None = None,
) -> None:
    email = _prepare_appointment_email(db, appointment, event, reason)
    if not email:
        return
    recipient, subject, body = email
    suffix = f":{dedupe_suffix}" if dedupe_suffix else ""
    enqueue_delivery(
        db,
        barbershop_id=appointment.barbershop_id,
        appointment_id=appointment.id,
        dedupe_key=f"appointment:{appointment.id}:{event}{suffix}:email",
        channel="email",
        event_type=f"appointment_{event.split(':', 1)[0]}",
        recipient=recipient,
        subject=subject,
        body=body,
    )


def _queue_appointment_whatsapp(
    db: Session,
    appointment: Appointment,
    recipient: str,
    message: str,
    event: str,
    dedupe_suffix: str | None = None,
) -> None:
    suffix = f":{dedupe_suffix}" if dedupe_suffix else ""
    enqueue_delivery(
        db,
        barbershop_id=appointment.barbershop_id,
        appointment_id=appointment.id,
        dedupe_key=(
            f"appointment:{appointment.id}:{event}{suffix}:whatsapp:"
            f"{hashlib.sha256(recipient.encode()).hexdigest()[:16]}"
        ),
        channel="whatsapp",
        event_type=f"appointment_{event.split(':', 1)[0]}",
        recipient=recipient,
        body=message,
    )


def _send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an actual SMTP message; never report success for a console placeholder."""
    if not all((
        settings.SMTP_USER.strip(), settings.SMTP_PASSWORD,
        settings.SMTP_HOST.strip(), settings.EMAIL_FROM.strip(),
    )):
        return False
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=8) as smtp:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=8) as smtp:
                smtp.starttls()
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        return True
    except Exception:
        logger.warning("Support email delivery failed", extra={"recipient": to_email})
        return False


def _get_current_user(db: Session, authorization: Optional[str]) -> User:
    """Use the shared authentication checks for every platform route."""
    return authenticate_user(authorization, db)


def _save_refresh_session(db: Session, user_id: int, token: str) -> RefreshSession:
    payload = verify_token(token, token_type="refresh")
    expires_at = datetime.fromtimestamp(float(payload["exp"]), timezone.utc).replace(tzinfo=None)
    session = RefreshSession(user_id=user_id, jti=payload["jti"], expires_at=expires_at)
    db.add(session)
    return session


LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
SUPPORT_MESSAGE_WINDOW = timedelta(hours=1)
SUPPORT_MESSAGE_LIMIT = 5
PUBLIC_BOOKING_WINDOW = timedelta(hours=1)
PUBLIC_BOOKING_TENANT_IP_LIMIT = 10
PUBLIC_BOOKING_IP_LIMIT = 60
PUBLIC_TRACK_IP_LIMIT = 120
PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT = 20


def _login_bucket_hash(kind: str, value: str) -> str:
    material = f"{kind}:{value}:{settings.SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _login_buckets(email: str, ip_address: str) -> list[tuple[str, int]]:
    return [
        (_login_bucket_hash("email", email.strip().lower()), 5),
        (_login_bucket_hash("ip", ip_address), 50),
    ]


def _lock_or_create_login_attempt(db: Session, key_hash: str, now: datetime) -> LoginAttempt:
    """Atomically ensure and lock a MySQL throttle row, including on first use."""
    statement = mysql_insert(LoginAttempt).values(
        key_hash=key_hash,
        failed_count=0,
        window_started_at=now,
        last_attempt_at=now,
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )
    db.execute(statement.on_duplicate_key_update(key_hash=statement.inserted.key_hash))
    return db.query(LoginAttempt).filter(
        LoginAttempt.key_hash == key_hash,
        LoginAttempt.is_deleted == False,
    ).with_for_update().one()


def _check_login_throttle(db: Session, buckets: list[tuple[str, int]], now: datetime) -> None:
    # Insert and lock both rows as one ordered MySQL operation. Separate
    # first-use inserts can deadlock when many identical logins race to create
    # the email and IP buckets at the same time. Commit each single-row ensure
    # independently, then lock the existing pair in a stable order.
    ordered = sorted(buckets)
    def lock_buckets():
        for key_hash, _ in ordered:
            db.execute(mysql_insert(LoginAttempt).values(
                key_hash=key_hash,
                failed_count=0,
                window_started_at=now,
                last_attempt_at=now,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            ).prefix_with("IGNORE"))
            db.commit()
        return db.query(LoginAttempt).filter(
            LoginAttempt.key_hash.in_([key_hash for key_hash, _ in ordered]),
            LoginAttempt.is_deleted == False,
        ).order_by(LoginAttempt.key_hash.asc()).with_for_update().all()

    attempt_rows = _retry_login_deadlock(db, lock_buckets)
    attempts_by_hash = {attempt.key_hash: attempt for attempt in attempt_rows}
    for key_hash, _ in ordered:
        attempt = attempts_by_hash[key_hash]
        if attempt and attempt.locked_until and attempt.locked_until > now:
            raise HTTPException(status_code=429, detail="Demasiados intentos. Espera 15 minutos y vuelve a intentar.")


def _retry_login_deadlock(db: Session, operation):
    """Retry rare InnoDB deadlocks from concurrent first-use bucket inserts."""
    for retry in range(4):
        try:
            return operation()
        except OperationalError as exc:
            error_code = exc.orig.args[0] if getattr(exc, "orig", None) and exc.orig.args else None
            if error_code not in {1205, 1213} or retry == 3:
                raise
            db.rollback()
            sleep_seconds(0.01 * (retry + 1))
    raise RuntimeError("No se pudo adquirir el bloqueo de autenticación")


def _record_login_failure(db: Session, buckets: list[tuple[str, int]], now: datetime) -> None:
    # The check already created and locked these rows. Re-entering through an
    # upsert here can deadlock concurrent MySQL inserts for the same bucket set.
    def record_failures():
        for key_hash, limit in sorted(buckets):
            attempt = db.query(LoginAttempt).filter(
                LoginAttempt.key_hash == key_hash,
                LoginAttempt.is_deleted == False,
            ).with_for_update().one()
            if now - attempt.window_started_at >= LOGIN_FAILURE_WINDOW:
                attempt.failed_count = 0
                attempt.window_started_at = now
                attempt.locked_until = None
            attempt.failed_count += 1
            attempt.last_attempt_at = now
            if attempt.failed_count >= limit:
                attempt.locked_until = now + LOGIN_FAILURE_WINDOW
        db.commit()

    _retry_login_deadlock(db, record_failures)


def _clear_login_failures(db: Session, buckets: list[tuple[str, int]], now: datetime) -> None:
    for key_hash, _ in sorted(buckets):
        attempt = db.query(LoginAttempt).filter(
            LoginAttempt.key_hash == key_hash,
            LoginAttempt.is_deleted == False,
        ).with_for_update().first()
        if attempt:
            attempt.failed_count = 0
            attempt.window_started_at = now
            attempt.last_attempt_at = now
            attempt.locked_until = None


def _consume_support_message_quota(db: Session, ip_address: str, now: datetime) -> None:
    """Apply a database-backed per-IP support message quota without storing the IP."""
    prune_expired_auth_records(db, now)
    key_hash = _login_bucket_hash("support-ip", ip_address)
    attempt = _lock_or_create_login_attempt(db, key_hash, now)
    if now - attempt.window_started_at >= SUPPORT_MESSAGE_WINDOW:
        attempt.failed_count = 0
        attempt.window_started_at = now
        attempt.locked_until = None
    if attempt.locked_until and attempt.locked_until > now:
        raise HTTPException(status_code=429, detail="Límite de mensajes de soporte alcanzado. Intenta más tarde.")
    attempt.failed_count += 1
    attempt.last_attempt_at = now
    if attempt.failed_count >= SUPPORT_MESSAGE_LIMIT:
        attempt.locked_until = now + SUPPORT_MESSAGE_WINDOW
    db.commit()


def _consume_public_booking_quota(
    db: Session, barbershop_id: int, ip_address: str, now: datetime,
) -> None:
    """Limit anonymous booking requests per tenant and source IP in MySQL."""
    buckets = sorted([
        (_login_bucket_hash("booking-tenant-ip", f"{barbershop_id}:{ip_address}"), PUBLIC_BOOKING_TENANT_IP_LIMIT),
        (_login_bucket_hash("booking-ip", ip_address), PUBLIC_BOOKING_IP_LIMIT),
    ])
    def consume():
        for key_hash, _limit in buckets:
            statement = mysql_insert(LoginAttempt).values(
                key_hash=key_hash,
                failed_count=0,
                window_started_at=now,
                last_attempt_at=now,
                created_at=now,
                updated_at=now,
                is_deleted=False,
            ).prefix_with("IGNORE")
            db.execute(statement)

        attempts = db.query(LoginAttempt).filter(
            LoginAttempt.key_hash.in_([key_hash for key_hash, _limit in buckets]),
            LoginAttempt.is_deleted == False,
        ).order_by(LoginAttempt.key_hash.asc()).with_for_update().all()
        attempts_by_hash = {attempt.key_hash: attempt for attempt in attempts}
        for key_hash, limit in buckets:
            attempt = attempts_by_hash[key_hash]
            if now - attempt.window_started_at >= PUBLIC_BOOKING_WINDOW:
                attempt.failed_count = 0
                attempt.window_started_at = now
            if attempt.failed_count >= limit:
                retry_after = max(
                    1,
                    int((attempt.window_started_at + PUBLIC_BOOKING_WINDOW - now).total_seconds()),
                )
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail="Se alcanzó el límite temporal de reservas. Intenta de nuevo más tarde.",
                    headers={"Retry-After": str(retry_after)},
                )
        for key_hash, _limit in buckets:
            attempt = attempts_by_hash[key_hash]
            attempt.failed_count += 1
            attempt.last_attempt_at = now
        db.commit()

    _retry_login_deadlock(db, consume)


def _consume_public_token_quota(
    db: Session, action: str, ip_address: str, now: datetime, limit: int,
) -> None:
    """Bound anonymous token lookups and mutations without retaining raw IPs."""
    prune_expired_auth_records(db, now)
    key_hash = _login_bucket_hash(f"public-{action}-ip", ip_address)

    def consume():
        attempt = _lock_or_create_login_attempt(db, key_hash, now)
        if now - attempt.window_started_at >= PUBLIC_BOOKING_WINDOW:
            attempt.failed_count = 0
            attempt.window_started_at = now
            attempt.locked_until = None
        if attempt.locked_until and attempt.locked_until > now:
            retry_after = max(1, int((attempt.locked_until - now).total_seconds()))
            db.commit()
            raise HTTPException(
                status_code=429,
                detail="Se alcanzó el límite temporal de solicitudes. Intenta más tarde.",
                headers={"Retry-After": str(retry_after)},
            )
        attempt.failed_count += 1
        attempt.last_attempt_at = now
        if attempt.failed_count >= limit:
            attempt.locked_until = attempt.window_started_at + PUBLIC_BOOKING_WINDOW
        db.commit()

    _retry_login_deadlock(db, consume)


def _public_booking_client_ip(request: Request) -> str:
    """Read the socket IP or one explicitly configured, trusted proxy header."""
    return get_client_ip(request, settings.CLIENT_IP_HEADER)


@router.post("/auth/login", response_model=AuthLoginResponse)
def auth_login(data: AuthLoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request, settings.CLIENT_IP_HEADER)
    buckets = _login_buckets(str(data.email), client_ip)
    now = utc_now_naive()
    prune_expired_auth_records(db, now)
    _check_login_throttle(db, buckets, now)
    normalized_email = str(data.email).strip().lower()
    user = db.query(User).filter(User.email == normalized_email, User.is_deleted == False).first()
    password_hash = user.password_hash if user else DUMMY_LOGIN_PASSWORD_HASH
    password_valid = verify_password(data.password, password_hash)
    if not user or not password_valid or not user.is_active:
        _record_login_failure(db, buckets, now)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    if user.barbershop_id and user.role != "super_admin":
        active_shop = db.query(Barbershop.id).filter(
            Barbershop.id == user.barbershop_id,
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        ).first()
        if not active_shop:
            raise HTTPException(status_code=403, detail="La barbería está desactivada")

    refresh_token = create_refresh_token({"sub": str(user.id), "auth_version": user.auth_version})
    refresh_session = _save_refresh_session(db, user.id, refresh_token)
    access_token = create_access_token({
        "sub": str(user.id), "role": user.role,
        "auth_version": user.auth_version, "sid": refresh_session.jti,
    })
    _clear_login_failures(db, buckets, now)
    db.commit()

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
            feature_flags=_get_user_feature_flags(db, user.id),
        ),
    )


def _tenant_slug(db: Session, name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:80] or "barberia"
    while True:
        slug = f"{base}-{secrets.token_hex(3)}"
        exists = db.query(Barbershop.id).filter(Barbershop.slug == slug).first()
        if not exists:
            return slug


def _flush_tenant_registration(db: Session) -> None:
    """Translate uniqueness races into a clean conflict and roll back all rows."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo completar el registro con esos datos") from exc


def _lock_platform_settings(db: Session) -> PlatformSettings:
    """Create the singleton defaults if needed, then lock them for signup."""
    statement = mysql_insert(PlatformSettings).values(
        id=1,
        registrations_enabled=True,
        free_period_days=30,
        updated_by_user_id=None,
        created_at=func.now(),
        updated_at=func.now(),
        is_deleted=False,
        deleted_at=None,
    )
    db.execute(statement.on_duplicate_key_update(id=statement.inserted.id))
    return db.query(PlatformSettings).filter(PlatformSettings.id == 1).with_for_update().one()


@router.post("/saas/register", response_model=AuthLoginResponse, status_code=201)
def register_tenant(data: TenantRegistrationRequest, db: Session = Depends(get_db)):
    """Atomically register a barber shop owner, the tenant and a free subscription."""
    platform_settings = _lock_platform_settings(db)
    if not platform_settings.registrations_enabled:
        raise HTTPException(status_code=503, detail="El registro de nuevas barberías está temporalmente cerrado")
    existing_user = db.query(User.id).filter(
        User.email == str(data.owner_email).lower(),
        User.is_deleted == False,
    ).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Ese correo ya está registrado")

    affiliate = None
    if data.affiliate_code:
        affiliate = db.query(Affiliate).filter(
            Affiliate.code == data.affiliate_code,
            Affiliate.is_active == True,
            Affiliate.is_deleted == False,
        ).with_for_update().first()
        if not affiliate:
            raise HTTPException(status_code=422, detail="El código de afiliado no es válido")

    now = utc_now_naive()
    subscription = Subscription(
        plan="free",
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=platform_settings.free_period_days if platform_settings else 30),
        auto_renew=False,
        is_trial=False,
    )
    _apply_plan_limits(subscription, "free")
    db.add(subscription)
    _flush_tenant_registration(db)

    shop = Barbershop(
        name=data.barbershop_name,
        slug=_tenant_slug(db, data.barbershop_name),
        email=str(data.barbershop_email).lower(),
        phone=data.barbershop_phone,
        address_line1=data.address_line1,
        city=data.city,
        state=data.state,
        postal_code=data.postal_code,
        country=data.country,
        timezone=data.timezone,
        currency=data.currency,
        subscription_id=subscription.id,
        referred_by_affiliate_id=affiliate.id if affiliate else None,
        is_active=True,
    )
    db.add(shop)
    _flush_tenant_registration(db)

    owner = User(
        email=str(data.owner_email).lower(),
        password_hash=hash_password(data.owner_password),
        first_name=data.owner_first_name,
        last_name=data.owner_last_name,
        phone=data.owner_phone,
        role="barbershop_owner",
        is_active=True,
        is_verified=False,
        barbershop_id=shop.id,
    )
    db.add(owner)
    _flush_tenant_registration(db)

    if affiliate:
        affiliate.total_referrals = (affiliate.total_referrals or 0) + 1
        affiliate.active_referrals = (affiliate.active_referrals or 0) + 1
        _audit(db, owner, "tenant.referred", "barbershop", shop.id, shop.id,
               {"affiliate_id": affiliate.id})

    refresh_token = create_refresh_token({"sub": str(owner.id), "auth_version": owner.auth_version})
    refresh_session = _save_refresh_session(db, owner.id, refresh_token)
    access_token = create_access_token({
        "sub": str(owner.id), "role": owner.role,
        "auth_version": owner.auth_version, "sid": refresh_session.jti,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo completar el registro con esos datos") from exc

    return AuthLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=AuthUserResponse(
            id=owner.id,
            email=owner.email,
            full_name=owner.full_name,
            role=owner.role,
            barbershop_id=shop.id,
        ),
    )


@router.post("/auth/refresh", response_model=RefreshTokenResponse)
def auth_refresh(data: RefreshTokenRequest, db: Session = Depends(get_db)):
    try:
        payload = verify_token(data.refresh_token, token_type="refresh")
        user_id = int(payload.get("sub", ""))
        token_id = payload.get("jti")
    except (TypeError, ValueError, Exception) as exc:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada") from exc

    now = utc_now_naive()
    session = db.query(RefreshSession).filter(
        RefreshSession.jti == token_id,
        RefreshSession.user_id == user_id,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.expires_at > now,
        RefreshSession.is_deleted == False,
    ).with_for_update().first()
    if not session:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True,
        User.is_deleted == False,
    ).first()
    if not user:
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    if payload.get("auth_version", 0) != user.auth_version:
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    session.revoked_at = now
    refresh_token = create_refresh_token({"sub": str(user.id), "auth_version": user.auth_version})
    refresh_session = _save_refresh_session(db, user.id, refresh_token)
    access_token = create_access_token({
        "sub": str(user.id), "role": user.role,
        "auth_version": user.auth_version, "sid": refresh_session.jti,
    })
    db.commit()
    return RefreshTokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/logout")
def auth_logout(data: RefreshTokenRequest, db: Session = Depends(get_db)):
    try:
        payload = verify_token(data.refresh_token, token_type="refresh")
    except Exception:
        return {"success": True}
    token_id = payload.get("jti")
    if token_id:
        db.query(RefreshSession).filter(
            RefreshSession.jti == token_id,
            RefreshSession.revoked_at.is_(None),
        ).update({RefreshSession.revoked_at: utc_now_naive()}, synchronize_session=False)
        db.commit()
    return {"success": True}


@router.post("/auth/change-password")
def auth_change_password(
    data: PasswordChangeRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    user.password_hash = hash_password(data.new_password)
    user.auth_version += 1
    now = utc_now_naive()
    db.query(RefreshSession).filter(
        RefreshSession.user_id == user.id,
        RefreshSession.revoked_at.is_(None),
    ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    _audit(db, user, "auth.password_changed", "user", user.id, user.barbershop_id,
           {"method": "authenticated"})
    db.commit()
    return {"success": True, "message": "Contraseña actualizada; inicia sesión de nuevo en tus otros dispositivos"}


@router.post("/support/contact")
def support_contact(data: SupportRequest, request: Request, db: Session = Depends(get_db)):
    _consume_support_message_quota(
        db, get_client_ip(request, settings.CLIENT_IP_HEADER), utc_now_naive()
    )
    recipient_query = db.query(User).filter(
        User.is_active == True,
        User.is_deleted == False,
        User.support_contact_enabled == True,
    )
    if data.barbershop_slug:
        shop = db.query(Barbershop).filter(
            Barbershop.slug == data.barbershop_slug,
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        ).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Barbería no encontrada")
        recipient_query = recipient_query.filter(
            User.barbershop_id == shop.id,
            User.role.in_(["barbershop_owner", "barber"]),
        )
    else:
        shop = None
        recipient_query = recipient_query.filter(User.role == "super_admin")
    recipients = recipient_query.order_by(User.id.asc()).all()

    ticket = SupportTicket(
        barbershop_id=shop.id if shop else None,
        sender_name=data.name.strip(),
        sender_email=str(data.email).strip().lower() if data.email else None,
        sender_phone=data.phone.strip() if data.phone else None,
        message=data.message.strip(),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    subject = f"Solicitud de soporte #{ticket.id}"
    body = (
        f"Solicitud #{ticket.id}\n"
        f"Barbería: {shop.name if shop else 'Plataforma'}\n"
        f"Nombre: {data.name}\n"
        f"Email: {data.email or '-'}\n"
        f"Teléfono: {data.phone or '-'}\n"
        f"Mensaje: {data.message}\n"
    )

    sent = sum(1 for user in recipients if user.email and _send_email(user.email, subject, body))
    if sent:
        ticket.notification_sent = True
        db.commit()

    return {
        "success": True,
        "ticket_id": ticket.id,
        "notification_sent": ticket.notification_sent,
        "sent_to": sent,
    }


@router.get("/admin/support/tickets")
def admin_list_support_tickets(
    status: Optional[str] = Query(None, pattern=r"^(open|in_progress|resolved|closed)$"),
    barbershop_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo el superadministrador puede consultar soporte")
    query = db.query(SupportTicket).filter(SupportTicket.is_deleted == False)
    if status:
        query = query.filter(SupportTicket.status == status)
    if barbershop_id is not None:
        query = query.filter(SupportTicket.barbershop_id == barbershop_id)
    total = query.order_by(None).count()
    tickets = (
        query.order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
        .offset(offset).limit(limit).all()
    )
    return {"items": [{
        "id": ticket.id,
        "barbershop_id": ticket.barbershop_id,
        "barbershop_name": ticket.barbershop.name if ticket.barbershop else "Plataforma",
        "name": ticket.sender_name,
        "email": ticket.sender_email,
        "phone": ticket.sender_phone,
        "message": ticket.message,
        "status": ticket.status,
        "notification_sent": ticket.notification_sent,
        "created_at": ticket.created_at.isoformat(),
    } for ticket in tickets], "total": total, "limit": limit, "offset": offset}


@router.put("/admin/support/tickets/{ticket_id}/status")
def admin_update_support_ticket_status(
    ticket_id: int,
    data: AdminSupportTicketStatusRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo el superadministrador puede gestionar soporte")
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.is_deleted == False,
    ).with_for_update().first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Solicitud de soporte no encontrada")
    previous = ticket.status
    ticket.status = data.status
    _audit(db, admin, "support.ticket_status_changed", "support_ticket", ticket.id,
           ticket.barbershop_id, {"previous": previous, "status": ticket.status})
    db.commit()
    return {"success": True, "ticket_id": ticket.id, "status": ticket.status}


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
        feature_flags=_get_user_feature_flags(db, user.id),
    )


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
        logo_url=shop.logo_url,
        primary_color=shop.primary_color,
        secondary_color=shop.secondary_color,
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
        )
        for s in services
    ]


def _slot_available_for_duration(
    slot: BarberAvailability,
    blocks: list[BarberAvailabilityBlock],
    appointments: list[Appointment],
    duration_minutes: int,
) -> bool:
    duration = timedelta(minutes=duration_minutes)
    if slot.slot_end - slot.slot_start < duration:
        return False
    service_end = slot.slot_start + duration
    if any(block.starts_at < service_end and block.ends_at > slot.slot_start for block in blocks):
        return False
    return not any(
        appointment.scheduled_time < service_end
        and appointment.scheduled_time + timedelta(minutes=appointment.estimated_duration) > slot.slot_start
        for appointment in appointments
    )


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
):
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _require_active_subscription(db, shop)
    source_ip = _public_booking_client_ip(request)
    _consume_public_booking_quota(db, shop.id, source_ip, utc_now_naive())
    subscription = _require_active_subscription(db, shop, lock=True)
    if subscription.max_appointments_per_month is not None:
        used = count_monthly_appointments(db, shop)
        if used >= subscription.max_appointments_per_month:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de citas de su plan")

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
        # Public bookings do not collect email. Keep a unique, non-deliverable
        # address without copying the client's phone number into the email field.
        synthetic_email = f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid"

        client = User(
            email=synthetic_email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
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
    _queue_appointment_whatsapp(db, appointment, phone, wa_message, "confirmation:client")

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
        _queue_appointment_whatsapp(db, appointment, barber_phone, barber_msg, "confirmation:barber")

    db.commit()
    db.refresh(appointment)

    return PublicCreateAppointmentResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        tracking_link=tracking_link,
        message="Cita agendada correctamente",
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
            is_verified=True,
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

    return PublicTrackAppointmentResponse(items=[
        PublicTrackAppointmentItem(
            appointment_id=appointment.id,
            status=appointment.status,
            scheduled_time=_utc_aware(appointment.scheduled_time),
            service_type=appointment.service_type,
            barber_name=appointment.barber.full_name if appointment.barber else None,
            estimated_duration=appointment.estimated_duration,
        )
    ])


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
    if appointment.status not in {"pending", "confirmed"}:
        raise HTTPException(status_code=409, detail="La cita ya no se puede cancelar")
    if appointment.scheduled_time <= utc_now_naive():
        raise HTTPException(status_code=409, detail="No se puede cancelar una cita que ya comenzó")

    appointment.status = "cancelled"
    appointment.cancelled_by = appointment.client_id
    appointment.cancellation_reason = data.reason
    _notify_appointment_staff(
        db, appointment, "appointment_cancelled", "Cita cancelada por el cliente",
        f"{appointment.service_type} · {_utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')}",
    )
    _audit(db, None, "appointment.cancelled_by_client", "appointment", appointment.id,
           shop.id, {"reason": data.reason})
    db.query(BarberAvailability).filter(
        BarberAvailability.barbershop_id == shop.id,
        BarberAvailability.barber_id == appointment.barber_id,
        BarberAvailability.slot_start == appointment.scheduled_time,
        BarberAvailability.is_booked == True,
        BarberAvailability.is_deleted == False,
    ).update({BarberAvailability.is_booked: False}, synchronize_session=False)
    _queue_appointment_email(db, appointment, "cancellation", data.reason)
    if appointment.client and appointment.client.phone:
        _queue_appointment_whatsapp(
            db, appointment, appointment.client.phone,
            f"La cita en {shop.name} para {_utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')} fue cancelada.",
            "cancellation:client",
        )
    db.commit()
    return {"success": True, "appointment_id": appointment.id, "status": appointment.status}


@router.post("/public/{slug}/appointments/reschedule")
def public_reschedule_appointment(
    slug: str,
    data: PublicRescheduleAppointmentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Move a private booking to a free slot without exposing client identity."""
    shop = _get_public_shop(db, slug)
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    _consume_public_token_quota(
        db, "appointment-change", _public_booking_client_ip(request),
        utc_now_naive(), PUBLIC_APPOINTMENT_CHANGE_IP_LIMIT,
    )
    _require_active_subscription(db, shop, lock=True)

    token_hash = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    appointment_ref = db.query(
        Appointment.id, Appointment.barber_id, Appointment.scheduled_time,
    ).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.tracking_token_hash == token_hash,
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

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_ref.id,
        Appointment.barbershop_id == shop.id,
        Appointment.tracking_token_hash == token_hash,
        Appointment.is_deleted == False,
    ).with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.barber_id != appointment_ref.barber_id:
        raise HTTPException(status_code=409, detail="La asignación de la cita cambió; vuelve a consultar")
    if appointment.status not in {"pending", "confirmed"} or appointment.scheduled_time <= utc_now_naive():
        raise HTTPException(status_code=409, detail="La cita ya no se puede reprogramar")

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
    appointment.barber_id = barber.id
    _notify_appointment_staff(
        db, appointment, "appointment_rescheduled", "Cita reprogramada",
        f"{appointment.service_type} · {_utc_aware(new_start).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')}",
        additional_barber_ids=(old_barber_id,),
        dedupe_suffix=reschedule_event_id,
    )
    _audit(db, None, "appointment.rescheduled_by_client", "appointment", appointment.id, shop.id,
           {"previous_time": old_start.isoformat(), "new_time": new_start.isoformat(),
            "previous_barber_id": old_barber_id, "new_barber_id": barber.id})
    if appointment.client and appointment.client.phone:
        _queue_appointment_whatsapp(
            db, appointment, appointment.client.phone,
            f"Tu cita en {shop.name} fue reprogramada para "
            f"{_utc_aware(new_start).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')}.",
            "rescheduled:client",
            dedupe_suffix=reschedule_event_id,
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


@router.get("/owner/barbers")
def owner_list_barbers(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    barbers = db.query(User).filter(
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).order_by(User.first_name.asc(), User.last_name.asc()).all()
    return {"items": [{"id": barber.id, "email": barber.email,
                       "first_name": barber.first_name, "last_name": barber.last_name,
                       "full_name": barber.full_name, "phone": barber.phone,
                       "is_active": barber.is_active,
                       "commission_rate_basis_points": barber.commission_rate_basis_points}
                      for barber in barbers]}


@router.post("/owner/barbers", status_code=201)
def owner_create_barber(
    data: OwnerCreateBarberRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    subscription = _require_active_subscription(db, shop, lock=True)
    barber_count = db.query(User.id).filter(
        User.barbershop_id == shop.id,
        User.role == "barber",
        User.is_active == True,
        User.is_deleted == False,
    ).count()
    if subscription.max_barbers is not None and barber_count >= subscription.max_barbers:
        raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de barberos de su plan")
    email = str(data.email).lower()
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="El correo ya está registrado")
    barber = User(
        email=email,
        password_hash=hash_password(data.password),
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        phone=_normalize_phone(data.phone or "") or None,
        role="barber",
        is_active=True,
        is_verified=False,
        barbershop_id=shop.id,
    )
    db.add(barber)
    try:
        db.flush()
        _audit(db, owner, "barber.created", "user", barber.id, shop.id, {"email": barber.email})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El correo ya está registrado") from exc
    return {"id": barber.id, "email": barber.email, "full_name": barber.full_name,
            "phone": barber.phone, "is_active": barber.is_active}


@router.put("/owner/barbers/{barber_id}/status")
def owner_update_barber_status(
    barber_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    # Serialize activations with barber creation so simultaneous changes cannot
    # exceed the subscription's seat limit.
    subscription = None
    if data.is_active:
        subscription = _require_active_subscription(db, shop, lock=True)
    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    if data.is_active and not barber.is_active:
        active_count = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "barber",
            User.is_active == True,
            User.is_deleted == False,
        ).count()
        if subscription.max_barbers is not None and active_count >= subscription.max_barbers:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de barberos de su plan")
    barber.is_active = data.is_active
    _audit(db, owner, "barber.status_changed", "user", barber.id, owner.barbershop_id,
           {"is_active": data.is_active})
    db.commit()
    return {"success": True, "barber_id": barber.id, "is_active": barber.is_active}


@router.put("/owner/barbers/{barber_id}")
def owner_update_barber(
    barber_id: int,
    data: OwnerBarberUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar su equipo")
    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    barber.first_name = data.first_name
    barber.last_name = data.last_name
    barber.phone = _normalize_phone(data.phone or "") or None
    _audit(db, owner, "barber.profile_updated", "user", barber.id, owner.barbershop_id,
           {"updated_fields": ["first_name", "last_name", "phone"]})
    db.commit()
    return {"id": barber.id, "full_name": barber.full_name, "phone": barber.phone}


@router.put("/owner/barbers/{barber_id}/commission-rate")
def owner_update_barber_commission_rate(
    barber_id: int,
    data: BarberCommissionRateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede configurar comisiones")
    barber = db.query(User).filter(
        User.id == barber_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    previous_rate = barber.commission_rate_basis_points
    barber.commission_rate_basis_points = data.rate_basis_points
    _audit(db, owner, "barber.commission_rate_changed", "user", barber.id, owner.barbershop_id,
           {"previous_rate_basis_points": previous_rate,
            "rate_basis_points": data.rate_basis_points})
    db.commit()
    return {"success": True, "barber_id": barber.id,
            "rate_basis_points": barber.commission_rate_basis_points}


def _commission_item(row: BarberCommission, barber: User) -> dict:
    return {
        "id": row.id,
        "barber_id": row.barber_id,
        "barber_name": barber.full_name,
        "payment_id": row.payment_id,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "rate_basis_points": row.rate_basis_points,
        "status": row.status,
        "accrued_at": row.accrued_at.isoformat(),
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "payment_method": row.payment_method,
        "payment_reference": row.payment_reference,
    }


@router.get("/owner/barber-commissions")
def owner_list_barber_commissions(
    status: Optional[str] = None,
    barber_id: Optional[int] = None,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar las comisiones")
    if status is not None and status not in {"pending", "paid"}:
        raise HTTPException(status_code=422, detail="Estado de comisión no válido")
    base = db.query(BarberCommission).filter(
        BarberCommission.barbershop_id == owner.barbershop_id,
        BarberCommission.is_deleted == False,
    )
    pending_totals = _commission_totals_for_scope(db, owner.barbershop_id, "pending")
    paid_totals = _commission_totals_for_scope(db, owner.barbershop_id, "paid")
    query = base
    if status:
        query = query.filter(BarberCommission.status == status)
    if barber_id:
        query = query.filter(BarberCommission.barber_id == barber_id)
    rows = query.order_by(BarberCommission.accrued_at.desc(), BarberCommission.id.desc()).limit(200).all()
    barber_ids = {row.barber_id for row in rows}
    barbers = {item.id: item for item in db.query(User).filter(User.id.in_(barber_ids)).all()} if barber_ids else {}
    return {
        "pending_totals_by_currency": pending_totals,
        "paid_totals_by_currency": paid_totals,
        "items": [_commission_item(row, barbers[row.barber_id]) for row in rows if row.barber_id in barbers],
    }


@router.get("/barber/commissions")
def barber_list_own_commissions(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    barber = _get_current_user(db, authorization)
    if barber.role != "barber" or not barber.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo un barbero puede consultar sus comisiones")
    rows = db.query(BarberCommission).filter(
        BarberCommission.barbershop_id == barber.barbershop_id,
        BarberCommission.barber_id == barber.id,
        BarberCommission.is_deleted == False,
    ).order_by(BarberCommission.accrued_at.desc(), BarberCommission.id.desc()).limit(200).all()
    return {
        "pending_totals_by_currency": _commission_totals_for_scope(
            db, barber.barbershop_id, "pending", barber_id=barber.id,
        ),
        "paid_totals_by_currency": _commission_totals_for_scope(
            db, barber.barbershop_id, "paid", barber_id=barber.id,
        ),
        "items": [_commission_item(row, barber) for row in rows],
    }


def _commission_totals_for_scope(
    db: Session, barbershop_id: int, status: str, barber_id: Optional[int] = None,
) -> list[dict]:
    query = db.query(
        BarberCommission.currency,
        func.coalesce(func.sum(BarberCommission.amount_cents), 0),
    ).filter(
        BarberCommission.barbershop_id == barbershop_id,
        BarberCommission.status == status,
        BarberCommission.is_deleted == False,
    )
    if barber_id is not None:
        query = query.filter(BarberCommission.barber_id == barber_id)
    return [{"currency": currency, "amount_cents": int(amount)}
            for currency, amount in query.group_by(BarberCommission.currency).order_by(BarberCommission.currency).all()]


@router.post("/owner/barber-commissions/{commission_id}/pay")
def owner_pay_barber_commission(
    commission_id: int,
    data: BarberCommissionPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede liquidar comisiones")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    if data.payment_method == "cash":
        business_date = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
        if _cash_register_closed_for_user(
            db, owner, shop.id, datetime.combine(business_date, time.min),
        ):
            raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se puede registrar un pago en efectivo")
    commission = db.query(BarberCommission).filter(
        BarberCommission.id == commission_id,
        BarberCommission.barbershop_id == owner.barbershop_id,
        BarberCommission.is_deleted == False,
    ).with_for_update().first()
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if commission.status != "pending":
        raise HTTPException(status_code=409, detail="La comisión ya fue liquidada")
    commission.status = "paid"
    commission.paid_at = utc_now_naive()
    commission.paid_by_user_id = owner.id
    commission.payment_method = data.payment_method
    commission.payment_reference = data.payment_reference.strip() if data.payment_reference else None
    _audit(db, owner, "barber.commission_paid", "barber_commission", commission.id,
           owner.barbershop_id, {"barber_id": commission.barber_id,
                                 "amount_cents": commission.amount_cents,
                                 "currency": commission.currency,
                                 "payment_method": commission.payment_method})
    db.commit()
    return {"success": True, "commission_id": commission.id, "status": commission.status,
            "paid_at": commission.paid_at.isoformat()}


@router.get("/owner/clients")
def owner_list_clients(
    limit: int = 50,
    offset: int = 0,
    search: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar sus clientes")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginación fuera de rango")
    client_query = db.query(User).filter(
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    )
    search_term = search.strip()
    if search_term:
        pattern = f"%{search_term}%"
        client_query = client_query.filter(or_(
            User.first_name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone.ilike(pattern),
            func.concat(User.first_name, " ", User.last_name).ilike(pattern),
        ))
    total = client_query.count()
    clients = client_query.order_by(User.id.desc()).offset(offset).limit(limit).all()
    client_ids = [client.id for client in clients]
    appointments = {}
    payments = {}
    if client_ids:
        appointment_rows = db.query(
            Appointment.client_id,
            func.count(Appointment.id),
            func.sum(case((Appointment.status == "completed", 1), else_=0)),
            func.max(case((Appointment.status == "completed", Appointment.scheduled_time), else_=None)),
        ).filter(
            Appointment.barbershop_id == owner.barbershop_id,
            Appointment.client_id.in_(client_ids),
            Appointment.is_deleted == False,
        ).group_by(Appointment.client_id).all()
        appointments = {row[0]: {"count": int(row[1] or 0), "completed": int(row[2] or 0), "last_visit": row[3]}
                        for row in appointment_rows}
        payment_rows = db.query(
            Appointment.client_id,
            func.sum(Payment.amount_cents + Payment.tip_cents),
        ).join(Payment, Payment.appointment_id == Appointment.id).filter(
            Appointment.barbershop_id == owner.barbershop_id,
            Appointment.client_id.in_(client_ids),
            Appointment.is_deleted == False,
            Payment.is_deleted == False,
        ).group_by(Appointment.client_id).all()
        payments = {row[0]: int(row[1] or 0) for row in payment_rows}
    return {"items": [{
        "id": client.id, "full_name": client.full_name, "first_name": client.first_name,
        "last_name": client.last_name, "phone": client.phone, "is_active": client.is_active,
        "created_at": client.created_at.isoformat(),
        "appointment_count": appointments.get(client.id, {}).get("count", 0),
        "completed_count": appointments.get(client.id, {}).get("completed", 0),
        "last_visit": appointments.get(client.id, {}).get("last_visit"),
        "total_paid_cents": payments.get(client.id, 0),
    } for client in clients], "limit": limit, "offset": offset, "total": total}


@router.get("/owner/clients/{client_id}/appointments")
def owner_list_client_appointment_history(
    client_id: int,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede consultar el historial")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginación fuera de rango")
    client = db.query(User).filter(
        User.id == client_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    appointment_query = db.query(Appointment).filter(
        Appointment.barbershop_id == owner.barbershop_id,
        Appointment.client_id == client.id,
        Appointment.is_deleted == False,
    )
    total = appointment_query.count()
    appointments = appointment_query.order_by(
        Appointment.scheduled_time.desc(), Appointment.id.desc(),
    ).offset(offset).limit(limit).all()
    appointment_ids = [appointment.id for appointment in appointments]
    payments = db.query(Payment).filter(
        Payment.barbershop_id == owner.barbershop_id,
        Payment.appointment_id.in_(appointment_ids),
        Payment.is_deleted == False,
    ).all() if appointment_ids else []
    payments_by_appointment = {payment.appointment_id: payment for payment in payments}
    barber_ids = {appointment.barber_id for appointment in appointments}
    barbers = db.query(User).filter(
        User.id.in_(barber_ids),
        User.barbershop_id == owner.barbershop_id,
        User.role == "barber",
    ).all() if barber_ids else []
    barber_names = {barber.id: barber.full_name for barber in barbers}

    def utc_iso(value: Optional[datetime]) -> Optional[str]:
        return f"{value.isoformat()}Z" if value else None

    items = []
    for appointment in appointments:
        payment = payments_by_appointment.get(appointment.id)
        actual_duration = None
        if appointment.actual_start_time and appointment.actual_end_time:
            actual_duration = max(
                0,
                int((appointment.actual_end_time - appointment.actual_start_time).total_seconds() / 60),
            )
        items.append({
            "id": appointment.id,
            "scheduled_time": utc_iso(appointment.scheduled_time),
            "status": appointment.status,
            "service_type": appointment.service_type,
            "estimated_duration": appointment.estimated_duration,
            "actual_duration": actual_duration,
            "service_price_cents": appointment.service_price,
            "barber_name": barber_names.get(appointment.barber_id),
            "payment": {
                "amount_cents": payment.amount_cents,
                "tip_cents": payment.tip_cents,
                "currency": payment.currency,
                "method": payment.method,
                "received_at": utc_iso(payment.received_at),
            } if payment else None,
        })
    return {"items": items, "limit": limit, "offset": offset, "total": total}


@router.post("/owner/clients", status_code=201)
def owner_create_client(
    data: OwnerClientCreateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar sus clientes")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=403, detail="Barbería inactiva")
    subscription = _require_active_subscription(db, shop, lock=True)
    phone = _normalize_phone(data.phone)
    existing = db.query(User).filter(
        User.phone == phone,
        User.barbershop_id == shop.id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un cliente con ese teléfono en esta barbería",
        )
    if subscription.max_clients is not None:
        client_count = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.role == "client",
            User.is_deleted == False,
        ).count()
        if client_count >= subscription.max_clients:
            raise HTTPException(status_code=402, detail="La barbería alcanzó el límite de clientes de su plan")

    client = User(
        email=f"client-{shop.id}-{secrets.token_hex(16)}@client.invalid",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        first_name=data.first_name,
        last_name=data.last_name,
        phone=phone,
        role="client",
        is_active=True,
        is_verified=True,
        barbershop_id=shop.id,
    )
    db.add(client)
    try:
        db.flush()
        _audit(db, owner, "client.created", "user", client.id, shop.id,
               {"phone_last4": phone[-4:], "source": "owner_manual"})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo registrar el cliente") from exc
    return {
        "id": client.id,
        "full_name": client.full_name,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "phone": client.phone,
        "is_active": client.is_active,
    }


@router.put("/owner/clients/{client_id}")
def owner_update_client(
    client_id: int,
    data: OwnerClientUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar sus clientes")
    shop = db.query(Barbershop).filter(
        Barbershop.id == owner.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    phone = _normalize_phone(data.phone or "") or None
    client = db.query(User).filter(
        User.id == client_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if phone and db.query(User.id).filter(
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.phone == phone,
        User.id != client.id,
        User.is_deleted == False,
    ).with_for_update().first():
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese teléfono en esta barbería")
    client.first_name = data.first_name
    client.last_name = data.last_name
    client.phone = phone
    _audit(db, owner, "client.profile_updated", "user", client.id, owner.barbershop_id,
           {"updated_fields": ["first_name", "last_name", "phone"]})
    db.commit()
    return {"id": client.id, "full_name": client.full_name, "phone": client.phone}


@router.put("/owner/clients/{client_id}/status")
def owner_update_client_status(
    client_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    owner = _get_current_user(db, authorization)
    if owner.role != "barbershop_owner" or not owner.barbershop_id:
        raise HTTPException(status_code=403, detail="Solo el propietario puede gestionar sus clientes")
    client = db.query(User).filter(
        User.id == client_id,
        User.barbershop_id == owner.barbershop_id,
        User.role == "client",
        User.is_deleted == False,
    ).with_for_update().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    previous = client.is_active
    client.is_active = data.is_active
    _audit(db, owner, "client.status_changed", "user", client.id, owner.barbershop_id,
           {"previous": previous, "is_active": data.is_active})
    db.commit()
    return {"success": True, "id": client.id, "is_active": client.is_active}


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

    assignment = db.query(Appointment.barber_id).filter(
        Appointment.id == appointment_id,
        Appointment.barbershop_id == user.barbershop_id,
        Appointment.is_deleted == False,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    assigned_barber = db.query(User).filter(
        User.id == assignment.barber_id,
        User.barbershop_id == user.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not assigned_barber:
        raise HTTPException(status_code=409, detail="El barbero asignado ya no está disponible")

    shop = None
    if status == "in_progress":
        # Cash close locks the shop before reading appointments. Acquire that
        # same mutex before locking this appointment to keep a consistent order.
        shop = db.query(Barbershop).filter(
            Barbershop.id == user.barbershop_id,
            Barbershop.is_deleted == False,
        ).with_for_update().first()
        if not shop:
            raise HTTPException(status_code=404, detail="Barbería no encontrada")

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.barbershop_id == user.barbershop_id,
            Appointment.is_deleted == False,
        )
        .with_for_update()
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.barber_id != assigned_barber.id:
        raise HTTPException(status_code=409, detail="La asignación de la cita cambió; vuelve a consultar")

    if user.role == "barber" and appointment.barber_id != user.id:
        raise HTTPException(status_code=403, detail="Solo puedes actualizar tus propias citas")

    allowed_transitions = {
        "pending": {"confirmed", "in_progress", "cancelled", "no_show"},
        "confirmed": {"in_progress", "cancelled", "no_show"},
        "in_progress": {"completed"},
        "completed": set(),
        "cancelled": set(),
        "no_show": set(),
    }
    if status not in allowed_transitions.get(appointment.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"No se puede cambiar una cita de {appointment.status} a {status}",
        )

    if status == "no_show":
        no_show_after = appointment.scheduled_time + timedelta(minutes=appointment.estimated_duration)
        if utc_now_naive() < no_show_after:
            raise HTTPException(status_code=409, detail="Una cita solo puede marcarse como no presentado después de su horario")

    if status == "completed":
        raise HTTPException(status_code=409, detail="Registra el pago para finalizar el servicio")

    now = utc_now_naive()
    if status == "in_progress":
        if abs((now - appointment.scheduled_time).total_seconds()) > 15 * 60:
            raise HTTPException(status_code=409, detail="Solo se puede iniciar el servicio dentro de los 15 minutos de la hora programada")
        if not assigned_barber.is_active:
            raise HTTPException(status_code=409, detail="El barbero asignado ya no está activo en esta barbería")
        business_day = _utc_aware(now).astimezone(_get_timezone(shop)).date()
        if _cash_register_closed_for_user(
            db, assigned_barber, shop.id, datetime.combine(business_day, time.min),
        ):
            raise HTTPException(status_code=409, detail="La caja de hoy está cerrada; no se pueden iniciar servicios nuevos")
        other_active_appointment = db.query(Appointment.id).filter(
            Appointment.barbershop_id == appointment.barbershop_id,
            Appointment.barber_id == appointment.barber_id,
            Appointment.status == "in_progress",
            Appointment.id != appointment.id,
            Appointment.is_deleted == False,
        ).with_for_update().first()
        if other_active_appointment:
            raise HTTPException(status_code=409, detail="El barbero ya tiene otro servicio en curso")

    previous_status = appointment.status
    appointment.status = status
    if status == "cancelled":
        appointment.cancelled_by = user.id
        appointment.cancellation_reason = data.reason
    if status == "in_progress" and not appointment.actual_start_time:
        appointment.actual_start_time = now
    if status == "completed" and not appointment.actual_end_time:
        appointment.actual_end_time = now
    if status == "cancelled":
        db.execute(
            update(BarberAvailability)
            .where(
                BarberAvailability.barbershop_id == appointment.barbershop_id,
                BarberAvailability.barber_id == appointment.barber_id,
                BarberAvailability.slot_start == appointment.scheduled_time,
                BarberAvailability.is_booked == True,
                BarberAvailability.is_deleted == False,
            )
            .values(is_booked=False)
        )

    if status in {"confirmed", "in_progress", "cancelled", "no_show"}:
        titles = {
            "confirmed": "Cita confirmada",
            "in_progress": "Servicio iniciado",
            "cancelled": "Cita cancelada",
            "no_show": "Cliente no se presentó",
        }
        _notify_appointment_staff(
            db, appointment, f"appointment_{status}", titles[status],
            f"{appointment.service_type} · {status}", exclude_user_id=user.id,
        )
    if status == "confirmed":
        _queue_appointment_email(db, appointment, "confirmation")
        shop = db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        if shop and appointment.client and appointment.client.phone:
            local_time = _utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop))
            _queue_appointment_whatsapp(
                db, appointment, appointment.client.phone,
                f"Tu cita en {shop.name} fue confirmada para "
                f"{local_time.strftime('%d/%m/%Y %H:%M')} ({appointment.service_type}).",
                "confirmation:client:status",
            )
    _audit(db, user, f"appointment.{status}", "appointment", appointment.id,
           appointment.barbershop_id, {"previous_status": previous_status})
    if status == "cancelled":
        _queue_appointment_email(db, appointment, "cancellation", appointment.cancellation_reason)
        shop = db.query(Barbershop).filter(Barbershop.id == appointment.barbershop_id).first()
        if appointment.client and appointment.client.phone and shop:
            _queue_appointment_whatsapp(
                db, appointment, appointment.client.phone,
                f"La cita en {shop.name} para "
                f"{_utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).strftime('%d/%m/%Y %H:%M')} fue cancelada.",
                "cancellation:client",
            )
    if status in {"cancelled", "no_show"}:
        try:
            from app.services.performance_service import PerformanceService

            shop = db.query(Barbershop).filter(Barbershop.id == appointment.barbershop_id).first()
            if not shop:
                raise ValueError("Barbershop not found while updating appointment performance")
            business_day = _business_date_for_appointment(appointment, shop)
            PerformanceService.calculate_daily_performance(
                db=db, barbershop_id=appointment.barbershop_id,
                barber_id=appointment.barber_id, target_date=business_day, commit=False,
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Appointment status consequences could not be persisted",
                             extra={"appointment_id": appointment.id, "status": status})
            raise HTTPException(
                status_code=503,
                detail="No se pudo guardar el cambio y actualizar el rendimiento; vuelve a consultar la cita",
            ) from exc
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El cambio de estado entró en conflicto; verifica la cita") from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Appointment status transaction failed",
                         extra={"appointment_id": appointment.id, "status": status})
        raise HTTPException(
            status_code=503,
            detail="No se pudo guardar el cambio de estado; vuelve a consultar la cita",
        ) from exc
    return {
        "success": True,
        "appointment_id": appointment.id,
        "status": appointment.status,
    }


@router.post("/barber/appointments/{appointment_id}/payment", status_code=201)
def barber_record_appointment_payment(
    appointment_id: int,
    data: AppointmentPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Record one full appointment payment and complete the service atomically."""
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner", "super_admin"] or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado")

    assignment = db.query(Appointment.barber_id).filter(
        Appointment.id == appointment_id,
        Appointment.barbershop_id == user.barbershop_id,
        Appointment.is_deleted == False,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if user.role == "barber" and assignment.barber_id != user.id:
        raise HTTPException(status_code=403, detail="Solo puedes cobrar tus propias citas")
    barber = db.query(User).filter(
        User.id == assignment.barber_id,
        User.barbershop_id == user.barbershop_id,
        User.role == "barber",
        User.is_deleted == False,
    ).with_for_update().first()
    if not barber:
        raise HTTPException(status_code=409, detail="El barbero asignado ya no está disponible")

    # Take the shared cash-close lock before the appointment row. Cash close
    # takes these locks in the same order, avoiding a shop/appointment cycle.
    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop or not shop.currency:
        raise HTTPException(status_code=409, detail="Configura la moneda de la barbería antes de cobrar")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.barbershop_id == user.barbershop_id,
        Appointment.is_deleted == False,
    ).with_for_update().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appointment.barber_id != barber.id:
        raise HTTPException(status_code=409, detail="La asignación de la cita cambió; vuelve a consultar")
    if user.role == "barber" and appointment.barber_id != user.id:
        raise HTTPException(status_code=403, detail="Solo puedes cobrar tus propias citas")
    if appointment.status != "in_progress":
        raise HTTPException(status_code=409, detail="Solo se puede cobrar un servicio en curso")
    now = utc_now_naive()
    if (
        not appointment.actual_start_time
        or now - appointment.actual_start_time < timedelta(minutes=5)
    ):
        raise HTTPException(status_code=409, detail="El servicio debe durar al menos 5 minutos antes de cobrar")
    if db.query(Payment.id).filter(Payment.appointment_id == appointment.id, Payment.is_deleted == False).first():
        raise HTTPException(status_code=409, detail="Esta cita ya tiene un pago registrado")

    # The shop row is the shared mutex used above and by daily cash close.
    business_day = _utc_aware(now).astimezone(_get_timezone(shop)).date()
    close_key = datetime.combine(business_day, time.min)
    if _cash_register_closed_for_user(db, user, shop.id, close_key):
        raise HTTPException(status_code=409, detail="La caja de hoy ya fue cerrada; no se pueden registrar más cobros")
    amount_cents = int(appointment.service_price or 0)
    if amount_cents <= 0:
        raise HTTPException(status_code=409, detail="El servicio no tiene un precio válido")

    payment = Payment(
        barbershop_id=appointment.barbershop_id,
        appointment_id=appointment.id,
        barber_id=appointment.barber_id,
        amount_cents=amount_cents,
        tip_cents=data.tip_cents,
        method=data.method,
        currency=shop.currency,
        received_at=now,
        recorded_by_user_id=user.id,
    )
    appointment.status = "completed"
    appointment.actual_end_time = now
    db.add(payment)
    db.flush()
    commission = None
    if barber and barber.commission_rate_basis_points > 0:
        rate = barber.commission_rate_basis_points
        commission_amount = (amount_cents * rate + 5000) // 10000
        if commission_amount > 0:
            commission = BarberCommission(
                barbershop_id=shop.id,
                barber_id=barber.id,
                payment_id=payment.id,
                amount_cents=commission_amount,
                currency=shop.currency,
                rate_basis_points=rate,
                status="pending",
                accrued_at=now,
            )
            db.add(commission)
            db.flush()
            _audit(db, user, "barber.commission_accrued", "barber_commission", commission.id,
                   shop.id, {"barber_id": barber.id, "payment_id": payment.id,
                             "amount_cents": commission_amount, "currency": shop.currency,
                             "rate_basis_points": rate})
    _audit(db, user, "appointment.payment_recorded", "payment", payment.id,
           appointment.barbershop_id, {"appointment_id": appointment.id,
                                       "amount_cents": payment.amount_cents,
                                       "tip_cents": payment.tip_cents,
                                       "method": payment.method})
    _notify_appointment_staff(
        db, appointment, "appointment_paid", "Servicio cobrado",
        f"{appointment.service_type} · {(payment.amount_cents + payment.tip_cents) / 100:.2f} {payment.currency}",
        exclude_user_id=user.id,
    )
    _queue_appointment_email(db, appointment, "completion")
    if appointment.client and appointment.client.phone:
        _queue_appointment_whatsapp(
            db, appointment, appointment.client.phone,
            f"Gracias por visitar {shop.name}. Registramos tu pago de "
            f"{(payment.amount_cents + payment.tip_cents) / 100:.2f} {payment.currency} por {appointment.service_type}.",
            "completion:client",
        )
    try:
        from app.services.performance_service import PerformanceService
        from app.services.achievement_service import AchievementService

        PerformanceService.calculate_daily_performance(
            db=db,
            barbershop_id=appointment.barbershop_id,
            barber_id=appointment.barber_id,
            target_date=_business_date_for_appointment(appointment, shop),
            commit=False,
        )
        AchievementService.check_and_award_achievements(
            db=db,
            user_id=appointment.barber_id,
            barbershop_id=appointment.barbershop_id,
            trigger_type="appointment_completed",
            context_data={
                "appointment_id": appointment.id,
                "business_date": _business_date_for_appointment(appointment, shop).isoformat(),
            },
            commit=False,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Checkout transaction conflicted", extra={"appointment_id": appointment_id})
        raise HTTPException(status_code=409, detail="El cobro entró en conflicto con otra operación; verifica el estado de la cita") from exc
    except Exception:
        db.rollback()
        logger.exception("Checkout consequences could not be persisted", extra={"appointment_id": appointment_id})
        raise HTTPException(status_code=503, detail="No se pudo registrar el cobro y sus resultados; vuelve a consultar la cita antes de reintentar")
    return {
        "success": True,
        "appointment_id": appointment.id,
        "status": appointment.status,
        "payment_id": payment.id,
        "amount_cents": payment.amount_cents,
        "tip_cents": payment.tip_cents,
        "total_cents": payment.amount_cents + payment.tip_cents,
        "currency": payment.currency,
        "method": payment.method,
        "barber_commission_id": commission.id if commission else None,
        "barber_commission_cents": commission.amount_cents if commission else 0,
    }


@router.get("/barber/cash/today")
def barber_cash_today(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner", "super_admin"] or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop or shop.is_deleted:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    start, end, _, _ = _local_day_bounds(utc_now_naive(), shop)
    query = db.query(Payment).filter(
        Payment.barbershop_id == shop.id,
        Payment.received_at >= start,
        Payment.received_at < end,
        Payment.is_deleted == False,
    )
    if user.role == "barber":
        query = query.filter(Payment.barber_id == user.id)
    payments = query.all()
    by_method = {}
    for payment in payments:
        by_method[payment.method] = by_method.get(payment.method, 0) + payment.amount_cents + payment.tip_cents
    cash_commissions_paid = 0
    if user.role in {"barbershop_owner", "super_admin"}:
        cash_commissions_paid = db.query(func.coalesce(func.sum(BarberCommission.amount_cents), 0)).filter(
            BarberCommission.barbershop_id == shop.id,
            BarberCommission.status == "paid",
            BarberCommission.payment_method == "cash",
            BarberCommission.paid_at >= start,
            BarberCommission.paid_at < end,
            BarberCommission.is_deleted == False,
        ).scalar() or 0
    expected_cash = by_method.get("cash", 0) - int(cash_commissions_paid)
    close_query = db.query(CashRegisterClose).filter(
        CashRegisterClose.barbershop_id == shop.id,
        CashRegisterClose.business_date == datetime.combine(_utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date(), time.min),
        CashRegisterClose.is_deleted == False,
    )
    if user.role == "barber":
        close_query = close_query.join(
            User, User.id == CashRegisterClose.closed_by_user_id,
        ).filter(or_(
            CashRegisterClose.closed_by_user_id == user.id,
            (User.role == "barbershop_owner") & (User.barbershop_id == shop.id),
        ))
    else:
        close_query = close_query.filter(CashRegisterClose.closed_by_user_id == user.id)
    close = close_query.first()
    return {
        "business_date": _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date().isoformat(),
        "currency": shop.currency,
        "payment_count": len(payments),
        "total_cents": sum(by_method.values()),
        "by_method": by_method,
        "cash_commissions_paid_cents": int(cash_commissions_paid),
        "expected_cash_cents": expected_cash,
        "closed": bool(close),
        "close": {
            "declared_cash_cents": close.declared_cash_cents,
            "difference_cents": close.difference_cents,
            "closed_at": close.closed_at.isoformat(),
        } if close else None,
    }


@router.post("/barber/cash/close", status_code=201)
def barber_close_cash_register(
    data: CashRegisterCloseRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role not in ["barber", "barbershop_owner", "super_admin"] or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop or shop.is_deleted:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    try:
        business_date = datetime.strptime(data.business_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Fecha de cierre no válida") from exc
    local_today = _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    if business_date > local_today:
        raise HTTPException(status_code=422, detail="No se puede cerrar una fecha futura")
    date_key = datetime.combine(business_date, time.min)
    if user.role == "barber":
        owner_close = db.query(CashRegisterClose.id).join(
            User, User.id == CashRegisterClose.closed_by_user_id,
        ).filter(
            CashRegisterClose.barbershop_id == shop.id,
            CashRegisterClose.business_date == date_key,
            CashRegisterClose.is_deleted == False,
            User.role == "barbershop_owner",
            User.barbershop_id == shop.id,
        ).with_for_update().first()
        if owner_close:
            raise HTTPException(status_code=409, detail="La caja del negocio ya fue cerrada por un propietario")
    existing = db.query(CashRegisterClose.id).filter(
        CashRegisterClose.barbershop_id == shop.id,
        CashRegisterClose.closed_by_user_id == user.id,
        CashRegisterClose.business_date == date_key,
        CashRegisterClose.is_deleted == False,
    ).with_for_update().first()
    if existing:
        raise HTTPException(status_code=409, detail="La caja de esta fecha ya fue cerrada")
    start = local_day_start_utc_naive(business_date, _get_timezone(shop))
    end = local_day_start_utc_naive(business_date + timedelta(days=1), _get_timezone(shop))
    open_services = db.query(Appointment.id).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.status == "in_progress",
        Appointment.scheduled_time >= start,
        Appointment.scheduled_time < end,
        Appointment.is_deleted == False,
    ).with_for_update()
    remaining_appointments = db.query(Appointment.id).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.status.in_({"pending", "confirmed"}),
        Appointment.scheduled_time >= start,
        Appointment.scheduled_time < end,
        Appointment.is_deleted == False,
    ).with_for_update()
    if user.role == "barber":
        open_services = open_services.filter(Appointment.barber_id == user.id)
        remaining_appointments = remaining_appointments.filter(Appointment.barber_id == user.id)
    if open_services.first():
        raise HTTPException(
            status_code=409,
            detail="Termina y cobra los servicios en curso antes de cerrar la caja",
        )
    if remaining_appointments.first():
        raise HTTPException(
            status_code=409,
            detail="Resuelve las citas del día antes de cerrar la caja",
        )
    payment_query = db.query(Payment).filter(
        Payment.barbershop_id == shop.id,
        Payment.method == "cash",
        Payment.received_at >= start,
        Payment.received_at < end,
        Payment.is_deleted == False,
    ).with_for_update()
    if user.role == "barber":
        payment_query = payment_query.filter(Payment.barber_id == user.id)
    cash_payments = payment_query.all()
    cash_commissions_paid = 0
    if user.role in {"barbershop_owner", "super_admin"}:
        paid_cash_commissions = db.query(BarberCommission.amount_cents).filter(
            BarberCommission.barbershop_id == shop.id,
            BarberCommission.status == "paid",
            BarberCommission.payment_method == "cash",
            BarberCommission.paid_at >= start,
            BarberCommission.paid_at < end,
            BarberCommission.is_deleted == False,
        ).with_for_update().all()
        cash_commissions_paid = sum(int(amount) for (amount,) in paid_cash_commissions)
    expected = sum(item.amount_cents + item.tip_cents for item in cash_payments) - int(cash_commissions_paid)
    close = CashRegisterClose(
        barbershop_id=shop.id,
        closed_by_user_id=user.id,
        business_date=date_key,
        expected_cash_cents=expected,
        declared_cash_cents=data.declared_cash_cents,
        difference_cents=data.declared_cash_cents - expected,
        payment_count=len(cash_payments),
        notes=data.notes,
        closed_at=utc_now_naive(),
    )
    db.add(close)
    try:
        db.flush()
        _audit(db, user, "cash.closed", "cash_register_close", close.id, shop.id,
               {"business_date": data.business_date, "expected_cents": expected,
                "cash_commissions_paid_cents": int(cash_commissions_paid),
                "declared_cents": data.declared_cash_cents,
                "difference_cents": data.declared_cash_cents - expected})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="La caja de esta fecha ya fue cerrada") from exc
    return {
        "success": True,
        "business_date": data.business_date,
        "currency": shop.currency,
        "expected_cash_cents": expected,
        "declared_cash_cents": close.declared_cash_cents,
        "difference_cents": close.difference_cents,
        "payment_count": close.payment_count,
        "cash_commissions_paid_cents": int(cash_commissions_paid),
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
    shop = db.query(Barbershop).filter(
        Barbershop.id == shop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

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

    now = utc_now_naive()
    day_start, day_end, yesterday_start, week_start = _local_day_bounds(now, shop)
    week_query = db.query(Appointment).filter(
            Appointment.barbershop_id == shop_id,
            Appointment.scheduled_time >= week_start,
            Appointment.scheduled_time < day_end,
            Appointment.is_deleted == False,
        )
    if user.role == "barber":
        week_query = week_query.filter(Appointment.barber_id == user.id)
    appointments_week = week_query.all()

    completed_query = db.query(Appointment).filter(
            Appointment.barbershop_id == shop_id,
            Appointment.status == "completed",
            Appointment.is_deleted == False,
        )
    if user.role == "barber":
        completed_query = completed_query.filter(Appointment.barber_id == user.id)
    completed_all_time = completed_query.count()

    today_query = db.query(Appointment).filter(
            Appointment.barbershop_id == shop_id,
            Appointment.scheduled_time >= day_start,
            Appointment.scheduled_time < day_end,
            Appointment.is_deleted == False,
        )
    if user.role == "barber":
        today_query = today_query.filter(Appointment.barber_id == user.id)
    appointments_today = today_query.order_by(Appointment.scheduled_time.asc()).all()

    active_query = db.query(Appointment).filter(
        Appointment.barbershop_id == shop_id,
        Appointment.status == "in_progress",
        Appointment.is_deleted == False,
    )
    if user.role == "barber":
        active_query = active_query.filter(Appointment.barber_id == user.id)
    active_appointment = active_query.order_by(Appointment.actual_start_time.asc()).first()

    completed_count = len([a for a in appointments_today if a.status == "completed"])
    in_progress_count = len([a for a in appointments_today if a.status == "in_progress"])
    pending_count = len([a for a in appointments_today if a.status in ["pending", "confirmed"]])
    total_count = len(appointments_today)
    revenue_query = db.query(Payment).filter(
        Payment.barbershop_id == shop_id,
        Payment.received_at >= day_start,
        Payment.received_at < day_end,
        Payment.is_deleted == False,
    )
    if user.role == "barber":
        revenue_query = revenue_query.filter(Payment.barber_id == user.id)
    revenue_cents = sum(item.amount_cents + item.tip_cents for item in revenue_query.all())
    from app.services.performance_service import PerformanceService

    efficiency_percent = round(PerformanceService.time_efficiency([
        appointment for appointment in appointments_today if appointment.status == "completed"
    ]))

    yesterday_end = day_start
    yesterday_query = db.query(Appointment).filter(
            Appointment.barbershop_id == shop_id,
            Appointment.scheduled_time >= yesterday_start,
            Appointment.scheduled_time < yesterday_end,
            Appointment.is_deleted == False,
        )
    if user.role == "barber":
        yesterday_query = yesterday_query.filter(Appointment.barber_id == user.id)
    appointments_yesterday = yesterday_query.all()
    completed_yesterday = len([a for a in appointments_yesterday if a.status == "completed"])
    revenue_yesterday_query = db.query(Payment).filter(
        Payment.barbershop_id == shop_id,
        Payment.received_at >= yesterday_start,
        Payment.received_at < yesterday_end,
        Payment.is_deleted == False,
    )
    if user.role == "barber":
        revenue_yesterday_query = revenue_yesterday_query.filter(Payment.barber_id == user.id)
    revenue_yesterday = sum(item.amount_cents + item.tip_cents for item in revenue_yesterday_query.all())
    efficiency_yesterday = round(PerformanceService.time_efficiency([
        appointment for appointment in appointments_yesterday if appointment.status == "completed"
    ]))

    completed_delta = completed_count - completed_yesterday
    revenue_delta = revenue_cents - revenue_yesterday
    efficiency_delta = efficiency_percent - efficiency_yesterday

    next_appointment_query = db.query(Appointment).filter(
        Appointment.barbershop_id == shop_id,
        Appointment.scheduled_time >= now,
        Appointment.status.in_(["pending", "confirmed"]),
        Appointment.is_deleted == False,
    )
    if user.role == "barber":
        next_appointment_query = next_appointment_query.filter(Appointment.barber_id == user.id)
    next_appointment = next_appointment_query.order_by(Appointment.scheduled_time.asc()).first()

    weekday_labels = ["L", "M", "X", "J", "V", "S", "D"]
    week_counts_by_day = {i: 0 for i in range(7)}
    for ap in appointments_week:
        if ap.status != "completed":
            continue
        local_day = _utc_aware(ap.scheduled_time).astimezone(_get_timezone(shop)).weekday()
        week_counts_by_day[local_day] += 1

    max_count = max(week_counts_by_day.values()) if week_counts_by_day else 0
    weekly_counts = [
        {
            "label": weekday_labels[day_idx],
            "count": week_counts_by_day[day_idx],
            "height_percent": int((week_counts_by_day[day_idx] / max_count) * 100) if max_count else 0,
        }
        for day_idx in range(7)
    ]

    achievement_items = []
    earned_ids = set()
    earned_points = 0
    unlocked_count = 0
    if user.role == "barber":
        earned = db.query(UserAchievement).filter(
            UserAchievement.user_id == user.id,
            UserAchievement.barbershop_id == shop_id,
            UserAchievement.is_deleted == False,
        ).all()
        earned_ids = {item.achievement_id for item in earned}
        unlocked_count = len(earned_ids)
        active_achievements = db.query(Achievement).filter(
            Achievement.is_active == True,
            Achievement.is_deleted == False,
        ).order_by(Achievement.requirement_value.asc()).all()
        achievement_defs = {item.id: item for item in active_achievements}
        earned_points = sum(achievement_defs[item_id].points or 0 for item_id in earned_ids if item_id in achievement_defs)
        daily_completed = {}
        for item in completed_query.all():
            day = _utc_aware(item.scheduled_time).astimezone(_get_timezone(shop)).date()
            daily_completed[day] = daily_completed.get(day, 0) + 1
        for achievement in active_achievements:
            if achievement.requirement_type in {"appointments", "total_appointments"}:
                current = completed_all_time
            elif achievement.requirement_type == "daily_appointments":
                current = max(daily_completed.values(), default=0)
            elif achievement.requirement_type == "streak":
                current = db.query(func.max(BarberPerformance.current_streak)).filter(
                    BarberPerformance.barbershop_id == shop_id,
                    BarberPerformance.barber_id == user.id,
                ).scalar() or 0
            else:
                current = 0
            achievement_items.append({
                "title": achievement.name,
                "description": achievement.description or "",
                "target": achievement.requirement_value,
                "current": current,
                "points": achievement.points or 0,
                "icon": achievement.icon,
                "earned": achievement.id in earned_ids,
            })
    achievements = {
        "unlocked": unlocked_count,
        "points": earned_points,
        "progress_percent": int((unlocked_count / len(achievement_items)) * 100) if achievement_items else 0,
        "items": achievement_items,
    }

    return {
        "business_date": _utc_aware(now).astimezone(_get_timezone(shop)).date().isoformat(),
        "summary": {
            "total": total_count,
            "completed": completed_count,
            "pending": pending_count,
            "in_progress": in_progress_count,
            "cancelled": sum(1 for appointment in appointments_today if appointment.status == "cancelled"),
            "no_show": sum(1 for appointment in appointments_today if appointment.status == "no_show"),
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
                "scheduled_time": _utc_aware(next_appointment.scheduled_time),
                "estimated_duration": next_appointment.estimated_duration,
            }
            if next_appointment
            else None
        ),
        "active_appointment": (
            {
                "id": active_appointment.id,
                "client_name": active_appointment.client.full_name if active_appointment.client else "Cliente",
                "service_type": active_appointment.service_type,
                "scheduled_time": _utc_aware(active_appointment.scheduled_time),
                "estimated_duration": active_appointment.estimated_duration,
                "actual_start_time": (
                    _utc_aware(active_appointment.actual_start_time)
                    if active_appointment.actual_start_time else None
                ),
                "progress_percent": _service_progress_percent(active_appointment, now),
                "service_price": active_appointment.service_price,
                "status": active_appointment.status,
            }
            if active_appointment else None
        ),
        "appointments": [
            {
                "id": a.id,
                "client_name": a.client.full_name if a.client else "Cliente",
                "service_type": a.service_type,
                "scheduled_time": _utc_aware(a.scheduled_time),
                "estimated_duration": a.estimated_duration,
                "actual_start_time": _utc_aware(a.actual_start_time) if a.actual_start_time else None,
                "progress_percent": _service_progress_percent(a, now) if a.status == "in_progress" else 0,
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


@router.get("/barber/appointments")
def barber_appointments_for_date(
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Return one tenant-local agenda day, restricted to the authenticated barber when applicable."""
    user = _get_current_user(db, authorization)
    if user.role not in {"barber", "barbershop_owner", "super_admin"} or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado")

    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    business_date = target_date or _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    business_timezone = _get_timezone(shop)
    start = local_day_start_utc_naive(business_date, business_timezone)
    end = local_day_start_utc_naive(business_date + timedelta(days=1), business_timezone)
    query = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.scheduled_time >= start,
        Appointment.scheduled_time < end,
        Appointment.is_deleted == False,
    )
    if user.role == "barber":
        query = query.filter(Appointment.barber_id == user.id)

    appointments = query.order_by(Appointment.scheduled_time.asc(), Appointment.id.asc()).all()
    now = utc_now_naive()
    return {
        "business_date": business_date.isoformat(),
        "summary": {
            "total": len(appointments),
            "completed": sum(item.status == "completed" for item in appointments),
            "pending": sum(item.status in {"pending", "confirmed"} for item in appointments),
            "in_progress": sum(item.status == "in_progress" for item in appointments),
            "cancelled": sum(item.status == "cancelled" for item in appointments),
            "no_show": sum(item.status == "no_show" for item in appointments),
        },
        "appointments": [{
            "id": item.id,
            "client_name": item.client.full_name if item.client else "Cliente",
            "service_type": item.service_type,
            "scheduled_time": _utc_aware(item.scheduled_time),
            "estimated_duration": item.estimated_duration,
            "progress_percent": _service_progress_percent(item, now) if item.status == "in_progress" else 0,
            "service_price": item.service_price,
            "status": item.status,
        } for item in appointments],
    }


@router.get("/barber/appointments/calendar")
def barber_appointments_calendar(
    view: str = "week",
    anchor_date: Optional[date] = None,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Return a tenant-local week or month of real appointments for the calendar grid."""
    user = _get_current_user(db, authorization)
    if user.role not in {"barber", "barbershop_owner", "super_admin"} or not user.barbershop_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    if view not in {"week", "month"}:
        raise HTTPException(status_code=422, detail="La vista debe ser week o month")
    shop = db.query(Barbershop).filter(
        Barbershop.id == user.barbershop_id,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    anchor = anchor_date or _utc_aware(utc_now_naive()).astimezone(_get_timezone(shop)).date()
    if view == "week":
        start_date = anchor - timedelta(days=anchor.weekday())
        end_date = start_date + timedelta(days=7)
    else:
        start_date = anchor.replace(day=1)
        end_date = date(start_date.year + (start_date.month == 12),
                        1 if start_date.month == 12 else start_date.month + 1, 1)

    business_timezone = _get_timezone(shop)
    start_utc = local_day_start_utc_naive(start_date, business_timezone)
    end_utc = local_day_start_utc_naive(end_date, business_timezone)
    query = db.query(Appointment).filter(
        Appointment.barbershop_id == shop.id,
        Appointment.scheduled_time >= start_utc,
        Appointment.scheduled_time < end_utc,
        Appointment.is_deleted == False,
    )
    if user.role == "barber":
        query = query.filter(Appointment.barber_id == user.id)
    appointments = query.order_by(Appointment.scheduled_time.asc(), Appointment.id.asc()).all()
    grouped: dict[str, list[dict]] = {}
    now = utc_now_naive()
    for item in appointments:
        local_date = _utc_aware(item.scheduled_time).astimezone(_get_timezone(shop)).date().isoformat()
        grouped.setdefault(local_date, []).append({
            "id": item.id,
            "client_name": item.client.full_name if item.client else "Cliente",
            "service_type": item.service_type,
            "scheduled_time": _utc_aware(item.scheduled_time),
            "estimated_duration": item.estimated_duration,
            "progress_percent": _service_progress_percent(item, now) if item.status == "in_progress" else 0,
            "service_price": item.service_price,
            "status": item.status,
        })
    return {
        "view": view,
        "start_date": start_date.isoformat(),
        "end_date_exclusive": end_date.isoformat(),
        "anchor_date": anchor.isoformat(),
        "days": [{"date": day.isoformat(), "appointments": grouped.get(day.isoformat(), [])}
                 for day in (start_date + timedelta(days=offset)
                             for offset in range((end_date - start_date).days))],
        "summary": {
            "total": len(appointments),
            "completed": sum(item.status == "completed" for item in appointments),
            "pending": sum(item.status in {"pending", "confirmed"} for item in appointments),
            "in_progress": sum(item.status == "in_progress" for item in appointments),
            "cancelled": sum(item.status == "cancelled" for item in appointments),
            "no_show": sum(item.status == "no_show" for item in appointments),
        },
    }


@router.get("/admin/overview")
def admin_overview(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    now = utc_now_naive()
    month_start = datetime(now.year, now.month, 1)
    next_month = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
    tenant_count = db.query(func.count(Barbershop.id)).filter(Barbershop.is_deleted == False).scalar() or 0
    active_tenant_count = db.query(func.count(Barbershop.id)).filter(
        Barbershop.is_deleted == False, Barbershop.is_active == True,
    ).scalar() or 0
    active_user_count = db.query(func.count(User.id)).filter(
        User.is_deleted == False, User.is_active == True,
    ).scalar() or 0
    active_subscription_count = db.query(func.count(Subscription.id)).filter(
        Subscription.is_deleted == False,
        Subscription.status == "active",
        Subscription.current_period_start <= now,
        Subscription.current_period_end > now,
    ).scalar() or 0
    appointment_query = db.query(Appointment).filter(
        Appointment.created_at >= month_start,
        Appointment.created_at < next_month,
        Appointment.is_deleted == False,
    )
    appointment_count = appointment_query.count()
    completed_appointment_count = appointment_query.filter(Appointment.status == "completed").count()
    payment_totals = db.query(
        Payment.currency,
        func.sum(Payment.amount_cents + Payment.tip_cents),
    ).filter(
        Payment.received_at >= month_start,
        Payment.received_at < next_month,
        Payment.is_deleted == False,
    ).group_by(Payment.currency).order_by(Payment.currency).all()
    return {
        "period_start": month_start.date().isoformat(),
        "tenant_count": int(tenant_count),
        "active_tenant_count": int(active_tenant_count),
        "active_user_count": int(active_user_count),
        "active_subscription_count": int(active_subscription_count),
        "appointments_created_this_month": int(appointment_count),
        "appointments_completed_this_month": int(completed_appointment_count),
        "collected_this_month_by_currency": [
            {"currency": currency, "amount_cents": int(amount or 0)}
            for currency, amount in payment_totals
        ],
    }


@router.get("/admin/tenants", response_model=AdminTenantsResponse)
def admin_tenants(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_current_user(db, authorization)
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    owner_email = db.query(User.email).filter(
        User.barbershop_id == Barbershop.id,
        User.role == "barbershop_owner",
        User.is_deleted == False,
    ).order_by(User.id.asc()).limit(1).correlate(Barbershop).scalar_subquery()
    tenant_rows = db.query(
        Barbershop, owner_email, Subscription.plan, Subscription.status,
    ).outerjoin(
        Subscription, Subscription.id == Barbershop.subscription_id,
    ).filter(
        Barbershop.is_deleted == False,
    ).order_by(Barbershop.id.asc()).all()

    items = [
        AdminTenantItem(
            barbershop_id=shop.id,
            barbershop_name=shop.name,
            slug=shop.slug,
            owner_email=owner_email,
            plan=plan,
            subscription_status=subscription_status,
            active=shop.is_active,
        )
        for shop, owner_email, plan, subscription_status in tenant_rows
    ]

    return AdminTenantsResponse(items=items)


@router.get("/admin/affiliates")
def admin_list_affiliates(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    affiliates = db.query(Affiliate).filter(Affiliate.is_deleted == False).order_by(Affiliate.id.desc()).all()
    affiliate_ids = [affiliate.id for affiliate in affiliates]
    active_counts = {}
    commission_totals = {}
    if affiliate_ids:
        active_counts = dict(db.query(
            Barbershop.referred_by_affiliate_id, func.count(Barbershop.id)
        ).filter(
            Barbershop.referred_by_affiliate_id.in_(affiliate_ids),
            Barbershop.is_active == True,
            Barbershop.is_deleted == False,
        ).group_by(Barbershop.referred_by_affiliate_id).all())
        for affiliate_id, currency, earned, paid in db.query(
            Commission.affiliate_id, Commission.currency,
            func.sum(Commission.amount),
            func.sum(case((Commission.status == CommissionStatus.PAID, Commission.amount), else_=0)),
        ).filter(
            Commission.affiliate_id.in_(affiliate_ids),
            Commission.is_deleted == False,
        ).group_by(Commission.affiliate_id, Commission.currency).all():
            commission_totals.setdefault(affiliate_id, []).append({
                "currency": currency, "earned_cents": int(earned or 0), "paid_cents": int(paid or 0),
            })
    return {"items": [{
        "id": affiliate.id, "name": affiliate.full_name, "email": affiliate.email,
        "phone": affiliate.phone, "code": affiliate.code,
        "commission_rate": affiliate.commission_rate, "is_active": affiliate.is_active,
        "total_referrals": affiliate.total_referrals or 0,
        "active_referrals": int(active_counts.get(affiliate.id, 0)),
        "commission_totals_by_currency": commission_totals.get(affiliate.id, []),
    } for affiliate in affiliates]}


@router.post("/admin/affiliates", status_code=201)
def admin_create_affiliate(
    data: AdminAffiliateCreateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    email = str(data.email).lower()
    if db.query(Affiliate.id).filter(Affiliate.email == email, Affiliate.is_deleted == False).first():
        raise HTTPException(status_code=409, detail="El correo ya pertenece a un afiliado")
    code = secrets.token_urlsafe(8).replace("-", "").replace("_", "").upper()[:10]
    while db.query(Affiliate.id).filter(Affiliate.code == code).first():
        code = secrets.token_urlsafe(8).replace("-", "").replace("_", "").upper()[:10]
    affiliate = Affiliate(
        first_name=data.first_name.strip(), last_name=data.last_name.strip(), email=email,
        phone=_normalize_phone(data.phone or "") or None, code=code,
        commission_rate=data.commission_rate, joined_at=utc_now_naive(),
        total_referrals=0, active_referrals=0,
        total_commissions_earned=0, total_commissions_paid=0,
        is_active=True, is_verified=False,
    )
    db.add(affiliate)
    try:
        db.flush()
        _audit(db, admin, "affiliate.created", "affiliate", affiliate.id,
               details={"email": affiliate.email, "commission_rate": affiliate.commission_rate})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo crear el afiliado") from exc
    return {"id": affiliate.id, "email": affiliate.email, "name": affiliate.full_name,
            "code": affiliate.code, "commission_rate": affiliate.commission_rate}


@router.put("/admin/affiliates/{affiliate_id}/status")
def admin_update_affiliate_status(
    affiliate_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    affiliate = db.query(Affiliate).filter(
        Affiliate.id == affiliate_id,
        Affiliate.is_deleted == False,
    ).with_for_update().first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Afiliado no encontrado")
    affiliate.is_active = data.is_active
    _audit(db, admin, "affiliate.status_changed", "affiliate", affiliate.id,
           details={"is_active": affiliate.is_active})
    db.commit()
    return {"success": True, "affiliate_id": affiliate.id, "is_active": affiliate.is_active}


@router.get("/admin/affiliates/{affiliate_id}/commissions")
def admin_list_affiliate_commissions(
    affiliate_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id, Affiliate.is_deleted == False).first()
    if not affiliate:
        raise HTTPException(status_code=404, detail="Afiliado no encontrado")
    rows = db.query(Commission).filter(
        Commission.affiliate_id == affiliate_id,
        Commission.is_deleted == False,
    ).order_by(Commission.period_start.desc(), Commission.id.desc()).all()
    return {"items": [{
        "id": row.id, "barbershop_id": row.barbershop_id,
        "barbershop_name": row.barbershop.name if row.barbershop else None,
        "subscription_id": row.subscription_id, "amount_cents": row.amount,
        "commission_rate_percent": row.commission_rate,
        "period_start": row.period_start.isoformat(), "period_end": row.period_end.isoformat(),
        "status": row.status, "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "payment_method": row.payment_method, "payment_reference": row.payment_reference,
    } for row in rows]}


@router.post("/admin/commissions/{commission_id}/approve")
def admin_approve_commission(
    commission_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    commission = db.query(Commission).filter(
        Commission.id == commission_id, Commission.is_deleted == False,
    ).with_for_update().first()
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if commission.status != CommissionStatus.PENDING:
        raise HTTPException(status_code=409, detail="Solo se aprueban comisiones pendientes")
    commission.status = CommissionStatus.APPROVED
    _audit(db, admin, "affiliate.commission_approved", "commission", commission.id,
           commission.barbershop_id, {"amount_cents": commission.amount})
    db.commit()
    return {"success": True, "commission_id": commission.id, "status": commission.status}


@router.post("/admin/commissions/{commission_id}/pay")
def admin_pay_commission(
    commission_id: int,
    data: AdminCommissionPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    commission = db.query(Commission).filter(
        Commission.id == commission_id, Commission.is_deleted == False,
    ).with_for_update().first()
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if commission.status != CommissionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="La comisión debe aprobarse antes de pagarla")
    affiliate = db.query(Affiliate).filter(Affiliate.id == commission.affiliate_id).with_for_update().first()
    if not affiliate:
        raise HTTPException(status_code=409, detail="Afiliado de la comisión no encontrado")
    commission.status = CommissionStatus.PAID
    commission.paid_at = utc_now_naive()
    commission.payment_method = data.payment_method.strip()
    commission.payment_reference = data.payment_reference
    commission.payment_notes = data.payment_notes
    affiliate.total_commissions_paid = (affiliate.total_commissions_paid or 0) + commission.amount
    _audit(db, admin, "affiliate.commission_paid", "commission", commission.id,
           commission.barbershop_id, {"amount_cents": commission.amount,
                                      "payment_method": commission.payment_method})
    db.commit()
    return {"success": True, "commission_id": commission.id, "status": commission.status,
            "paid_at": commission.paid_at.isoformat()}


@router.get("/admin/audit-logs")
def admin_audit_logs(
    barbershop_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Read tenant-aware audit history; only the platform super admin can query it."""
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginación fuera de rango")
    query = db.query(AuditLog)
    if barbershop_id is not None:
        query = query.filter(AuditLog.barbershop_id == barbershop_id)
    rows = query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {"items": [{
        "id": row.id,
        "barbershop_id": row.barbershop_id,
        "actor_user_id": row.actor_user_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "occurred_at": row.occurred_at.isoformat(),
        "details": row.details,
    } for row in rows], "limit": limit, "offset": offset}


@router.put("/admin/tenants/{barbershop_id}/status")
def admin_update_tenant_status(
    barbershop_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")
    previous_status = shop.is_active
    if previous_status != data.is_active:
        now = utc_now_naive()
        tenant_user_ids = db.query(User.id).filter(
            User.barbershop_id == shop.id,
            User.is_deleted == False,
        )
        db.query(User).filter(
            User.barbershop_id == shop.id,
            User.is_deleted == False,
        ).update({User.auth_version: User.auth_version + 1}, synchronize_session=False)
        db.query(RefreshSession).filter(
            RefreshSession.user_id.in_(tenant_user_ids),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.is_deleted == False,
        ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    shop.is_active = data.is_active
    _audit(db, admin, "tenant.status_changed", "barbershop", shop.id, shop.id,
           {"previous_is_active": previous_status, "is_active": data.is_active})
    db.commit()
    return {"success": True, "barbershop_id": shop.id, "is_active": shop.is_active}


def _apply_plan_limits(sub: Subscription, plan: str) -> None:
    """Sync max_barbers/max_appointments_per_month/max_clients with the plan's defaults."""
    limits = next((l for key, l in SUBSCRIPTION_LIMITS.items() if key == plan), None)
    if limits is None:
        return

    sub.max_barbers = limits["max_barbers"]
    sub.max_appointments_per_month = limits["max_appointments_per_month"]
    sub.max_clients = limits["max_clients"]


@router.get("/admin/tenants/{barbershop_id}/subscription", response_model=AdminSubscriptionResponse)
def admin_get_subscription(
    barbershop_id: int,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id, Barbershop.is_deleted == False,
    ).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    if not shop.subscription_id:
        raise HTTPException(status_code=404, detail="La barbería no tiene una suscripción asociada")

    sub = db.query(Subscription).filter(Subscription.id == shop.subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    return AdminSubscriptionResponse(
        subscription_id=sub.id,
        barbershop_id=shop.id,
        plan=sub.plan,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        auto_renew=sub.auto_renew,
        max_barbers=sub.max_barbers,
        max_appointments_per_month=sub.max_appointments_per_month,
        max_clients=sub.max_clients,
    )


@router.put("/admin/tenants/{barbershop_id}/subscription", response_model=AdminSubscriptionResponse)
def admin_update_subscription(
    barbershop_id: int,
    data: AdminSubscriptionUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Gestiona plan, estado y cobros (mensualidad) de una barbería afiliada."""
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id,
        Barbershop.is_deleted == False,
    ).with_for_update().first()
    if not shop:
        raise HTTPException(status_code=404, detail="Barbería no encontrada")

    valid_plans = {"free", "basic", "professional", "enterprise"}
    valid_statuses = {"active", "inactive", "cancelled", "expired", "suspended"}

    if data.plan is not None and data.plan not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Plan inválido. Use uno de: {sorted(valid_plans)}")

    if data.status is not None and data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {sorted(valid_statuses)}")

    sub = None
    if shop.subscription_id:
        sub = db.query(Subscription).filter(
            Subscription.id == shop.subscription_id,
            Subscription.is_deleted == False,
        ).with_for_update().first()

    previous = None if sub is None else {
        "plan": sub.plan,
        "status": sub.status,
        "current_period_end": sub.current_period_end.isoformat(),
        "auto_renew": sub.auto_renew,
    }

    if not sub:
        # Crear una suscripción nueva si la barbería aún no tenía una asociada.
        now = utc_now_naive()
        period_end = data.current_period_end or (now + timedelta(days=30))
        if period_end.tzinfo is not None:
            period_end = period_end.astimezone(timezone.utc).replace(tzinfo=None)
        if period_end <= now:
            raise HTTPException(status_code=422, detail="El fin del periodo debe ser posterior al inicio")
        sub = Subscription(
            plan=data.plan or "free",
            status=data.status or "active",
            current_period_start=now,
            current_period_end=period_end,
            auto_renew=data.auto_renew if data.auto_renew is not None else True,
        )
        _apply_plan_limits(sub, sub.plan)
        db.add(sub)
        db.flush()
        shop.subscription_id = sub.id
    else:
        if data.plan is not None:
            sub.plan = data.plan
            _apply_plan_limits(sub, sub.plan)
        if data.status is not None:
            sub.status = data.status
        if data.current_period_end is not None:
            period_end = data.current_period_end
            if period_end.tzinfo is not None:
                period_end = period_end.astimezone(timezone.utc).replace(tzinfo=None)
            if period_end <= sub.current_period_start:
                raise HTTPException(status_code=422, detail="El fin del periodo debe ser posterior al inicio")
            sub.current_period_end = period_end
        if data.auto_renew is not None:
            sub.auto_renew = data.auto_renew

    _audit(
        db, admin, "subscription.updated", "subscription", sub.id, shop.id,
        {"previous": previous, "plan": sub.plan, "status": sub.status,
         "current_period_start": sub.current_period_start.isoformat(),
         "current_period_end": sub.current_period_end.isoformat(),
         "auto_renew": sub.auto_renew},
    )
    db.commit()
    db.refresh(sub)

    return AdminSubscriptionResponse(
        subscription_id=sub.id,
        barbershop_id=shop.id,
        plan=sub.plan,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        auto_renew=sub.auto_renew,
        max_barbers=sub.max_barbers,
        max_appointments_per_month=sub.max_appointments_per_month,
        max_clients=sub.max_clients,
    )


@router.post("/admin/tenants/{barbershop_id}/subscription/payments", status_code=201)
def admin_record_subscription_payment(
    barbershop_id: int,
    data: AdminSubscriptionPaymentRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    """Record an externally collected subscription charge and create its commission atomically."""
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    shop = db.query(Barbershop).filter(
        Barbershop.id == barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
    if not shop or not shop.subscription_id:
        raise HTTPException(status_code=404, detail="Barbería o suscripción no encontrada")
    subscription = db.query(Subscription).filter(
        Subscription.id == shop.subscription_id,
        Subscription.is_deleted == False,
    ).with_for_update().first()
    if not subscription:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    if subscription.plan == "free":
        raise HTTPException(status_code=409, detail="No se registra cobro para el plan gratuito")

    period_start = data.period_start
    period_end = data.period_end
    if period_start.tzinfo is not None:
        period_start = period_start.astimezone(timezone.utc).replace(tzinfo=None)
    if period_end.tzinfo is not None:
        period_end = period_end.astimezone(timezone.utc).replace(tzinfo=None)
    now = utc_now_naive()
    if period_end <= period_start or period_start > now or period_end <= now:
        raise HTTPException(status_code=422, detail="El periodo del pago debe ser válido y estar vigente")
    method = data.method.strip().lower()
    if method not in {"cash", "card", "bank_transfer", "other"}:
        raise HTTPException(status_code=422, detail="Método no válido: cash, card, bank_transfer u other")
    if db.query(SubscriptionPayment.id).filter(
        SubscriptionPayment.subscription_id == subscription.id,
        SubscriptionPayment.period_start == period_start,
        SubscriptionPayment.period_end == period_end,
        SubscriptionPayment.is_deleted == False,
    ).first():
        raise HTTPException(status_code=409, detail="Ese periodo ya tiene un pago registrado")

    payment = SubscriptionPayment(
        barbershop_id=shop.id,
        subscription_id=subscription.id,
        recorded_by_user_id=admin.id,
        amount_cents=data.amount_cents,
        currency=shop.currency,
        method=method,
        reference=data.reference,
        period_start=period_start,
        period_end=period_end,
        paid_at=now,
    )
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.status = "active"
    db.add(payment)
    try:
        db.flush()
        commission = AffiliateService.calculate_commission(
            db=db,
            barbershop_id=shop.id,
            subscription_id=subscription.id,
            period_start=period_start,
            period_end=period_end,
            subscription_amount_cents=data.amount_cents,
            commit=False,
        )
        _audit(db, admin, "subscription.payment_recorded", "subscription_payment", payment.id,
               shop.id, {"subscription_id": subscription.id,
                         "amount_cents": data.amount_cents, "currency": shop.currency,
                         "method": method, "commission_id": commission.id if commission else None})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El pago del periodo ya fue registrado") from exc
    return {"success": True, "payment_id": payment.id, "subscription_id": subscription.id,
            "amount_cents": payment.amount_cents, "currency": payment.currency,
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "commission_id": commission.id if commission else None,
            "subscription_status": subscription.status}


@router.get("/admin/users", response_model=AdminUsersResponse)
def admin_users(
    barbershop_id: Optional[int] = None,
    search: Optional[str] = Query(None, min_length=1, max_length=120),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")

    query = db.query(User).filter(User.is_deleted == False)
    if barbershop_id is not None:
        query = query.filter(User.barbershop_id == barbershop_id)
    search_term = search.strip() if search else ""
    if search_term:
        term = f"%{search_term}%"
        query = query.filter(or_(
            User.email.ilike(term),
            User.first_name.ilike(term),
            User.last_name.ilike(term),
        ))

    total = query.count()
    users = query.order_by(User.id.asc()).offset(offset).limit(limit).all()
    feature_rows = db.query(UserFeatureFlag).filter(
        UserFeatureFlag.user_id.in_([user.id for user in users]),
        UserFeatureFlag.is_deleted == False,
    ).all() if users else []
    feature_flags_by_user: dict[int, dict[str, bool]] = {}
    for feature in feature_rows:
        feature_flags_by_user.setdefault(feature.user_id, {})[feature.feature_key] = bool(feature.enabled)
    items = [
        AdminUserItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            barbershop_id=u.barbershop_id,
            is_active=u.is_active,
            support_contact_enabled=u.support_contact_enabled,
            feature_flags=feature_flags_by_user.get(u.id, {}),
        )
        for u in users
    ]
    return AdminUsersResponse(items=items, total=total, offset=offset, limit=limit)


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

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.role not in ["super_admin", "barbershop_owner", "barber"]:
        raise HTTPException(status_code=400, detail="Solo roles administrativos/barbero pueden recibir soporte")

    user.support_contact_enabled = data.support_contact_enabled
    _audit(db, admin, "user.support_contact_changed", "user", user.id, user.barbershop_id,
           {"enabled": data.support_contact_enabled})
    db.commit()
    return {"success": True, "user_id": user.id, "support_contact_enabled": user.support_contact_enabled}


@router.put("/admin/users/{user_id}/status")
def admin_update_user_status(
    user_id: int,
    data: AdminStatusUpdateRequest,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
):
    admin = _get_current_user(db, authorization)
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Solo super admin")
    # Serialize last-admin checks across all concurrent administrator changes.
    active_admin_ids = db.query(User.id).filter(
        User.role == "super_admin", User.is_active == True, User.is_deleted == False,
    ).order_by(User.id.asc()).with_for_update().all()
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not data.is_active and user.id == admin.id:
        raise HTTPException(status_code=409, detail="No puedes desactivar tu propia cuenta")
    if not data.is_active and user.role == "super_admin":
        if len(active_admin_ids) <= 1:
            raise HTTPException(status_code=409, detail="No se puede desactivar el último super administrador")
    previous_status = user.is_active
    if previous_status != data.is_active:
        now = utc_now_naive()
        user.auth_version += 1
        db.query(RefreshSession).filter(
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.is_deleted == False,
        ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    user.is_active = data.is_active
    _audit(db, admin, "user.status_changed", "user", user.id, user.barbershop_id,
           {"previous_is_active": previous_status, "is_active": data.is_active})
    db.commit()
    return {"success": True, "user_id": user.id, "is_active": user.is_active}


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

    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).with_for_update().first()
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

    db.flush()
    _audit(db, admin, "user.feature_changed", "user_feature_flag", feature.id,
           user.barbershop_id, {"user_id": user.id, "feature_key": data.feature_key,
                                "enabled": data.enabled})
    db.commit()
    return {"success": True, "user_id": user.id, "feature_key": data.feature_key, "enabled": data.enabled}
