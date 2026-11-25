"""Append-only stock ledger for inventory products."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from app.models.base import BaseModel


class InventoryMovement(BaseModel):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        UniqueConstraint("barbershop_id", "request_key_hash", name="uq_inventory_shop_request_key"),
        CheckConstraint("quantity_delta != 0", name="ck_inventory_movement_nonzero"),
        CheckConstraint("unit_cost_cents >= 0", name="ck_inventory_movement_cost_nonnegative"),
        Index("ix_inventory_movement_shop_created", "barbershop_id", "created_at"),
        Index("ix_inventory_movement_product_created", "product_id", "created_at"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("inventory_products.id"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quantity_delta = Column(Integer, nullable=False)
    unit_cost_cents = Column(Integer, nullable=False)
    reason = Column(String(30), nullable=False)
    note = Column(String(500), nullable=True)
    request_key_hash = Column(String(64), nullable=False)
    request_payload_hash = Column(String(64), nullable=False)
