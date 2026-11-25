"""Customer account API contracts."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class ClientAccountRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=72)
    first_name: str = Field(..., min_length=2, max_length=100)
    last_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=6, max_length=30)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede exceder 72 bytes")
        if not any(char.isupper() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("La contraseña debe incluir una mayúscula y un número")
        return value

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        digits = "".join(char for char in value if char.isdigit())
        if not 6 <= len(digits) <= 20:
            raise ValueError("El teléfono debe contener entre 6 y 20 dígitos")
        return digits


class ClientAccountVerifyRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=128)


class ClientAccountResendRequest(BaseModel):
    email: EmailStr


class ClientAppointmentClaimRequest(BaseModel):
    tracking_token: str = Field(..., min_length=32, max_length=128)
