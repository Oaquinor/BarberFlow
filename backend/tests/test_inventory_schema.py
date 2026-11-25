"""Inventory request rules that do not need a database connection."""

import pytest
from pydantic import ValidationError

from app.schemas.inventory import (
    InventoryMovementCreate,
    InventoryProductCreate,
    InventorySaleCreate,
)


def test_product_defaults_and_normalizes_empty_barcode():
    product = InventoryProductCreate(name="  Pomada  ", barcode="   ")
    assert product.name == "Pomada"
    assert product.barcode is None
    assert product.unit_cost_cents == 0
    assert product.stock_minimum == 0


@pytest.mark.parametrize("quantity", [0, 2_000_001, -2_000_001])
def test_movement_rejects_zero_or_unbounded_quantities(quantity: int):
    with pytest.raises(ValidationError):
        InventoryMovementCreate(
            idempotency_key="efdfbe07-d601-4b46-8ca5-269ac894322c",
            quantity_delta=quantity,
            reason="adjustment",
        )


def test_movement_rejects_unknown_reason_and_negative_cost():
    common = {"idempotency_key": "efdfbe07-d601-4b46-8ca5-269ac894322c", "quantity_delta": 1}
    with pytest.raises(ValidationError):
        InventoryMovementCreate(**common, reason="sale")
    with pytest.raises(ValidationError):
        InventoryMovementCreate(**common, reason="receipt", unit_cost_cents=-1)


def test_retail_sale_requires_unique_positive_items_and_rejects_client_prices():
    sale = InventorySaleCreate(
        idempotency_key="efdfbe07-d601-4b46-8ca5-269ac894322c",
        method="cash",
        items=[{"product_id": 4, "quantity": 2}, {"product_id": 9, "quantity": 1}],
    )
    assert [item.product_id for item in sale.items] == [4, 9]
    with pytest.raises(ValidationError):
        InventorySaleCreate(
            idempotency_key="efdfbe07-d601-4b46-8ca5-269ac894322c",
            method="cash",
            items=[{"product_id": 4, "quantity": 1}, {"product_id": 4, "quantity": 2}],
        )
    with pytest.raises(ValidationError):
        InventorySaleCreate(
            idempotency_key="efdfbe07-d601-4b46-8ca5-269ac894322c",
            method="cash",
            items=[{"product_id": 4, "quantity": 1, "unit_price_cents": 1}],
        )
