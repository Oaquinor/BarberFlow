"""Tenant-scoped retail and consumable products."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from app.models.base import BaseModel


class InventoryProduct(BaseModel):
    __tablename__ = "inventory_products"
    __table_args__ = (
        UniqueConstraint("barbershop_id", "barcode", name="uq_inventory_shop_barcode"),
        CheckConstraint("unit_cost_cents >= 0", name="ck_inventory_product_cost_nonnegative"),
        CheckConstraint("unit_price_cents >= 0", name="ck_inventory_product_price_nonnegative"),
        CheckConstraint("stock_quantity >= 0", name="ck_inventory_product_stock_nonnegative"),
        CheckConstraint("stock_minimum >= 0", name="ck_inventory_product_minimum_nonnegative"),
        Index("ix_inventory_shop_active_name", "barbershop_id", "is_active", "name"),
    )

    barbershop_id = Column(Integer, ForeignKey("barbershops.id"), nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(String(1000), nullable=True)
    category = Column(String(80), nullable=False, default="General")
    barcode = Column(String(80), nullable=True)
    unit = Column(String(30), nullable=False, default="unidad")
    unit_cost_cents = Column(Integer, nullable=False, default=0)
    unit_price_cents = Column(Integer, nullable=False, default=0)
    stock_quantity = Column(Integer, nullable=False, default=0)
    stock_minimum = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
