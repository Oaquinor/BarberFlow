"""Validation for the public booking waitlist and owner operations."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PublicWaitlistRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    client_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=30)
    service_id: int = Field(gt=0)
    idempotency_key: UUID
    barber_id: int | None = Field(default=None, gt=0)
    preferred_date_start: date | None = None
    preferred_date_end: date | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("client_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if len(value.strip()) < 2:
            raise ValueError("El nombre debe contener al menos dos caracteres")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if sum(character.isdigit() for character in value) < 6:
            raise ValueError("El teléfono debe contener al menos seis dígitos")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @model_validator(mode="after")
    def validate_preferred_dates(self):
        if (
            self.preferred_date_start
            and self.preferred_date_end
            and self.preferred_date_end < self.preferred_date_start
        ):
            raise ValueError("La fecha final debe ser igual o posterior a la fecha inicial")
        return self


class WaitlistStatusUpdate(BaseModel):
    status: Literal["new", "contacted", "closed"]
