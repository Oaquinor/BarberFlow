"""Durable external notification outbox backed by MySQL."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.models.base import BaseModel


class NotificationDelivery(BaseModel):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("barbershop_id", "dedupe_key", name="uq_notification_delivery_dedupe"),
        Index("ix_notification_deliveries_due", "status", "next_attempt_at", "scheduled_for"),
        Index("ix_notification_deliveries_appointment", "appointment_id", "event_type"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=True)
    dedupe_key = Column(String(191), nullable=False)
    channel = Column(String(16), nullable=False)
    event_type = Column(String(50), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    scheduled_for = Column(DateTime, nullable=False)
    next_attempt_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    last_error = Column(String(500), nullable=True)
