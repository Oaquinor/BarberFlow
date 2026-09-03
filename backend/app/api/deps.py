"""
API dependencies.

Common dependencies used across API endpoints.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_user_id_from_token
from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.repositories.user_repository import UserRepository
from app.models.user import User


def get_current_user(
    authorization: Annotated[str, Header()],
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token.

    Args:
        authorization: Authorization header with Bearer token
        db: Database session

    Returns:
        Current user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    try:
        # Extract token from header
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )

        token = authorization.replace("Bearer ", "")

        # Get user ID from token
        user_id = get_user_id_from_token(token)

        # Get user from database
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )

        return user

    except (InvalidTokenError, TokenExpiredError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db)
) -> User | None:
    """
    Get current user if authenticated, None otherwise.

    Args:
        authorization: Optional authorization header
        db: Database session

    Returns:
        Current user or None
    """
    if not authorization:
        return None

    try:
        return get_current_user(authorization, db)
    except HTTPException:
        return None


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
DatabaseSession = Annotated[Session, Depends(get_db)]
