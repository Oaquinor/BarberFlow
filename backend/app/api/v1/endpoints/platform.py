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
from time import sleep as sleep_seconds

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy import func, or_, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core import get_db
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
from app.models.affiliate import Affiliate
from app.models.platform_settings import PlatformSettings
from app.models.support_ticket import SupportTicket
from app.models.achievement import Achievement, UserAchievement
from app.models.barber_performance import BarberPerformance
from app.schemas.auth import PasswordChangeRequest, RefreshTokenRequest, RefreshTokenResponse
from app.schemas.platform import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthUserResponse,
    TenantRegistrationRequest,
    SupportRequest,
    BarberAppointmentStatusUpdateRequest,
    AppointmentPaymentRequest,
    CashRegisterCloseRequest,
)
from app.utils.datetime import local_day_start_utc_naive, utc_now_naive
from app.utils.client_ip import get_client_ip
from app.services.notification_service import NotificationService
from app.services.notification_outbox import enqueue_delivery
from app.services.auth_record_retention import prune_expired_auth_records
from app.api.v1.endpoints.common import (
    _apply_plan_limits,
    _audit,
    _cash_register_closed_for_user,
    _get_current_user,
    _get_timezone,
    _utc_aware,
)

router = APIRouter(tags=["platform"])
settings = get_settings()
logger = get_logger(__name__)
DUMMY_LOGIN_PASSWORD_HASH = hash_password("unusable-login-sentinel-value")




def _build_client_link(slug: str) -> str:
    frontend_base = os.getenv("FRONTEND_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{frontend_base}/client.html?shop={slug}"


def _get_public_shop(db: Session, slug: str) -> Optional[Barbershop]:
    return db.query(Barbershop).filter(
        Barbershop.slug == slug,
        Barbershop.is_active == True,
        Barbershop.is_deleted == False,
    ).first()




def _parse_date_time(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")




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




def _business_date_for_appointment(appointment: Appointment, shop: Barbershop):
    """Return the appointment's calendar date in its barbershop's timezone."""
    return _utc_aware(appointment.scheduled_time).astimezone(_get_timezone(shop)).date()




def _service_progress_percent(appointment: Appointment, now_utc: datetime) -> int:
    """Estimate elapsed service time from the persisted UTC start timestamp."""
    if not appointment.actual_start_time or appointment.estimated_duration <= 0:
        return 0
    elapsed_minutes = max(0, (now_utc - appointment.actual_start_time).total_seconds() / 60)
    return min(100, int(round(elapsed_minutes / appointment.estimated_duration * 100)))




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
    client = db.query(User).filter(
        User.id == appointment.client_id,
        User.is_deleted == False,
    ).first()
    if not client or not client.email or client.email.endswith("@client.invalid"):
        return None
    barber = db.query(User).filter(
        User.id == appointment.barber_id,
        User.is_deleted == False,
    ).first()
    shop = db.query(Barbershop).filter(
        Barbershop.id == appointment.barbershop_id,
        Barbershop.is_deleted == False,
    ).first()
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
        if shop and appointment.client and not appointment.client.is_deleted and appointment.client.phone:
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
        shop = db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id,
            Barbershop.is_deleted == False,
        ).first()
        if shop and appointment.client and not appointment.client.is_deleted and appointment.client.phone:
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
    if appointment.client and not appointment.client.is_deleted and appointment.client.phone:
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
                "client_name": (
                    next_appointment.client.full_name
                    if next_appointment.client and not next_appointment.client.is_deleted else "Cliente"
                ),
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
                "client_name": (
                    active_appointment.client.full_name
                    if active_appointment.client and not active_appointment.client.is_deleted else "Cliente"
                ),
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
