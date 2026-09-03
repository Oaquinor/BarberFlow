"""
Custom exceptions for the application.

All custom exceptions should inherit from BaseAppException.
"""

from typing import Any


class BaseAppException(Exception):
    """Base exception class for all custom exceptions."""

    def __init__(self, message: str, detail: Any = None):
        self.message = message
        self.detail = detail
        super().__init__(self.message)


# Authentication Exceptions

class AuthenticationError(BaseAppException):
    """Raised when authentication fails."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when token has expired."""
    pass


class InvalidTokenError(AuthenticationError):
    """Raised when token is invalid."""
    pass


# Authorization Exceptions

class AuthorizationError(BaseAppException):
    """Raised when user lacks permissions."""
    pass


class InsufficientPermissionsError(AuthorizationError):
    """Raised when user doesn't have required permissions."""
    pass


# Resource Exceptions

class ResourceNotFoundError(BaseAppException):
    """Raised when a resource is not found."""
    pass


class UserNotFoundError(ResourceNotFoundError):
    """Raised when user is not found."""
    pass


class AppointmentNotFoundError(ResourceNotFoundError):
    """Raised when appointment is not found."""
    pass


class ClientNotFoundError(ResourceNotFoundError):
    """Raised when client is not found."""
    pass


class BarberNotFoundError(ResourceNotFoundError):
    """Raised when barber is not found."""
    pass


class BarbershopNotFoundError(ResourceNotFoundError):
    """Raised when barbershop is not found."""
    pass


# Validation Exceptions

class ValidationError(BaseAppException):
    """Raised when validation fails."""
    pass


class InvalidTimeSlotError(ValidationError):
    """Raised when time slot is invalid or unavailable."""
    pass


class InvalidDateRangeError(ValidationError):
    """Raised when date range is invalid."""
    pass


class DuplicateResourceError(ValidationError):
    """Raised when trying to create duplicate resource."""
    pass


# Business Logic Exceptions

class BusinessLogicError(BaseAppException):
    """Raised when business logic fails."""
    pass


class AppointmentConflictError(BusinessLogicError):
    """Raised when appointment conflicts with existing one."""
    pass


class BarberUnavailableError(BusinessLogicError):
    """Raised when barber is not available."""
    pass


class SubscriptionExpiredError(BusinessLogicError):
    """Raised when subscription has expired."""
    pass


class SubscriptionLimitReachedError(BusinessLogicError):
    """Raised when subscription limit is reached."""
    pass


# External Service Exceptions

class ExternalServiceError(BaseAppException):
    """Raised when external service fails."""
    pass


class EmailServiceError(ExternalServiceError):
    """Raised when email service fails."""
    pass


class PushNotificationError(ExternalServiceError):
    """Raised when push notification fails."""
    pass


class PaymentServiceError(ExternalServiceError):
    """Raised when payment service fails."""
    pass
