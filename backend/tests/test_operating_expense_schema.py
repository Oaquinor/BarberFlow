"""Validation for financial expense requests."""

import pytest
from pydantic import ValidationError

from app.schemas.expenses import OperatingExpenseCreate


def test_operating_expense_accepts_cents_and_rejects_invalid_money_or_fields():
    common = {
        "idempotency_key": "6b9683ba-36a1-4c36-a455-ffcd60426c9f",
        "category": "supplies",
        "description": "Compra de navajas",
        "amount_cents": 2500,
        "payment_method": "cash",
    }
    expense = OperatingExpenseCreate(**common)
    assert expense.amount_cents == 2500
    with pytest.raises(ValidationError):
        OperatingExpenseCreate(**{**common, "amount_cents": -1})
    with pytest.raises(ValidationError):
        OperatingExpenseCreate(**{**common, "amount_cents": 0})
    with pytest.raises(ValidationError):
        OperatingExpenseCreate(**{**common, "tenant_id": 42})
