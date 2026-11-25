"""Customer requests to be contacted when appointment availability changes."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.models.base import BaseModel


class BookingWaitlistEntry(BaseModel):
    """Tenant-scoped, non-binding request for appointment availability."""

    __tablename__ = "booking_waitlist_entries"
    __table_args__ = (
        Index("ix_waitlist_shop_status_created", "barbershop_id", "status", "created_at"),
        Index("ix_waitlist_shop_phone", "barbershop_id", "phone"),
        UniqueConstraint("barbershop_id", "request_key_hash", name="uq_waitlist_shop_request_key"),
        CheckConstraint("status IN ('new', 'contacted', 'closed')", name="ck_waitlist_status"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    request_key_hash = Column(String(64), nullable=False)
    service_name_snapshot = Column(String(100), nullable=False)
    barber_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    barber_name_snapshot = Column(String(201), nullable=True)
    client_name = Column(String(120), nullable=False)
    phone = Column(String(20), nullable=False)
    preferred_date_start = Column(Date, nullable=True)
    preferred_date_end = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="new", server_default="new")
    contacted_at = Column(DateTime, nullable=True)
