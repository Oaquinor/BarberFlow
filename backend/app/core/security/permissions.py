"""
Permission checking utilities.

Provides role-based access control (RBAC) functionality.
"""

from typing import List

from app.core.constants import UserRole
from app.core.exceptions import InsufficientPermissionsError
from app.models.user import User


def check_permission(user: User, required_roles: List[UserRole]) -> None:
    """
    Check if user has required role.

    Args:
        user: User to check
        required_roles: List of allowed roles

    Raises:
        InsufficientPermissionsError: If user doesn't have required role
    """
    if user.role not in required_roles:
        raise InsufficientPermissionsError(
            f"User role '{user.role}' is not authorized for this action"
        )


def is_super_admin(user: User) -> bool:
    """Check if user is super admin."""
    return user.role == UserRole.SUPER_ADMIN


def is_barbershop_owner(user: User) -> bool:
    """Check if user is barbershop owner."""
    return user.role == UserRole.BARBERSHOP_OWNER


def is_barber(user: User) -> bool:
    """Check if user is barber."""
    return user.role == UserRole.BARBER


def is_client(user: User) -> bool:
    """Check if user is client."""
    return user.role == UserRole.CLIENT


def can_manage_barbershop(user: User) -> bool:
    """Check if user can manage barbershop."""
    return user.role in [UserRole.SUPER_ADMIN, UserRole.BARBERSHOP_OWNER]


def can_manage_appointments(user: User) -> bool:
    """Check if user can manage appointments."""
    return user.role in [UserRole.SUPER_ADMIN, UserRole.BARBERSHOP_OWNER, UserRole.BARBER]


def check_barbershop_access(user: User, barbershop_id: int) -> None:
    """
    Check if user has access to barbershop.

    Args:
        user: User to check
        barbershop_id: Barbershop ID to check access to

    Raises:
        InsufficientPermissionsError: If user doesn't have access
    """
    # Super admin has access to all
    if is_super_admin(user):
        return

    # Check if user belongs to barbershop
    if user.barbershop_id != barbershop_id:
        raise InsufficientPermissionsError(
            "You don't have access to this barbershop"
        )
