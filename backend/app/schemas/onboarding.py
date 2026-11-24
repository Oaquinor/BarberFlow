"""
Onboarding schemas for barbershop personalization.
"""

from datetime import time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class OnboardingStep1(BaseModel):
    """Step 1: Basic barbershop info"""
    barbershop_name: str = Field(..., min_length=2, max_length=200)


class OnboardingStep2(BaseModel):
    """Step 2: Logo upload (handled separately via file upload)"""
    pass


class OnboardingStep3(BaseModel):
    """Step 3: Brand colors"""
    primary_color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')
    secondary_color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')


class OnboardingStep4(BaseModel):
    """Step 4: Barbershop style"""
    style: str = Field(..., pattern=r'^(classic|modern|urban|premium|family|custom)$')


class OnboardingStep5(BaseModel):
    """Step 5: Primary goal"""
    primary_goal: str = Field(
        ..., 
        pattern=r'^(more_clients|organization|reduce_cancellations|save_time|better_service|productivity)$'
    )


class OnboardingStep6(BaseModel):
    """Step 6: Team size"""
    team_size: int = Field(..., ge=1, le=100)


class OnboardingStep7(BaseModel):
    """Step 7: Services (handled by existing service creation)"""
    avg_service_duration: int = Field(..., ge=5, le=240)  # 5-240 minutes


class OnboardingStep8(BaseModel):
    """Step 8: Business hours"""
    opening_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')  # HH:MM
    closing_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')  # HH:MM


class OnboardingStep9(BaseModel):
    """Step 9: Personality"""
    personality: str = Field(
        ..., 
        pattern=r'^(professional|friendly|energetic|elegant|authentic)$'
    )


class OnboardingComplete(BaseModel):
    """Complete onboarding data"""
    barbershop_name: str = Field(..., min_length=2, max_length=200)
    primary_color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')
    secondary_color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')
    style: str = Field(..., pattern=r'^(classic|modern|urban|premium|family|custom)$')
    primary_goal: str = Field(..., pattern=r'^(more_clients|organization|reduce_cancellations|save_time|better_service|productivity)$')
    team_size: int = Field(..., ge=1, le=100)
    avg_service_duration: int = Field(..., ge=5, le=240)
    opening_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    closing_time: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    personality: str = Field(..., pattern=r'^(professional|friendly|energetic|elegant|authentic)$')
    logo_uploaded: bool = False

    @model_validator(mode="after")
    def validate_business_hours(self):
        try:
            opening = time.fromisoformat(self.opening_time)
            closing = time.fromisoformat(self.closing_time)
        except ValueError as exc:
            raise ValueError("Business hours must use valid HH:MM times") from exc
        if opening >= closing:
            raise ValueError("Opening time must be before closing time")
        return self


class BusinessSettingsUpdate(BaseModel):
    """Editable owner settings used by both the dashboard and public booking page."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    opening_time: time
    closing_time: time
    timezone: str = Field(..., min_length=3, max_length=50)
    primary_color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def validate_hours(self):
        if self.opening_time >= self.closing_time:
            raise ValueError("La hora de apertura debe preceder al cierre")
        return self

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("Selecciona una zona horaria IANA válida") from exc
        return value


class BarbershopProfile(BaseModel):
    """Barbershop profile for frontend"""
    id: int
    name: str
    currency: str = "USD"
    timezone: str
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    logo_url: Optional[str]
    description: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    style: Optional[str]
    primary_goal: Optional[str]
    team_size: Optional[int]
    avg_service_duration: Optional[int]
    personality: Optional[str]
    onboarding_completed: bool

    model_config = ConfigDict(from_attributes=True)


class DashboardLayoutResponse(BaseModel):
    """Goal-focused recommendations shown alongside the existing dashboard."""
    layout_type: str
    greeting_message: str
    insights: List[str]


class ContextualMessage(BaseModel):
    """Contextual message for UI"""
    type: str  # greeting, insight, celebration, warning
    message: str
    icon: str
    priority: str  # high, medium, low
