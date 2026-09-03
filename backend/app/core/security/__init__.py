"""Security package."""

from app.core.security.jwt import (
    create_access_token,
    create_refresh_token,
    verify_token,
    get_user_id_from_token,
)
from app.core.security.password import hash_password, verify_password
from app.core.security.permissions import (
    check_permission,
    is_super_admin,
    is_barbershop_owner,
    is_barber,
    is_client,
    can_manage_barbershop,
    can_manage_appointments,
    check_barbershop_access,
)
from app.core.security.dependencies import (
    get_current_user,
    get_current_active_user,
    get_current_barber,
    get_current_owner,
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "get_user_id_from_token",
    "hash_password",
    "verify_password",
    "check_permission",
    "is_super_admin",
    "is_barbershop_owner",
    "is_barber",
    "is_client",
    "can_manage_barbershop",
    "can_manage_appointments",
    "check_barbershop_access",
    "get_current_user",
    "get_current_active_user",
    "get_current_barber",
    "get_current_owner",
]
