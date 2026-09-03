"""Schemas package."""

from app.schemas.common import StandardResponse, PaginatedResponse, MessageResponse
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest

__all__ = [
    "StandardResponse",
    "PaginatedResponse",
    "MessageResponse",
    "LoginRequest",
    "LoginResponse",
    "RegisterRequest",
]
