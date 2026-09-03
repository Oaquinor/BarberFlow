"""
Authentication service.

Handles user authentication business logic.
"""

from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.models.user import User
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token
)
from app.core.exceptions import (
    InvalidCredentialsError,
    DuplicateResourceError,
    InvalidTokenError
)
from app.core.constants import UserRole


class AuthService:
    """Handles authentication business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repository = UserRepository(db)

    async def login(self, credentials: LoginRequest) -> Dict[str, Any]:
        """
        Authenticate user and return tokens.

        Args:
            credentials: Login credentials

        Returns:
            Dictionary with tokens and user info

        Raises:
            InvalidCredentialsError: If credentials are invalid
        """
        # Get user by email
        user = await self.user_repository.get_by_email(credentials.email)

        if not user:
            raise InvalidCredentialsError("Invalid email or password")

        # Verify password
        if not verify_password(credentials.password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password")

        # Check if user is active
        if not user.is_active:
            raise InvalidCredentialsError("Account is inactive")

        # Create tokens
        access_token = create_access_token({"sub": str(user.id), "role": user.role})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "barbershop_id": user.barbershop_id
            }
        }

    async def register(self, data: RegisterRequest) -> User:
        """
        Register new user.

        Args:
            data: Registration data

        Returns:
            Created user

        Raises:
            DuplicateResourceError: If email already exists
        """
        # Check if email exists
        if await self.user_repository.email_exists(data.email):
            raise DuplicateResourceError("Email already registered")

        # Hash password
        password_hash = hash_password(data.password)

        # Create user
        user = await self.user_repository.create(
            email=data.email,
            password_hash=password_hash,
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            role=UserRole.CLIENT,  # Default role
            is_active=True
        )

        return user

    async def refresh_access_token(self, refresh_token: str) -> str:
        """
        Generate new access token from refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            New access token

        Raises:
            InvalidTokenError: If refresh token is invalid
        """
        # Verify refresh token
        payload = verify_token(refresh_token, token_type="refresh")

        user_id = payload.get("sub")
        if not user_id:
            raise InvalidTokenError("Invalid token payload")

        # Get user
        user = await self.user_repository.get_by_id(int(user_id))
        if not user:
            raise InvalidTokenError("User not found")

        # Generate new access token
        access_token = create_access_token({"sub": str(user.id), "role": user.role})

        return access_token

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        """
        Change user password.

        Args:
            user_id: User ID
            current_password: Current password
            new_password: New password

        Raises:
            InvalidCredentialsError: If current password is wrong
        """
        user = await self.user_repository.get_by_id(user_id)

        if not user:
            raise InvalidCredentialsError("User not found")

        # Verify current password
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")

        # Update password
        new_password_hash = hash_password(new_password)
        await self.user_repository.update(user_id, password_hash=new_password_hash)
