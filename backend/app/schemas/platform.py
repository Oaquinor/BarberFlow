"""
Schemas para operación productiva: auth, cliente público, barbero y admin.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password exceeds the supported 72-byte limit")
        return value


class TenantRegistrationRequest(BaseModel):
    """Create an owner account, tenant and free subscription as one operation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    owner_email: EmailStr
    owner_password: str = Field(..., min_length=12, max_length=72)
    owner_first_name: str = Field(..., min_length=2, max_length=100)
    owner_last_name: str = Field(..., min_length=2, max_length=100)
    owner_phone: str = Field(..., min_length=6, max_length=30)
    barbershop_name: str = Field(..., min_length=2, max_length=200)
    barbershop_email: EmailStr
    barbershop_phone: str = Field(..., min_length=6, max_length=20)
    address_line1: str = Field(..., min_length=3, max_length=255)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    postal_code: str = Field(..., min_length=2, max_length=20)
    country: str = Field(..., min_length=2, max_length=100)
    timezone: str = Field(..., min_length=3, max_length=50)
    currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    affiliate_code: Optional[str] = Field(None, min_length=4, max_length=50)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("Select a valid IANA time zone") from exc
        return value

    @field_validator("affiliate_code")
    @classmethod
    def normalize_affiliate_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        code = value.strip().upper()
        if not code.isalnum():
            raise ValueError("El código de afiliado solo puede contener letras y números")
        return code

    @field_validator("owner_password")
    @classmethod
    def validate_owner_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 UTF-8 bytes")
        if not any(character.isupper() for character in value) or not any(character.isdigit() for character in value):
            raise ValueError("Password must include an uppercase letter and a number")
        return value


class AuthUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    barbershop_id: Optional[int] = None
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class AuthLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class PublicBarbershopResponse(BaseModel):
    id: int
    name: str
    slug: str
    currency: str
    timezone: str
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
    service_id: int = Field(..., gt=0)
    barber_id: Optional[int] = Field(None, gt=0)
    scheduled_time: datetime
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("client_name")
    @classmethod
    def validate_client_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Client name must contain at least two non-space characters")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if sum(character.isdigit() for character in value) < 6:
            raise ValueError("Phone number must contain at least six digits")
        return value


class WalkInAppointmentRequest(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=6, max_length=30)
    service_id: int = Field(..., gt=0)
    barber_id: Optional[int] = Field(None, gt=0)

    @field_validator("client_name")
    @classmethod
    def validate_walk_in_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe contener al menos dos caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_walk_in_phone(cls, value: str) -> str:
        if sum(character.isdigit() for character in value) < 6:
            raise ValueError("El teléfono debe tener al menos seis dígitos")
        return value


class PublicAvailableSlotResponse(BaseModel):
    availability_id: int
    barber_id: int
    barber_name: str
    slot_start: datetime
    slot_end: datetime


class BarberCreateSlotsRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Formato YYYY-MM-DD")
    start_time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Formato HH:MM")
    end_time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Formato HH:MM")
    slot_minutes: int = Field(30, ge=10, le=180)

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Date must be a valid calendar date in YYYY-MM-DD format") from exc
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("Time must use the HH:MM 24-hour format") from exc
        return value


class BarberAbsenceRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Formato YYYY-MM-DD")
    start_time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Formato HH:MM")
    end_time: str = Field(..., pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$", description="Formato HH:MM")
    reason: Optional[str] = Field(None, max_length=255)

    @field_validator("date")
    @classmethod
    def validate_absence_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Date must be a valid calendar date in YYYY-MM-DD format") from exc
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_absence_time(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("Time must use the HH:MM 24-hour format") from exc
        return value

    @field_validator("reason")
    @classmethod
    def normalize_absence_reason(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value else None


class PublicCreateAppointmentResponse(BaseModel):
    appointment_id: int
    status: str
    tracking_link: str
    message: str


class PublicTrackAppointmentRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=128)


class PublicCancelAppointmentRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=128)
    reason: Optional[str] = Field(None, max_length=500)


class PublicRescheduleAppointmentRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=128)
    availability_id: int = Field(..., gt=0)


class PublicTrackAppointmentItem(BaseModel):
    appointment_id: int
    status: str
    scheduled_time: datetime
    service_type: str
    barber_name: Optional[str] = None
    estimated_duration: int


class PublicTrackAppointmentResponse(BaseModel):
    items: List[PublicTrackAppointmentItem]


class BarberShareLinkResponse(BaseModel):
    barbershop_name: str
    client_link: str
    whatsapp_share_link: str


