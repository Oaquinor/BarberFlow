"""Persisted refresh token sessions with rotation and revocation support."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.models.base import BaseModel


class RefreshSession(BaseModel):
    __tablename__ = "refresh_sessions"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti = Column(String(36), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
