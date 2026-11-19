"""Non-enumerating, one-time password recovery endpoints."""

from datetime import timedelta
from hashlib import sha256
from html import escape
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security.password import hash_password
from app.models import LoginAttempt, PasswordResetToken, RefreshSession, User
from app.schemas.auth import PasswordResetConfirm, PasswordResetRequest
from app.services.audit_service import record_audit
from app.services.auth_record_retention import prune_expired_auth_records
from app.services.notification_service import NotificationService
from app.utils.datetime import utc_now_naive

router = APIRouter(prefix="/auth/password-reset", tags=["Authentication"])
RESET_TOKEN_TTL = timedelta(minutes=30)
RESET_RATE_WINDOW = timedelta(hours=1)
RESET_RATE_LIMIT = 5
RESET_IP_RATE_LIMIT = 30
GENERIC_REQUEST_MESSAGE = "Si el correo corresponde a una cuenta activa, recibirás instrucciones para recuperar el acceso."


def _deliver_reset_email(recipient: str, first_name: str, reset_url: str) -> None:
    body = (
        f"<p>Hola {escape(first_name)},</p>"
        "<p>Recibimos una solicitud para cambiar la contraseña de tu cuenta de KingFlow Barber.</p>"
        f'<p><a href="{escape(reset_url, quote=True)}">Crear una contraseña nueva</a></p>'
        "<p>El enlace vence en 30 minutos y solo se puede usar una vez. "
        "Si no solicitaste este cambio, ignora este mensaje.</p>"
    )
    NotificationService(None)._send_email(
        recipient, "Recupera el acceso a KingFlow Barber", body
    )


def _email_hash(email: str, client_ip: str) -> str:
    secret = get_settings().SECRET_KEY
    return sha256(f"password-reset:{email}:{client_ip}:{secret}".encode("utf-8")).hexdigest()


def _ip_hash(client_ip: str) -> str:
    secret = get_settings().SECRET_KEY
    return sha256(f"password-reset-ip:{client_ip}:{secret}".encode("utf-8")).hexdigest()


def _consume_bucket(db: Session, key_hash: str, limit: int, now) -> None:
    row = db.query(LoginAttempt).filter(LoginAttempt.key_hash == key_hash).with_for_update().first()
    if not row:
        try:
            with db.begin_nested():
                row = LoginAttempt(
                    key_hash=key_hash,
                    failed_count=0,
                    window_started_at=now,
                    last_attempt_at=now,
                )
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.query(LoginAttempt).filter(LoginAttempt.key_hash == key_hash).with_for_update().first()
    if now - row.window_started_at >= RESET_RATE_WINDOW:
        row.failed_count = 0
        row.window_started_at = now
        row.locked_until = None
    if row.locked_until and row.locked_until > now:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta más tarde.")
    row.failed_count += 1
    row.last_attempt_at = now
    if row.failed_count >= limit:
        row.locked_until = now + RESET_RATE_WINDOW


def _consume_request_quota(db: Session, email: str, client_ip: str, now) -> None:
    _consume_bucket(db, _email_hash(email, client_ip), RESET_RATE_LIMIT, now)
    _consume_bucket(db, _ip_hash(client_ip), RESET_IP_RATE_LIMIT, now)


@router.post("/request", status_code=202)
def request_password_reset(
    data: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    now = utc_now_naive()
    prune_expired_auth_records(db, now)
    email = str(data.email).strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    _consume_request_quota(db, email, client_ip, now)

    user = db.query(User).filter(
        User.email == email,
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not user:
        db.commit()
        return {"message": GENERIC_REQUEST_MESSAGE}

    raw_token = secrets.token_urlsafe(32)
    token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.consumed_at.is_(None),
        PasswordResetToken.revoked_at.is_(None),
    ).update({PasswordResetToken.revoked_at: now}, synchronize_session=False)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + RESET_TOKEN_TTL,
    )
    db.add(reset_token)
    db.commit()

    settings = get_settings()
    reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password.html?token={raw_token}"
    # Send after the generic response to reduce account-existence timing leaks.
    background_tasks.add_task(_deliver_reset_email, user.email, user.first_name, reset_url)
    return {"message": GENERIC_REQUEST_MESSAGE}


@router.post("/confirm")
def confirm_password_reset(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    now = utc_now_naive()
    token_hash = sha256(data.token.encode("utf-8")).hexdigest()
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.consumed_at.is_(None),
        PasswordResetToken.revoked_at.is_(None),
        PasswordResetToken.expires_at > now,
        PasswordResetToken.is_deleted == False,
    ).with_for_update().first()
    if not reset_token:
        raise HTTPException(status_code=400, detail="El enlace no es válido o ya venció")
    user = db.query(User).filter(
        User.id == reset_token.user_id,
        User.is_active == True,
        User.is_deleted == False,
    ).with_for_update().first()
    if not user:
        reset_token.revoked_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="El enlace no es válido o ya venció")

    user.password_hash = hash_password(data.new_password)
    user.auth_version += 1
    reset_token.consumed_at = now
    db.query(RefreshSession).filter(
        RefreshSession.user_id == user.id,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.is_deleted == False,
    ).update({RefreshSession.revoked_at: now}, synchronize_session=False)
    record_audit(
        db, user, "auth.password_reset", "user", user.id,
        details={"method": "email_token"},
    )
    db.commit()
    return {"success": True, "message": "Contraseña actualizada. Inicia sesión con tu nueva contraseña."}
