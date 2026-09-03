"""
User model.

Represents system users (super admin, barbershop owners, barbers, clients).
"""

from sqlalchemy import Column, String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.core.constants import UserRole


class User(BaseModel):
    """User entity."""

    __tablename__ = "users"

    # Basic Info
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)

    # Role & Status
    role = Column(String(50), nullable=False, default=UserRole.CLIENT)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    support_contact_enabled = Column(Boolean, default=False, nullable=False)

    # Multi-tenant
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=True)

    # Profile
    avatar_url = Column(String(500), nullable=True)
    bio = Column(String(500), nullable=True)

    # Relationships
    barbershop = relationship("Barbershop", back_populates="users")
    appointments_as_client = relationship(
        "Appointment",
        foreign_keys="Appointment.client_id",
        back_populates="client"
    )
    appointments_as_barber = relationship(
        "Appointment",
        foreign_keys="Appointment.barber_id",
        back_populates="barber"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        return f"{self.first_name} {self.last_name}"


class UserFeatureFlag(BaseModel):
    """Feature flags por usuario para habilitar/deshabilitar módulos."""

    __tablename__ = "user_feature_flags"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    feature_key = Column(String(100), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
