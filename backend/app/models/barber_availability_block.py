"""Ranges during which a barber cannot accept appointments."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.models.base import BaseModel


class BarberAvailabilityBlock(BaseModel):
    __tablename__ = "barber_availability_blocks"

    barbershop_id = Column(Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False)
    barber_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_availability_blocks_barber_range", "barber_id", "starts_at", "ends_at"),
        Index("ix_availability_blocks_tenant", "barbershop_id", "barber_id"),
    )
