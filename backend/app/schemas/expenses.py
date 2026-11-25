"""Request contracts for tenant operating expenses."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpenseCategory = Literal[
    "rent",
    "utilities",
    "payroll",
    "commission",
    "supplies",
    "maintenance",
    "marketing",
    "administrative",
    "internet",
    "water",
    "electricity",
    "other",
]


class OperatingExpenseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    idempotency_key: UUID
    category: ExpenseCategory
    description: str = Field(min_length=2, max_length=200)
    amount_cents: int = Field(gt=0, le=2_000_000_000)
    payment_method: Literal["cash", "card", "transfer", "other"]

    @field_validator("description")
    @classmethod
    def require_visible_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Describe el gasto")
        return value
