"""Service commissions accrued by barbers from completed, paid appointments."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class BarberCommission(BaseModel):
    __tablename__ = "barber_commissions"
    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_barber_commissions_payment"),
        Index("ix_barber_commissions_shop_barber_status", "barbershop_id", "barber_id", "status"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    barber_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    rate_basis_points = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    accrued_at = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    paid_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    payment_method = Column(String(20), nullable=True)
    payment_reference = Column(String(120), nullable=True)
