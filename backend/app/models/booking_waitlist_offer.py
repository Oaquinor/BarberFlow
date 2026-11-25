"""Expiring, single-use offers for real appointment slots."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from app.models.base import BaseModel


class BookingWaitlistOffer(BaseModel):
    __tablename__ = "booking_waitlist_offers"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_waitlist_offer_token_hash"),
        UniqueConstraint("appointment_id", name="uq_waitlist_offer_appointment"),
        Index("ix_waitlist_offer_entry_state", "waitlist_entry_id", "status", "expires_at"),
        Index("ix_waitlist_offer_slot_state", "availability_id", "status", "expires_at"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'cancelled')",
            name="ck_waitlist_offer_status",
        ),
    )

    barbershop_id = Column(
        Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False
    )
    waitlist_entry_id = Column(
        Integer, ForeignKey("booking_waitlist_entries.id", ondelete="RESTRICT"), nullable=False
    )
    availability_id = Column(
        Integer,
        ForeignKey("barber_availabilities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    appointment_id = Column(
        Integer, ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=True
    )
    token_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
