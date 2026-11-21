"""Bound storage growth for expired authentication throttles and reset links."""

from datetime import datetime, timedelta
import logging
from threading import Lock
from time import monotonic

from sqlalchemy.orm import Session

from app.models import LoginAttempt, PasswordResetToken

logger = logging.getLogger(__name__)
CLEANUP_INTERVAL_SECONDS = 900
RETENTION_AGE = timedelta(days=1)
MAX_ROWS_PER_TABLE = 1000
_cleanup_lock = Lock()
_last_cleanup_at = 0.0


def prune_expired_auth_records(db: Session, now: datetime, *, force: bool = False) -> int:
    """Delete at most 1,000 stale throttle rows and reset tokens per 15 minutes per process."""
    global _last_cleanup_at
    current = monotonic()
    if not force and current - _last_cleanup_at < CLEANUP_INTERVAL_SECONDS:
        return 0

    with _cleanup_lock:
        current = monotonic()
        if not force and current - _last_cleanup_at < CLEANUP_INTERVAL_SECONDS:
            return 0
        cutoff = now - RETENTION_AGE
        try:
            with db.begin_nested():
                attempt_ids = [row[0] for row in db.query(LoginAttempt.id).filter(
                    LoginAttempt.last_attempt_at < cutoff,
                    LoginAttempt.is_deleted == False,
                ).order_by(LoginAttempt.last_attempt_at.asc()).limit(MAX_ROWS_PER_TABLE).all()]
                if attempt_ids:
                    db.query(LoginAttempt).filter(LoginAttempt.id.in_(attempt_ids)).delete(
                        synchronize_session=False
                    )

                token_ids = [row[0] for row in db.query(PasswordResetToken.id).filter(
                    PasswordResetToken.expires_at < cutoff,
                    PasswordResetToken.is_deleted == False,
                ).order_by(PasswordResetToken.expires_at.asc()).limit(MAX_ROWS_PER_TABLE).all()]
                if token_ids:
                    db.query(PasswordResetToken).filter(PasswordResetToken.id.in_(token_ids)).delete(
                        synchronize_session=False
                    )
            _last_cleanup_at = current
            return len(attempt_ids) + len(token_ids)
        except Exception:
            logger.exception("Could not prune expired authentication records")
            return 0
