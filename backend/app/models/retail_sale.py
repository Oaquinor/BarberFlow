"""Immutable, appointment-free retail sale and line snapshots."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class RetailSale(BaseModel):
    __tablename__ = "retail_sales"
    __table_args__ = (
        UniqueConstraint("barbershop_id", "request_key_hash", name="uq_retail_sale_shop_request"),
        CheckConstraint("subtotal_cents > 0", name="ck_retail_sale_subtotal_positive"),
        CheckConstraint(
            "total_cents = subtotal_cents", name="ck_retail_sale_total_matches_subtotal"
        ),
        CheckConstraint("cost_total_cents >= 0", name="ck_retail_sale_cost_nonnegative"),
        Index("ix_retail_sale_shop_sold", "barbershop_id", "sold_at"),
        Index("ix_retail_sale_shop_method_sold", "barbershop_id", "payment_method", "sold_at"),
    )

    barbershop_id = Column(
        Integer, ForeignKey("barbershops.id", ondelete="RESTRICT"), nullable=False
    )
    sold_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    payment_method = Column(String(20), nullable=False)
    currency = Column(String(3), nullable=False)
    subtotal_cents = Column(Integer, nullable=False)
    total_cents = Column(Integer, nullable=False)
    cost_total_cents = Column(Integer, nullable=False)
    sold_at = Column(DateTime, nullable=False)
    request_key_hash = Column(String(64), nullable=False)
    request_payload_hash = Column(String(64), nullable=False)
    lines = relationship("RetailSaleLine", order_by="RetailSaleLine.id", lazy="selectin")


class RetailSaleLine(BaseModel):
    __tablename__ = "retail_sale_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_retail_sale_line_quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="ck_retail_sale_line_price_nonnegative"),
        CheckConstraint("unit_cost_cents >= 0", name="ck_retail_sale_line_cost_nonnegative"),
        CheckConstraint("line_total_cents >= 0", name="ck_retail_sale_line_total_nonnegative"),
        Index("ix_retail_sale_line_product", "product_id"),
    )

    sale_id = Column(Integer, ForeignKey("retail_sales.id", ondelete="RESTRICT"), nullable=False)
    product_id = Column(
        Integer, ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False
    )
    product_name_snapshot = Column(String(120), nullable=False)
    barcode_snapshot = Column(String(80), nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price_cents = Column(Integer, nullable=False)
    unit_cost_cents = Column(Integer, nullable=False)
    line_total_cents = Column(Integer, nullable=False)
