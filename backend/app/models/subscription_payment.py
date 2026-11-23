"""Externally collected subscription payments recorded by platform administration."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class SubscriptionPayment(BaseModel):
    __tablename__ = "subscription_payments"
    __table_args__ = (
        UniqueConstraint("subscription_id", "period_start", "period_end", name="uq_subscription_payment_period"),
        Index("ix_subscription_payments_shop_paid", "barbershop_id", "paid_at"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    method = Column(String(40), nullable=False)
    reference = Column(String(120), nullable=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=False)
