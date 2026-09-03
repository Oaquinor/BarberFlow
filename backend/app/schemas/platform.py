"""
Schemas para operación productiva: auth, cliente público, barbero y admin.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    barbershop_id: Optional[int] = None


class AuthLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class PublicBarbershopResponse(BaseModel):
    id: int
    name: str
    slug: str
    logo_url: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    client_app_link: str


class PublicServiceResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    duration_minutes: int
    price_cents: int
    category: str


class PublicCreateAppointmentRequest(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=6, max_length=30)
    service_id: int
    scheduled_time: datetime
    notes: Optional[str] = None


class PublicAvailableSlotResponse(BaseModel):
    availability_id: int
    barber_id: int
    barber_name: str
    slot_start: datetime
    slot_end: datetime


class BarberCreateSlotsRequest(BaseModel):
    date: str = Field(..., description="Formato YYYY-MM-DD")
    start_time: str = Field(..., description="Formato HH:MM")
    end_time: str = Field(..., description="Formato HH:MM")
    slot_minutes: int = Field(30, ge=10, le=180)


class PublicCreateAppointmentResponse(BaseModel):
    appointment_id: int
    status: str
    tracking_link: str
    message: str


class PublicTrackAppointmentRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=30)
    appointment_id: Optional[int] = None


class PublicTrackAppointmentItem(BaseModel):
    appointment_id: int
    status: str
    scheduled_time: datetime
    service_type: str
    barber_name: Optional[str] = None


class PublicTrackAppointmentResponse(BaseModel):
    items: List[PublicTrackAppointmentItem]


class BarberShareLinkResponse(BaseModel):
    barbershop_name: str
    client_link: str
    whatsapp_share_link: str


class AdminTenantItem(BaseModel):
    barbershop_id: int
    barbershop_name: str
    slug: str
    owner_email: Optional[str] = None
    plan: Optional[str] = None
    subscription_status: Optional[str] = None
    active: bool


class AdminTenantsResponse(BaseModel):
    items: List[AdminTenantItem]


class SupportRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    message: str


class AdminUserSupportToggleRequest(BaseModel):
    support_contact_enabled: bool


class AdminUserFeatureFlagRequest(BaseModel):
    feature_key: str
    enabled: bool


class AdminSubscriptionUpdateRequest(BaseModel):
    plan: Optional[str] = Field(None, description="free|basic|professional|enterprise")
    status: Optional[str] = Field(None, description="active|inactive|cancelled|expired|suspended")
    current_period_end: Optional[datetime] = None
    auto_renew: Optional[bool] = None


class AdminSubscriptionResponse(BaseModel):
    subscription_id: int
    barbershop_id: int
    plan: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    auto_renew: bool
    max_barbers: Optional[int] = None
    max_appointments_per_month: Optional[int] = None
    max_clients: Optional[int] = None


class AdminUserItem(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    barbershop_id: Optional[int] = None
    is_active: bool
    support_contact_enabled: bool


class AdminUsersResponse(BaseModel):
    items: List[AdminUserItem]


class BarberAppointmentStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="pending|confirmed|in_progress|completed|cancelled|no_show")
