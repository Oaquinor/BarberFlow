"""Persistence for private, consent-controlled style records."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.models.base import BaseModel


class StylePassportEntry(BaseModel):
    """A customer's private, consent-controlled record of a completed cut."""

    __tablename__ = "style_passport_entries"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_style_passport_appointment"),
        Index(
            "ix_style_passport_account_shop_active",
            "account_user_id",
            "barbershop_id",
            "is_deleted",
        ),
        Index(
            "ix_style_passport_shop_share_active",
            "barbershop_id",
            "share_with_shop",
            "is_deleted",
        ),
    )

    account_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    barbershop_id = Column(
        Integer,
        ForeignKey("barbershops.id", ondelete="RESTRICT"),
        nullable=False,
    )
    appointment_id = Column(
        Integer,
        ForeignKey("appointments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    haircut_type = Column(String(120), nullable=True)
    fade_style = Column(String(120), nullable=True)
    top_length = Column(String(120), nullable=True)
    sides_length = Column(String(120), nullable=True)
    beard_style = Column(String(120), nullable=True)
    products_used = Column(String(300), nullable=True)
    preferences = Column(Text, nullable=True)
    barber_notes = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    share_with_shop = Column(Boolean, nullable=False, default=False, server_default="0")
    share_consent_updated_at = Column(DateTime, nullable=True)


class StylePassportPhoto(BaseModel):
    """Sanitized private image metadata; bytes are stored outside public assets."""

    __tablename__ = "style_passport_photos"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="ck_style_passport_photo_size_positive"),
        CheckConstraint("byte_size <= 5242880", name="ck_style_passport_photo_size_limit"),
        CheckConstraint(
            "photo_kind IN ('reference','result')",
            name="ck_style_passport_photo_kind",
        ),
        UniqueConstraint("storage_key", name="uq_style_passport_photo_storage_key"),
        Index("ix_style_passport_photo_entry", "entry_id", "is_deleted"),
    )

    entry_id = Column(
        Integer,
        ForeignKey("style_passport_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    photo_kind = Column(String(20), nullable=False)
    storage_key = Column(String(64), nullable=False)
    content_type = Column(String(50), nullable=False, default="image/jpeg")
    byte_size = Column(Integer, nullable=False)
