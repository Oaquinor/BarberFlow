"""Append-only operating expenses recorded by a barber shop owner."""

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

from app.models.base import BaseModel


class OperatingExpense(BaseModel):
    __tablename__ = "operating_expenses"
    __table_args__ = (
        UniqueConstraint(
            "barbershop_id",
            "request_key_hash",
            name="uq_expense_shop_request",
        ),
        Index("ix_expense_shop_spent", "barbershop_id", "spent_at"),
        Index(
            "ix_expense_shop_category_spent",
            "barbershop_id",
            "category",
            "spent_at",
        ),
        CheckConstraint("amount_cents > 0", name="ck_expense_amount_positive"),
        CheckConstraint(
            "category IN ('rent','utilities','payroll','commission',"
            "'supplies',"
            "'maintenance','marketing','administrative','internet','water',"
            "'electricity','other')",
            name="ck_operating_expense_category",
        ),
        CheckConstraint(
            "payment_method IN ('cash','card','transfer','other')",
            name="ck_operating_expense_method",
        ),
    )

    barbershop_id = Column(
        Integer,
        ForeignKey("barbershops.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    category = Column(String(40), nullable=False)
    description = Column(String(200), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    payment_method = Column(String(20), nullable=False)
    currency = Column(String(3), nullable=False)
    spent_at = Column(DateTime, nullable=False)
    request_key_hash = Column(String(64), nullable=False)
    request_payload_hash = Column(String(64), nullable=False)
