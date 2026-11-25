"""Validated requests for the owner inventory module."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category: str = Field(default="General", min_length=2, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    unit: str = Field(default="unidad", min_length=1, max_length=30)
    unit_cost_cents: int = Field(default=0, ge=0, le=2_000_000_000)
    unit_price_cents: int = Field(default=0, ge=0, le=2_000_000_000)
    stock_minimum: int = Field(default=0, ge=0, le=2_000_000)

    @field_validator("barcode")
    @classmethod
    def normalize_barcode(cls, value: str | None) -> str | None:
        return value or None


class InventoryProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    barcode: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    unit_cost_cents: int | None = Field(default=None, ge=0, le=2_000_000_000)
    unit_price_cents: int | None = Field(default=None, ge=0, le=2_000_000_000)
    stock_minimum: int | None = Field(default=None, ge=0, le=2_000_000)
    is_active: bool | None = None

    @field_validator("barcode")
    @classmethod
    def normalize_barcode(cls, value: str | None) -> str | None:
        return value or None


class InventoryMovementCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    idempotency_key: UUID
    quantity_delta: int = Field(ge=-2_000_000, le=2_000_000)
    reason: Literal["receipt", "return", "consumption", "adjustment"]
    unit_cost_cents: int | None = Field(default=None, ge=0, le=2_000_000_000)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("quantity_delta")
    @classmethod
    def movement_must_change_stock(cls, value: int) -> int:
        if value == 0:
            raise ValueError("La cantidad del movimiento no puede ser cero")
        return value


class InventorySaleLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100_000)


class InventorySaleCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    idempotency_key: UUID
    method: Literal["cash", "card", "transfer", "other"]
    items: list[InventorySaleLineRequest] = Field(min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def reject_duplicate_products(cls, items: list[InventorySaleLineRequest]):
        product_ids = [item.product_id for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Combina cada producto en una sola línea")
        return items
