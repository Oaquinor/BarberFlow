"""
Barbershop model.

Represents a barbershop (tenant in multi-tenant architecture).
"""

from sqlalchemy import Column, String, Integer, Boolean, Time, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Barbershop(BaseModel):
    """Barbershop entity (tenant)."""

    __tablename__ = "barbershops"

    # Basic Info
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(1000), nullable=True)

    # Contact
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    website = Column(String(255), nullable=True)

    # Address
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    postal_code = Column(String(20), nullable=False)
    country = Column(String(100), nullable=False, default="USA")

    # Location
    latitude = Column(String(50), nullable=True)
    longitude = Column(String(50), nullable=True)

    # Branding
    logo_url = Column(String(500), nullable=True)
    cover_image_url = Column(String(500), nullable=True)

    # Personalización (Onboarding)
    primary_color = Column(String(7), nullable=True, default="#667eea")  # Hex color
    secondary_color = Column(String(7), nullable=True, default="#764ba2")  # Hex color
    style = Column(String(50), nullable=True)  # classic, modern, urban, premium, family, custom
    primary_goal = Column(String(50), nullable=True)  # more_clients, organization, reduce_cancellations, save_time, better_service, productivity
    team_size = Column(Integer, nullable=True)  # Number of barbers
    avg_service_duration = Column(Integer, nullable=True)  # Minutes
    personality = Column(String(50), nullable=True)  # professional, friendly, energetic, elegant, authentic
    onboarding_completed = Column(Boolean, default=False, nullable=False)

    # Business Hours (default)
    opening_time = Column(Time, nullable=True)
    closing_time = Column(Time, nullable=True)

    # Settings
    timezone = Column(String(50), nullable=False, default="America/New_York")
    currency = Column(String(3), nullable=False, default="USD")
    appointment_duration_minutes = Column(Integer, nullable=False, default=30)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Subscription
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)

    # Affiliate
    referred_by_affiliate_id = Column(Integer, ForeignKey("affiliates.id"), nullable=True)

    # Branding Colors (for personalization)
    primary_color = Column(String(7), nullable=True)  # hex color
    secondary_color = Column(String(7), nullable=True)

    # Relationships
    users = relationship("User", back_populates="barbershop")
    appointments = relationship("Appointment", back_populates="barbershop")
    subscription = relationship("Subscription", back_populates="barbershop")
    services = relationship("Service", back_populates="barbershop")
    referred_by_affiliate = relationship("Affiliate", back_populates="referrals")

    def __repr__(self) -> str:
        return f"<Barbershop(id={self.id}, name='{self.name}', slug='{self.slug}')>"
