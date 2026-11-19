"""
Authentication schemas.

DTOs for authentication endpoints.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _validate_bcrypt_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password cannot exceed 72 UTF-8 bytes")
    return value


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, max_length=72, description="User password")

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        return _validate_bcrypt_password(v)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "securepassword123"
            }
        })


class LoginResponse(BaseModel):
    """Login response schema."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field("bearer", description="Token type")
    user: dict = Field(..., description="User information")

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": 1,
                    "email": "user@example.com",
                    "role": "client"
                }
            }
        })


class RegisterRequest(BaseModel):
    """Registration request schema."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, max_length=72, description="User password")
    first_name: str = Field(..., min_length=2, max_length=50, description="First name")
    last_name: str = Field(..., min_length=2, max_length=50, description="Last name")
    phone: str = Field(..., description="Phone number")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return _validate_bcrypt_password(v)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "email": "newuser@example.com",
                "password": "SecurePass123",
                "first_name": "John",
                "last_name": "Doe",
                "phone": "+1234567890"
            }
        })


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str = Field(..., description="Refresh token")


class RefreshTokenResponse(BaseModel):
    """Refresh token response schema."""
    access_token: str = Field(..., description="New JWT access token")
    refresh_token: str = Field(..., description="Rotated JWT refresh token")
    token_type: str = Field("bearer", description="Token type")


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=72, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return _validate_bcrypt_password(v)


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: EmailStr = Field(..., description="User email")


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema."""
    token: str = Field(..., min_length=32, max_length=128, description="Reset token")
    new_password: str = Field(..., min_length=8, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return _validate_bcrypt_password(v)
