"""
Services Management API endpoints.

Handles CRUD for barbershop services.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.services import ServiceManagementService
from app.core.security import get_current_user
from app.models import User

router = APIRouter(prefix="/services", tags=["Services"])


class CreateServiceRequest(BaseModel):
    """Request to create a new service."""
    name: str
    description: Optional[str] = None
    duration_minutes: int
    price: int  # in cents
    category: str
    icon: Optional[str] = None


class UpdateServiceRequest(BaseModel):
    """Request to update a service."""
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: Optional[int] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_service(
    request: CreateServiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new service for the barbershop."""
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )

    try:
        service = ServiceManagementService.create_service(
            db=db,
            barbershop_id=current_user.barbershop_id,
            name=request.name,
            description=request.description,
            duration_minutes=request.duration_minutes,
            price=request.price,
            category=request.category,
            icon=request.icon
        )

        return {
            "id": service.id,
            "name": service.name,
            "description": service.description,
            "duration_minutes": service.duration_minutes,
            "price": service.price,
            "price_formatted": service.price_formatted,
            "category": service.category,
            "icon": service.icon,
            "is_active": service.is_active
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/")
def get_services(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all active services for the barbershop."""
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )

    try:
        if category:
            services = ServiceManagementService.get_services_by_category(
                db=db,
                barbershop_id=current_user.barbershop_id,
                category=category
            )
        else:
            services = ServiceManagementService.get_active_services(
                db=db,
                barbershop_id=current_user.barbershop_id
            )

        return {
            "total": len(services),
            "services": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "duration_minutes": s.duration_minutes,
                    "price": s.price,
                    "price_formatted": s.price_formatted,
                    "category": s.category,
                    "icon": s.icon,
                    "is_active": s.is_active,
                    "display_order": s.display_order
                }
                for s in services
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{service_id}")
def get_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific service by ID."""
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )

    service = ServiceManagementService.get_service_by_id(
        db=db,
        service_id=service_id,
        barbershop_id=current_user.barbershop_id
    )

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price": service.price,
        "price_formatted": service.price_formatted,
        "category": service.category,
        "icon": service.icon,
        "is_active": service.is_active,
        "display_order": service.display_order
    }


@router.put("/{service_id}")
def update_service(
    service_id: int,
    request: UpdateServiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a service."""
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )

    try:
        service = ServiceManagementService.update_service(
            db=db,
            service_id=service_id,
            barbershop_id=current_user.barbershop_id,
            **request.dict(exclude_unset=True)
        )

        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )

        return {
            "id": service.id,
            "name": service.name,
            "description": service.description,
            "duration_minutes": service.duration_minutes,
            "price": service.price,
            "price_formatted": service.price_formatted,
            "category": service.category,
            "icon": service.icon,
            "is_active": service.is_active,
            "display_order": service.display_order
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete (soft delete) a service."""
    if not current_user.barbershop_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a barbershop"
        )

    success = ServiceManagementService.delete_service(
        db=db,
        service_id=service_id,
        barbershop_id=current_user.barbershop_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    return None
