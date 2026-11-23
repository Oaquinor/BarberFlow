"""Support requests retained for the platform support inbox."""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class SupportTicket(BaseModel):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_support_tickets_status_created", "status", "created_at"),
    )

    barbershop_id = Column(
        Integer,
        ForeignKey("barbershops.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sender_name = Column(String(120), nullable=False)
    sender_email = Column(String(320), nullable=True)
    sender_phone = Column(String(30), nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="open")
    notification_sent = Column(Boolean, nullable=False, default=False)

    barbershop = relationship("Barbershop")
