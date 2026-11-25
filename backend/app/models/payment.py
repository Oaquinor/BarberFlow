"""Immutable records of completed appointment payments."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index

from app.models.base import BaseModel


class Payment(BaseModel):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_payments_appointment_id"),
        Index("ix_payments_shop_received", "barbershop_id", "received_at"),
        Index("ix_payments_barber_received", "barber_id", "received_at"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False)
    barber_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    tip_cents = Column(Integer, nullable=False, default=0)
    method = Column(String(20), nullable=False)
    currency = Column(String(3), nullable=False)
    received_at = Column(DateTime, nullable=False)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class CashRegisterClose(BaseModel):
    __tablename__ = "cash_register_closes"
    __table_args__ = (
        UniqueConstraint("barbershop_id", "closed_by_user_id", "business_date", name="uq_cash_close_scope_date"),
        Index("ix_cash_close_shop_date", "barbershop_id", "business_date"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    closed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    business_date = Column(DateTime, nullable=False)
    expected_cash_cents = Column(Integer, nullable=False)
    opening_cash_cents = Column(Integer, nullable=False, default=0)
    declared_cash_cents = Column(Integer, nullable=False)
    difference_cents = Column(Integer, nullable=False)
    payment_count = Column(Integer, nullable=False)
    notes = Column(String(1000), nullable=True)
    closed_at = Column(DateTime, nullable=False)
