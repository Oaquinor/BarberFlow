"""Persistent login failure buckets used to throttle password guessing."""

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, Index

from app.models.base import BaseModel


class LoginAttempt(BaseModel):
    __tablename__ = "login_attempts"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_login_attempts_key_hash"),
        Index("ix_login_attempts_locked_until", "locked_until"),
        Index("ix_login_attempts_last_attempt_at", "last_attempt_at"),
    )

    key_hash = Column(String(64), nullable=False)
    failed_count = Column(Integer, nullable=False, default=0)
    window_started_at = Column(DateTime, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, nullable=False)
