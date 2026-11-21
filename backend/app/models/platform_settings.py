"""Singleton settings that control platform behavior, never secret credentials."""

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer

from app.models.base import BaseModel


class PlatformSettings(BaseModel):
    __tablename__ = "platform_settings"
    __table_args__ = (
        CheckConstraint("free_period_days BETWEEN 1 AND 365", name="ck_platform_settings_period_days"),
    )

    registrations_enabled = Column(Boolean, nullable=False, default=True)
    free_period_days = Column(Integer, nullable=False, default=30)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
