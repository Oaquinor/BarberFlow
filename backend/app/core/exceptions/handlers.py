"""
Global exception handlers.

Handles all exceptions and returns standardized error responses.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.exceptions.base import (
    BaseAppException,
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
    BusinessLogicError,
    ExternalServiceError,
)
from app.core.logging import get_logger
from app.schemas.common import StandardResponse

logger = get_logger(__name__)


async def base_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    """Handle custom base exceptions."""
    logger.error(f"Application error: {exc.message}", extra={"detail": exc.detail})

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=StandardResponse(
            success=False,
            message=exc.message,
            errors=[exc.message]
        ).dict()
    )


async def authentication_exception_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    """Handle authentication exceptions."""
    logger.warning(f"Authentication error: {exc.message}")

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=StandardResponse(
            success=False,
            message="Authentication failed",
            errors=[exc.message]
        ).dict()
    )


async def authorization_exception_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    """Handle authorization exceptions."""
    logger.warning(f"Authorization error: {exc.message}")

    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=StandardResponse(
            success=False,
            message="Access denied",
            errors=[exc.message]
        ).dict()
    )


async def not_found_exception_handler(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    """Handle resource not found exceptions."""
    logger.info(f"Resource not found: {exc.message}")

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=StandardResponse(
            success=False,
            message="Resource not found",
            errors=[exc.message]
        ).dict()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle pydantic validation exceptions."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append(f"{field}: {message}")

    logger.warning(f"Validation error: {errors}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=StandardResponse(
            success=False,
            message="Validation failed",
            errors=errors
        ).dict()
    )


async def business_logic_exception_handler(request: Request, exc: BusinessLogicError) -> JSONResponse:
    """Handle business logic exceptions."""
    logger.warning(f"Business logic error: {exc.message}")

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=StandardResponse(
            success=False,
            message=exc.message,
            errors=[exc.message]
        ).dict()
    )


async def external_service_exception_handler(request: Request, exc: ExternalServiceError) -> JSONResponse:
    """Handle external service exceptions."""
    logger.error(f"External service error: {exc.message}", extra={"detail": exc.detail})

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=StandardResponse(
            success=False,
            message="External service temporarily unavailable",
            errors=[exc.message]
        ).dict()
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other unhandled exceptions."""
    logger.exception(f"Unhandled exception: {str(exc)}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=StandardResponse(
            success=False,
            message="An unexpected error occurred",
            errors=["Internal server error"]
        ).dict()
    )


def register_exception_handlers(app):
    """Register all exception handlers with FastAPI app."""
    app.add_exception_handler(BaseAppException, base_exception_handler)
    app.add_exception_handler(AuthenticationError, authentication_exception_handler)
    app.add_exception_handler(AuthorizationError, authorization_exception_handler)
    app.add_exception_handler(ResourceNotFoundError, not_found_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(BusinessLogicError, business_logic_exception_handler)
    app.add_exception_handler(ExternalServiceError, external_service_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
