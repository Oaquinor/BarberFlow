"""
API dependencies.

Common dependencies used across API endpoints.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_user_id_from_token, verify_token
from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.security.sessions import access_session_is_active
from app.models.user import User


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
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
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )

        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )

        # Get user ID from token
        payload = verify_token(token)
        user_id = get_user_id_from_token(token)

        # The active application uses synchronous SQLAlchemy sessions and MySQL.
        user = db.query(User).filter(
            User.id == user_id,
            User.is_deleted == False,
        ).first()

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
        if payload.get("auth_version", 0) != user.auth_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session was revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        session_id = payload.get("sid")
        if session_id is not None and not access_session_is_active(db, user.id, session_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session was revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user.barbershop_id and user.role != "super_admin":
            from app.models.barbershop import Barbershop

            active_shop = db.query(Barbershop.id).filter(
                Barbershop.id == user.barbershop_id,
                Barbershop.is_active == True,
                Barbershop.is_deleted == False,
            ).first()
            if not active_shop:
                raise HTTPException(status_code=403, detail="Barbershop is inactive")

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
