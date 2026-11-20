"""Tenant scoped, durable inbox notifications for authenticated users."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class InAppNotification(BaseModel):
    __tablename__ = "in_app_notifications"
    __table_args__ = (
        UniqueConstraint("recipient_user_id", "dedupe_key", name="uq_in_app_notification_recipient_key"),
        Index("ix_in_app_notifications_recipient_unread", "recipient_user_id", "read_at", "created_at"),
        Index("ix_in_app_notifications_shop_created", "barbershop_id", "created_at"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    dedupe_key = Column(String(191), nullable=False)
    event_type = Column(String(50), nullable=False)
    title = Column(String(180), nullable=False)
    message = Column(String(1000), nullable=False)
    entity_type = Column(String(40), nullable=True)
    entity_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)
    read_at = Column(DateTime, nullable=True)
