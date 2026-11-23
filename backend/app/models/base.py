"""
Base model with common fields.

All models should inherit from this base class.
"""

from sqlalchemy import Column, Integer, DateTime, Boolean

from app.core.database import Base
from app.utils.datetime import utc_now_naive


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class SoftDeleteMixin:
    """Mixin for soft delete functionality."""

    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)


class BaseModel(Base, TimestampMixin, SoftDeleteMixin):
    """
    Base model with common fields.

    Provides:
    - Primary key (id)
    - Timestamps (created_at, updated_at)
    - Soft delete (is_deleted, deleted_at)
    """

    __abstract__ = True

    # A primary key is indexed by MySQL already; an extra index only bloats
    # every table and drifts from the migration-managed schema.
    id = Column(Integer, primary_key=True)

    def soft_delete(self) -> None:
        """Mark record as deleted."""
        self.is_deleted = True
        self.deleted_at = utc_now_naive()

    def restore(self) -> None:
        """Restore soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
