"""
Disponibilidad de turnos configurados por barbero.
"""

from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class BarberAvailability(BaseModel):
    __tablename__ = "barber_availabilities"

    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)
    barber_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    slot_start = Column(DateTime, nullable=False, index=True)
    slot_end = Column(DateTime, nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    is_booked = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("barber_id", "slot_start", name="uq_barber_slot_start"),
    )

    barber = relationship("User", foreign_keys=[barber_id])
    barbershop = relationship("Barbershop", foreign_keys=[barbershop_id])
