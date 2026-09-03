"""Models package."""

from app.models.base import BaseModel, TimestampMixin, SoftDeleteMixin
from app.models.user import User, UserFeatureFlag
from app.models.barbershop import Barbershop
from app.models.appointment import Appointment
from app.models.subscription import Subscription
from app.models.service import Service
from app.models.barber_performance import BarberPerformance
from app.models.affiliate import Affiliate
from app.models.commission import Commission
from app.models.achievement import Achievement, UserAchievement
from app.models.barber_availability import BarberAvailability

__all__ = [
    "BaseModel",
    "TimestampMixin",
    "SoftDeleteMixin",
    "User",
    "UserFeatureFlag",
    "Barbershop",
    "Appointment",
    "Subscription",
    "Service",
    "BarberPerformance",
    "Affiliate",
    "Commission",
    "Achievement",
    "UserAchievement",
    "BarberAvailability",
]
