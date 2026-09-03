"""
Service Management Service.

Handles CRUD operations for barbershop services.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import Service


class ServiceManagementService:
    """Service for managing barbershop services."""

    @staticmethod
    def create_service(
        db: Session,
        barbershop_id: int,
        name: str,
        description: Optional[str],
        duration_minutes: int,
        price: int,  # in cents
        category: str,
        icon: Optional[str] = None
    ) -> Service:
        """Create a new service."""
        service = Service(
            barbershop_id=barbershop_id,
            name=name,
            description=description,
            duration_minutes=duration_minutes,
            price=price,
            category=category,
            icon=icon
        )

        db.add(service)
        db.commit()
        db.refresh(service)

        return service

    @staticmethod
    def get_active_services(
        db: Session,
        barbershop_id: int
    ) -> List[Service]:
        """Get all active services for a barbershop."""
        return db.query(Service).filter(
            and_(
                Service.barbershop_id == barbershop_id,
                Service.is_active == True,
                Service.is_deleted == False
            )
        ).order_by(Service.display_order, Service.name).all()

    @staticmethod
    def get_service_by_id(
        db: Session,
        service_id: int,
        barbershop_id: int
    ) -> Optional[Service]:
        """Get a specific service by ID."""
        return db.query(Service).filter(
            and_(
                Service.id == service_id,
                Service.barbershop_id == barbershop_id,
                Service.is_deleted == False
            )
        ).first()

    @staticmethod
    def update_service(
        db: Session,
        service_id: int,
        barbershop_id: int,
        **kwargs
    ) -> Optional[Service]:
        """Update a service."""
        service = ServiceManagementService.get_service_by_id(db, service_id, barbershop_id)

        if not service:
            return None

        # Update allowed fields
        allowed_fields = [
            'name', 'description', 'duration_minutes', 
            'price', 'category', 'icon', 'is_active', 'display_order'
        ]

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(service, key, value)

        db.commit()
        db.refresh(service)

        return service

    @staticmethod
    def delete_service(
        db: Session,
        service_id: int,
        barbershop_id: int
    ) -> bool:
        """Soft delete a service."""
        service = ServiceManagementService.get_service_by_id(db, service_id, barbershop_id)

        if not service:
            return False

        service.is_deleted = True
        db.commit()

        return True

    @staticmethod
    def get_services_by_category(
        db: Session,
        barbershop_id: int,
        category: str
    ) -> List[Service]:
        """Get services filtered by category."""
        return db.query(Service).filter(
            and_(
                Service.barbershop_id == barbershop_id,
                Service.category == category,
                Service.is_active == True,
                Service.is_deleted == False
            )
        ).order_by(Service.display_order, Service.name).all()
