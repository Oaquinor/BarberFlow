"""
Application-wide constants and enums.

Centralized location for all constants used across the application.
"""

from enum import Enum


class UserRole(str, Enum):
    """User role types."""
    SUPER_ADMIN = "super_admin"
    BARBERSHOP_OWNER = "barbershop_owner"
    BARBER = "barber"
    CLIENT = "client"


class AppointmentStatus(str, Enum):
    """Appointment status types."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class SubscriptionPlan(str, Enum):
    """Subscription plan types."""
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """Subscription status types."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class PaymentStatus(str, Enum):
    """Payment status types."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class CommissionStatus(str, Enum):
    """Commission status types."""
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    REJECTED = "rejected"


class NotificationType(str, Enum):
    """Notification types."""
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"
    IN_APP = "in_app"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class DayOfWeek(str, Enum):
    """Days of the week."""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class ServiceType(str, Enum):
    """Service types offered."""
    HAIRCUT = "haircut"
    BEARD_TRIM = "beard_trim"
    SHAVE = "shave"
    HAIR_COLOR = "hair_color"
    FACIAL = "facial"
    COMBO = "combo"


# Constants

MAX_APPOINTMENT_DURATION_MINUTES = 120
MIN_APPOINTMENT_DURATION_MINUTES = 15
DEFAULT_APPOINTMENT_DURATION_MINUTES = 30

MAX_DAILY_APPOINTMENTS_PER_BARBER = 20
MAX_ADVANCE_BOOKING_DAYS = 90

DEFAULT_WORKING_HOURS_START = "09:00"
DEFAULT_WORKING_HOURS_END = "18:00"

# Subscription Limits
SUBSCRIPTION_LIMITS = {
    SubscriptionPlan.FREE: {
        "max_barbers": 1,
        "max_appointments_per_month": 50,
        "max_clients": 100,
    },
    SubscriptionPlan.BASIC: {
        "max_barbers": 3,
        "max_appointments_per_month": 200,
        "max_clients": 500,
    },
    SubscriptionPlan.PROFESSIONAL: {
        "max_barbers": 10,
        "max_appointments_per_month": 1000,
        "max_clients": 2000,
    },
    SubscriptionPlan.ENTERPRISE: {
        "max_barbers": None,  # Unlimited
        "max_appointments_per_month": None,  # Unlimited
        "max_clients": None,  # Unlimited
    },
}

# Commission Rates
AFFILIATE_COMMISSION_RATES = {
    "basic": 0.10,  # 10%
    "silver": 0.15,  # 15%
    "gold": 0.20,  # 20%
}

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE = 100
RATE_LIMIT_REQUESTS_PER_HOUR = 1000

# File Upload
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_SIZE_MB = 5
MAX_FILE_SIZE_MB = 10

# Notification Templates
EMAIL_TEMPLATES = {
    "appointment_created": "appointment_created.html",
    "appointment_reminder": "appointment_reminder.html",
    "appointment_cancelled": "appointment_cancelled.html",
    "appointment_rescheduled": "appointment_rescheduled.html",
    "welcome": "welcome.html",
}

# WebSocket Events
WS_EVENT_APPOINTMENT_CREATED = "appointment_created"
WS_EVENT_APPOINTMENT_UPDATED = "appointment_updated"
WS_EVENT_APPOINTMENT_DELETED = "appointment_deleted"
WS_EVENT_BARBER_STATUS_CHANGED = "barber_status_changed"
WS_EVENT_CLIENT_CHECKED_IN = "client_checked_in"
