"""Compatibility exports for dependencies used by API route modules."""

from app.core.security.dependencies import (
    CurrentUser,
    DatabaseSession,
    OptionalUser,
    get_current_active_user,
    get_current_barber,
    get_current_owner,
    get_current_user,
    get_optional_user,
)

__all__ = [
    "CurrentUser",
    "DatabaseSession",
    "OptionalUser",
    "get_current_active_user",
    "get_current_barber",
    "get_current_owner",
    "get_current_user",
    "get_optional_user",
]
