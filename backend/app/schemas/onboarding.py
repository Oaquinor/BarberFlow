"""
Onboarding schemas for barbershop personalization.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, validator


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
    barbershop_name: str
    primary_color: str
    secondary_color: str
    style: str
    primary_goal: str
    team_size: int
    avg_service_duration: int
    opening_time: str
    closing_time: str
    personality: str
    logo_uploaded: bool = False


class BarbershopProfile(BaseModel):
    """Barbershop profile for frontend"""
    id: int
    name: str
    logo_url: Optional[str]
    primary_color: str
    secondary_color: str
    style: Optional[str]
    primary_goal: Optional[str]
    team_size: Optional[int]
    avg_service_duration: Optional[int]
    personality: Optional[str]
    onboarding_completed: bool

    class Config:
        from_attributes = True


class DashboardLayoutResponse(BaseModel):
    """Dashboard layout adapted to barbershop goal"""
    layout_type: str
    priority_metrics: List[str]
    widgets: List[str]
    greeting_message: str
    insights: List[str]


class ContextualMessage(BaseModel):
    """Contextual message for UI"""
    type: str  # greeting, insight, celebration, warning
    message: str
    icon: str
    priority: str  # high, medium, low
