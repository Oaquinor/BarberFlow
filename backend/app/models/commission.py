"""
Commission model.

Tracks commissions for affiliate referrals.
"""

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.core.constants import CommissionStatus


class Commission(BaseModel):
    """Commission entity."""

    __tablename__ = "commissions"

    # Relationships
    affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=False, index=True)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)

    # Amount
    amount = Column(Integer, nullable=False)  # in cents
    commission_rate = Column(Integer, nullable=False)  # percentage * 100

    # Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Status
    status = Column(String(50), nullable=False, default=CommissionStatus.PENDING, index=True)

    # Payment
    paid_at = Column(DateTime, nullable=True)
    payment_method = Column(String(50), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    payment_notes = Column(Text, nullable=True)

    # Relationships
    affiliate = relationship("Affiliate", back_populates="commissions")
    barbershop = relationship("Barbershop")
    subscription = relationship("Subscription")

    def __repr__(self) -> str:
        return f"<Commission(id={self.id}, affiliate_id={self.affiliate_id}, amount={self.amount}, status='{self.status}')>"

    @property
    def amount_formatted(self) -> str:
        """Get formatted amount."""
        return f"${self.amount / 100:.2f}"
