"""
Achievement model.

Tracks achievements and badges for gamification.
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Achievement(BaseModel):
    """Achievement definition."""

    __tablename__ = "achievements"

    # Achievement Info
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    icon = Column(String(50), nullable=False)  # emoji or icon identifier
    category = Column(String(50), nullable=False)  # streak, productivity, milestone

    # Requirements
    requirement_type = Column(String(50), nullable=False)  # appointments, streak, revenue
    requirement_value = Column(Integer, nullable=False)

    # Display
    points = Column(Integer, default=0)
    rarity = Column(String(20), default="common")  # common, rare, epic, legendary

    # Status
    is_active = Column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Achievement(code='{self.code}', name='{self.name}')>"


class UserAchievement(BaseModel):
    """User achievement tracking."""

    __tablename__ = "user_achievements"

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False, index=True)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False, index=True)

    # Tracking
    earned_at = Column(DateTime, nullable=False)
    progress = Column(Integer, default=100)  # percentage
    is_viewed = Column(Boolean, default=False)

    # Context
    context_data = Column(JSON, nullable=True)  # additional data about how it was earned

    # Relationships
    user = relationship("User")
    achievement = relationship("Achievement")
    barbershop = relationship("Barbershop")

    def __repr__(self) -> str:
        return f"<UserAchievement(user_id={self.user_id}, achievement_id={self.achievement_id})>"