class AdminTenantItem(BaseModel):
    barbershop_id: int
    barbershop_name: str
    currency: str
    slug: str
    owner_email: Optional[str] = None
    plan: Optional[str] = None
    subscription_status: Optional[str] = None
    active: bool


class AdminTenantsResponse(BaseModel):
    items: List[AdminTenantItem]


class SupportRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=30)
    message: str = Field(..., min_length=5, max_length=5000)
    barbershop_slug: Optional[str] = Field(None, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_support_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value

    @field_validator("message")
    @classmethod
    def validate_support_message(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("El mensaje debe tener al menos cinco caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_support_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = value.strip()
            if value and sum(character.isdigit() for character in value) < 6:
                raise ValueError("El teléfono debe tener al menos seis dígitos")
        return value or None


class AdminUserSupportToggleRequest(BaseModel):
    support_contact_enabled: bool


class AdminStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminSupportTicketStatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(open|in_progress|resolved|closed)$")


class OwnerCreateBarberRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=72)
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and sum(character.isdigit() for character in value) < 6:
            raise ValueError("El teléfono debe tener al menos seis dígitos")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72 or not any(ch.isupper() for ch in value) or not any(ch.isdigit() for ch in value):
            raise ValueError("La contraseña debe tener máximo 72 bytes, una mayúscula y un número")
        return value


class OwnerBarberUpdateRequest(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            digits = "".join(character for character in value if character.isdigit())
            if digits and not 6 <= len(digits) <= 20:
                raise ValueError("El teléfono debe contener entre 6 y 20 dígitos")
            return digits or None
        return None


class OwnerClientCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=6, max_length=20)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_client_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_client_phone(cls, value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) < 6 or len(digits) > 20:
            raise ValueError("El teléfono debe contener entre 6 y 20 dígitos")
        return digits


class OwnerClientUpdateRequest(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_client_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_client_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = value.strip()
            if value and sum(character.isdigit() for character in value) < 6:
                raise ValueError("El teléfono debe tener al menos seis dígitos")
        return value or None

class AdminAffiliateCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    commission_rate: float = Field(0.15, gt=0, le=1)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_affiliate_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value


class AdminCommissionPaymentRequest(BaseModel):
    payment_method: str = Field(..., pattern=r"^(bank_transfer|cash|card|other)$")
    payment_reference: Optional[str] = Field(None, max_length=100)
    payment_notes: Optional[str] = Field(None, max_length=1000)


class BarberCommissionRateRequest(BaseModel):
    rate_basis_points: int = Field(..., ge=0, le=10000)


class BarberCommissionPaymentRequest(BaseModel):
    payment_method: str = Field(..., pattern=r"^(bank_transfer|cash|card|other)$")
    payment_reference: Optional[str] = Field(None, max_length=120)


class AdminSubscriptionPaymentRequest(BaseModel):
    amount_cents: int = Field(..., gt=0, le=2_000_000_000)
    method: str = Field(..., min_length=2, max_length=40)
    reference: Optional[str] = Field(None, max_length=120)
    period_start: datetime
    period_end: datetime

class AdminUserFeatureFlagRequest(BaseModel):
    feature_key: str = Field(..., pattern=r"^branding_auto$")
    enabled: bool


class PlatformSettingsUpdateRequest(BaseModel):
    registrations_enabled: bool
    free_period_days: int = Field(..., ge=1, le=365)


class PlatformSettingsResponse(BaseModel):
    registrations_enabled: bool
    free_period_days: int


class AdminSubscriptionUpdateRequest(BaseModel):
    plan: Optional[str] = Field(None, description="free|basic|professional|enterprise")
    status: Optional[str] = Field(None, description="active|inactive|cancelled|expired|suspended")
    current_period_end: Optional[datetime] = None
class AdminSubscriptionResponse(BaseModel):
    subscription_id: int
    barbershop_id: int
    plan: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    auto_renew: bool = Field(description="Administrative indicator only; automatic charges are not processed or scheduled.")
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
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class AdminUsersResponse(BaseModel):
    items: List[AdminUserItem]
    total: int
    offset: int
    limit: int


class BarberAppointmentStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="pending|confirmed|in_progress|completed|cancelled|no_show")
    reason: Optional[str] = Field(None, max_length=500)


class AppointmentPaymentRequest(BaseModel):
    method: str = Field(..., pattern=r"^(cash|card|transfer|other)$")
    tip_cents: int = Field(0, ge=0, le=10_000_000)


class CashRegisterCloseRequest(BaseModel):
    business_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    declared_cash_cents: int = Field(..., ge=0, le=2_000_000_000)
    notes: Optional[str] = Field(None, max_length=1000)
