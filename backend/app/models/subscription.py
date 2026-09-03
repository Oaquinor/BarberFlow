"""
Subscription model.

Represents barbershop subscription plans.
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.core.constants import SubscriptionPlan, SubscriptionStatus


class Subscription(BaseModel):
    """Subscription entity."""

    __tablename__ = "subscriptions"

    # Plan
    plan = Column(String(50), nullable=False, default=SubscriptionPlan.FREE)
    status = Column(String(50), nullable=False, default=SubscriptionStatus.ACTIVE)

    # Billing
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)

    # Limits
    max_barbers = Column(Integer, nullable=True)
    max_appointments_per_month = Column(Integer, nullable=True)
    max_clients = Column(Integer, nullable=True)

    # Payment
    stripe_subscription_id = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(255), nullable=True)

    # Trial
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    is_trial = Column(Boolean, default=False)

    # Auto-renewal
    auto_renew = Column(Boolean, default=True)

    # Relationships
    barbershop = relationship("Barbershop", back_populates="subscription", uselist=False)

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, plan='{self.plan}', status='{self.status}')>"
