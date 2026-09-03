"""
Affiliate model.

Represents affiliate partners who refer barbershops.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Affiliate(BaseModel):
    """Affiliate entity."""

    __tablename__ = "affiliates"

    # Personal Info
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=True)

    # Affiliate Info
    code = Column(String(50), unique=True, nullable=False, index=True)
    commission_rate = Column(Float, nullable=False, default=0.15)  # 15%

    # Bank Info
    bank_account = Column(String(100), nullable=True)
    bank_name = Column(String(100), nullable=True)
    id_number = Column(String(50), nullable=True)

    # Stats
    total_referrals = Column(Integer, default=0)
    active_referrals = Column(Integer, default=0)
    total_commissions_earned = Column(Integer, default=0)  # in cents
    total_commissions_paid = Column(Integer, default=0)  # in cents

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    joined_at = Column(DateTime, nullable=True)

    # Relationships
    referrals = relationship("Barbershop", back_populates="referred_by_affiliate")
    commissions = relationship("Commission", back_populates="affiliate")

    def __repr__(self) -> str:
        return f"<Affiliate(id={self.id}, code='{self.code}', email='{self.email}')>"

    @property
    def full_name(self) -> str:
        """Get affiliate's full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def pending_commissions(self) -> int:
        """Calculate pending commissions."""
        return self.total_commissions_earned - self.total_commissions_paid
