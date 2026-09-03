"""
Service model.

Represents services offered by a barbershop.
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Service(BaseModel):
    """Service entity."""

    __tablename__ = "services"

    # Multi-tenant
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)

    # Service Info
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=30)
    price = Column(Integer, nullable=False)  # in cents

    # Category
    category = Column(String(50), nullable=False)  # haircut, beard, combo, etc.

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Display
    display_order = Column(Integer, default=0)
    icon = Column(String(50), nullable=True)  # icon identifier

    # Relationships
    barbershop = relationship("Barbershop", back_populates="services")

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, name='{self.name}', price={self.price})>"

    @property
    def price_formatted(self) -> str:
        """Get formatted price."""
        return f"${self.price / 100:.2f}"
