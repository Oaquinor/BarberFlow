"""Current operational presence selected by a barber."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class BarberLiveState(BaseModel):
    """Persist an explicit available/on-break state per tenant barber."""

    __tablename__ = "barber_live_states"
    __table_args__ = (
        UniqueConstraint("barber_id", name="uq_barber_live_state_barber"),
        CheckConstraint("state IN ('available', 'on_break')", name="ck_barber_live_state"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)
    barber_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    state = Column(String(20), nullable=False, default="available", server_default="available")
    expected_return_at = Column(DateTime, nullable=True)
