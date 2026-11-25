"""Input contracts for private customer style records."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StylePassportFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    haircut_type: str | None = Field(default=None, max_length=120)
    fade_style: str | None = Field(default=None, max_length=120)
    top_length: str | None = Field(default=None, max_length=120)
    sides_length: str | None = Field(default=None, max_length=120)
    beard_style: str | None = Field(default=None, max_length=120)
    products_used: str | None = Field(default=None, max_length=300)
    preferences: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "haircut_type",
        "fade_style",
        "top_length",
        "sides_length",
        "beard_style",
        "products_used",
        "preferences",
    )
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        cleaned = value.strip() if value else None
        return cleaned or None


class StylePassportCreate(StylePassportFields):
    appointment_id: int = Field(gt=0)
    share_with_shop: bool = False


class StylePassportUpdate(StylePassportFields):
    haircut_type: str | None = Field(default=None, max_length=120)
    fade_style: str | None = Field(default=None, max_length=120)
    top_length: str | None = Field(default=None, max_length=120)
    sides_length: str | None = Field(default=None, max_length=120)
    beard_style: str | None = Field(default=None, max_length=120)
    products_used: str | None = Field(default=None, max_length=300)
    preferences: str | None = Field(default=None, max_length=2000)
    share_with_shop: bool | None = None

    @field_validator("share_with_shop", mode="before")
    @classmethod
    def require_boolean_consent(cls, value):
        if value is None:
            raise ValueError("Indica si autorizas o retiras el acceso de la barbería")
        return value


class StylePassportStaffUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barber_notes: str | None = Field(default=None, max_length=2000)
    recommendations: str | None = Field(default=None, max_length=2000)

    @field_validator("barber_notes", "recommendations")
    @classmethod
    def trim_staff_text(cls, value: str | None) -> str | None:
        cleaned = value.strip() if value else None
        return cleaned or None


StylePassportPhotoKind = Literal["reference", "result"]
