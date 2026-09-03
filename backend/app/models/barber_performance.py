"""
Performance model.

Tracks barber performance metrics and statistics.
"""

from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class BarberPerformance(BaseModel):
    """Barber performance tracking."""

    __tablename__ = "barber_performances"

    # Multi-tenant
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)
    barber_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Period
    date = Column(Date, nullable=False, index=True)

    # Metrics
    appointments_completed = Column(Integer, default=0)
    appointments_cancelled = Column(Integer, default=0)
    appointments_no_show = Column(Integer, default=0)
    total_revenue = Column(Integer, default=0)  # in cents

    # Time Metrics
    total_service_time_minutes = Column(Integer, default=0)
    average_service_time_minutes = Column(Float, nullable=True)
    time_efficiency_percentage = Column(Float, nullable=True)  # actual vs estimated

    # Streaks
    consecutive_days_worked = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)

    # Goals
    daily_goal_completed = Column(Integer, default=0)  # boolean as int

    # Additional Data
    extra_data = Column(JSON, nullable=True)  # for future extensions

    # Relationships
    barbershop = relationship("Barbershop")
    barber = relationship("User", foreign_keys=[barber_id])

    def __repr__(self) -> str:
        return f"<BarberPerformance(barber_id={self.barber_id}, date={self.date})>"
