"""
JWT token handling.

Provides functions for creating and validating JWT tokens.
"""

from datetime import datetime, timedelta
from typing import Any, Dict

from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError

settings = get_settings()


def create_access_token(data: Dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Create JWT access token.

    Args:
        data: Data to encode in token
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create JWT refresh token.

    Args:
        data: Data to encode in token

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    Verify and decode JWT token.

    Args:
        token: JWT token to verify
        token_type: Expected token type (access or refresh)

    Returns:
        Decoded token data

    Raises:
        InvalidTokenError: If token is invalid
        TokenExpiredError: If token is expired
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Verify token type
        if payload.get("type") != token_type:
            raise InvalidTokenError("Invalid token type")

        return payload

    except JWTError as e:
        if "expired" in str(e).lower():
            raise TokenExpiredError("Token has expired")
        raise InvalidTokenError("Invalid token")


def get_user_id_from_token(token: str) -> int:
    """
    Extract user ID from token.

    Args:
        token: JWT token

    Returns:
        User ID
    """
    payload = verify_token(token)
    user_id = payload.get("sub")

    if not user_id:
        raise InvalidTokenError("Invalid token payload")

    return int(user_id)
