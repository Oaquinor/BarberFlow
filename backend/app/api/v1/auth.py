"""
Authentication endpoints.

Handles login, registration, token refresh, etc.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DatabaseSession, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    PasswordChangeRequest
)
from app.schemas.common import StandardResponse, MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="Authenticate user and return JWT tokens"
)
async def login(
    credentials: LoginRequest,
    db: DatabaseSession
) -> LoginResponse:
    """
    Login endpoint.

    Authenticates user credentials and returns access and refresh tokens.
    """
    service = AuthService(db)
    result = await service.login(credentials)

    return LoginResponse(**result)


@router.post(
    "/register",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User registration",
    description="Register a new user account"
)
async def register(
    data: RegisterRequest,
    db: DatabaseSession
) -> StandardResponse:
    """
    Registration endpoint.

    Creates a new user account with client role by default.
    """
    service = AuthService(db)
    user = await service.register(data)

    return StandardResponse(
        success=True,
        message="User registered successfully",
        data={
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Get new access token using refresh token"
)
async def refresh_token(
    data: RefreshTokenRequest,
    db: DatabaseSession
) -> RefreshTokenResponse:
    """
    Refresh token endpoint.

    Generates a new access token from a valid refresh token.
    """
    service = AuthService(db)
    access_token = await service.refresh_access_token(data.refresh_token)

    return RefreshTokenResponse(
        access_token=access_token,
        token_type="bearer"
    )


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Change user password"
)
async def change_password(
    data: PasswordChangeRequest,
    current_user: CurrentUser,
    db: DatabaseSession
) -> MessageResponse:
    """
    Change password endpoint.

    Allows authenticated users to change their password.
    """
    service = AuthService(db)
    await service.change_password(
        user_id=current_user.id,
        current_password=data.current_password,
        new_password=data.new_password
    )

    return MessageResponse(message="Password changed successfully")


@router.get(
    "/me",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user",
    description="Get authenticated user information"
)
async def get_current_user_info(
    current_user: CurrentUser
) -> StandardResponse:
    """
    Get current user endpoint.

    Returns information about the authenticated user.
    """
    return StandardResponse(
        success=True,
        message="User information retrieved",
        data={
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "barbershop_id": current_user.barbershop_id,
            "is_active": current_user.is_active,
            "is_verified": current_user.is_verified
        }
    )
