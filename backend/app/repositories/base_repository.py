"""
Base repository with common CRUD operations.

All repositories should inherit from this class.
"""

from typing import Generic, TypeVar, Type, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """
    Base repository with generic CRUD operations.

    This class provides common database operations that can be reused
    by all specific repositories.
    """

    def __init__(self, model: Type[ModelType], db: Session):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            db: Database session
        """
        self.model = model
        self.db = db

    def create(self, **kwargs) -> ModelType:
        """
        Create new record.

        Args:
            **kwargs: Field values for new record

        Returns:
            Created model instance
        """
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def get_by_id(self, record_id: int) -> Optional[ModelType]:
        """
        Get record by ID.

        Args:
            record_id: Record ID

        Returns:
            Model instance or None
        """
        result = self.db.execute(
            select(self.model).where(
                self.model.id == record_id,
                self.model.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False
    ) -> List[ModelType]:
        """
        Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_deleted: Whether to include soft-deleted records

        Returns:
            List of model instances
        """
        query = select(self.model)

        if not include_deleted:
            query = query.where(self.model.is_deleted == False)

        query = query.offset(skip).limit(limit)

        result = self.db.execute(query)
        return list(result.scalars().all())

    def update(self, record_id: int, **kwargs) -> Optional[ModelType]:
        """
        Update record.

        Args:
            record_id: Record ID to update
            **kwargs: Fields to update

        Returns:
            Updated model instance or None
        """
        instance = self.get_by_id(record_id)
        if not instance:
            return None

        for key, value in kwargs.items():
            setattr(instance, key, value)

        self.db.commit()
        self.db.refresh(instance)
        return instance

    def delete(self, record_id: int, soft: bool = True) -> bool:
        """
        Delete record (soft or hard delete).

        Args:
            record_id: Record ID to delete
            soft: If True, performs soft delete; if False, hard delete

        Returns:
            True if deleted, False if not found
        """
        instance = self.get_by_id(record_id)
        if not instance:
            return False

        if soft:
            instance.soft_delete()
            self.db.commit()
        else:
            self.db.delete(instance)
            self.db.commit()

        return True

    def count(self, include_deleted: bool = False) -> int:
        """
        Count total records.

        Args:
            include_deleted: Whether to include soft-deleted records

        Returns:
            Total count
        """
        query = select(self.model)

        if not include_deleted:
            query = query.where(self.model.is_deleted == False)

        result = self.db.execute(query)
        return len(list(result.scalars().all()))

    def exists(self, record_id: int) -> bool:
        """
        Check if record exists.

        Args:
            record_id: Record ID to check

        Returns:
            True if exists, False otherwise
        """
        instance = self.get_by_id(record_id)
        return instance is not None
