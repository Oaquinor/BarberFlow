"""
Common schemas used across the application.

These schemas provide standardized request/response formats.
"""

from typing import Any, Generic, List, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


class StandardResponse(BaseModel):
    """
    Standard API response format.

    All API endpoints should return this format.
    """
    success: bool = Field(..., description="Indicates if operation was successful")
    message: str = Field(..., description="Human-readable message")
    data: Any = Field(None, description="Response data")
    errors: List[str] = Field(default_factory=list, description="List of errors if any")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"id": 1, "name": "Example"},
                "errors": []
            }
        }


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated response format.

    Used for list endpoints with pagination.
    """
    items: List[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    size: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total": 100,
                "page": 1,
                "size": 20,
                "pages": 5
            }
        }


class PaginationParams(BaseModel):
    """Pagination query parameters."""
    page: int = Field(1, ge=1, description="Page number")
    size: int = Field(20, ge=1, le=100, description="Items per page")


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str = Field(..., description="Response message")


class IDResponse(BaseModel):
    """Response with just an ID."""
    id: int = Field(..., description="Resource ID")


class SuccessResponse(BaseModel):
    """Simple success indicator."""
    success: bool = Field(..., description="Operation success")
