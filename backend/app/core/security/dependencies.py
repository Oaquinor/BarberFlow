"""Shared authentication and authorization dependencies for FastAPI."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.security.jwt import get_user_id_from_token, verify_token
from app.core.security.sessions import access_session_is_active
from app.models.user import User


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    """Return the active authenticated user and reject revoked sessions."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_token(token)
        user_id = get_user_id_from_token(token)
    except (InvalidTokenError, TokenExpiredError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user = db.query(User).filter(
        User.id == user_id,
        User.is_deleted == False,
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
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


def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User | None:
    """Return the authenticated user, or None when no valid auth is supplied."""
    if not authorization:
        return None
    try:
        return get_current_user(authorization, db)
    except HTTPException:
        return None


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Require an active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user


def get_current_barber(current_user: User = Depends(get_current_user)) -> User:
    """Require a barber or owner account allowed to use barber operations."""
    from app.core.constants import UserRole

    if current_user.role not in [UserRole.BARBER, UserRole.BARBERSHOP_OWNER]:
        raise HTTPException(status_code=403, detail="User is not a barber")
    return current_user


def get_current_owner(current_user: User = Depends(get_current_user)) -> User:
    """Require a barbershop owner account."""
    from app.core.constants import UserRole

    if current_user.role != UserRole.BARBERSHOP_OWNER:
        raise HTTPException(status_code=403, detail="User is not a barbershop owner")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
DatabaseSession = Annotated[Session, Depends(get_db)]
