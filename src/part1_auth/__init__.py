"""
Part 1: Authentication, Access Control & User Identity.
Owned by Developer 1.
"""

from src.part1_auth.router import (
    router,
    auth_router,
    users_router,
    portal_router,
)
from src.part1_auth.dependencies import (
    get_db_session,
    get_current_user,
    require_admin,
    require_staff,
    require_customer,
)
from src.part1_auth.services import (
    register_user,
    create_user_as_admin,
    authenticate_user,
    get_user_by_id,
    get_user_by_email,
    list_users,
    set_user_active,
    update_user_profile,
    create_password_reset,
    request_password_reset,
    confirm_password_reset,
)
