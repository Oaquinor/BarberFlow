"""
Appointment model.

Represents a booking/appointment between a client and barber.
"""

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.core.constants import AppointmentStatus, ServiceType


class Appointment(BaseModel):
    """Appointment entity."""

    __tablename__ = "appointments"

    # Multi-tenant
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)

    # Participants
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    barber_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Scheduling
    scheduled_time = Column(DateTime, nullable=False, index=True)
    estimated_duration = Column(Integer, nullable=False, default=30)  # minutes
    actual_start_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True)

    # Service
    service_type = Column(String(50), nullable=False, default=ServiceType.HAIRCUT)
    service_price = Column(Integer, nullable=True)  # in cents

    # Status
    status = Column(String(50), nullable=False, default=AppointmentStatus.PENDING, index=True)

    # Notes
    client_notes = Column(Text, nullable=True)
    barber_notes = Column(Text, nullable=True)

    # Cancellation
    cancelled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Check-in
    checked_in_at = Column(DateTime, nullable=True)

    # Relationships
    barbershop = relationship("Barbershop", back_populates="appointments")
    client = relationship(
        "User",
        foreign_keys=[client_id],
        back_populates="appointments_as_client"
    )
    barber = relationship(
        "User",
        foreign_keys=[barber_id],
        back_populates="appointments_as_barber"
    )

    def __repr__(self) -> str:
        return f"<Appointment(id={self.id}, client_id={self.client_id}, barber_id={self.barber_id}, status='{self.status}')>"

    @property
    def actual_duration(self) -> int | None:
        """Calculate actual duration in minutes."""
        if self.actual_start_time and self.actual_end_time:
            delta = self.actual_end_time - self.actual_start_time
            return int(delta.total_seconds() / 60)
        return None

    @property
    def is_completed(self) -> bool:
        """Check if appointment is completed."""
        return self.status == AppointmentStatus.COMPLETED

    @property
    def is_active(self) -> bool:
        """Check if appointment is active (confirmed or in progress)."""
        return self.status in [AppointmentStatus.CONFIRMED, AppointmentStatus.IN_PROGRESS]
