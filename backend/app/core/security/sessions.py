"""Helpers for checking persisted, rotatable authentication sessions."""

from sqlalchemy.orm import Session

from app.models import RefreshSession
from app.utils.datetime import utc_now_naive


def access_session_is_active(db: Session, user_id: int, session_id: str) -> bool:
    """Return whether an access token's refresh session remains active."""
    return db.query(RefreshSession.id).filter(
        RefreshSession.user_id == user_id,
        RefreshSession.jti == session_id,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.expires_at > utc_now_naive(),
        RefreshSession.is_deleted == False,
    ).first() is not None
