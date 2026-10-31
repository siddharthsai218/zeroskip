import sqlite3
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query

from src.common.security import create_access_token
from src.part1_auth import services
from src.part1_auth.dependencies import (
    get_db_session,
    get_current_user,
    require_admin,
    require_customer,
)
from src.part1_auth.schemas import (
    Role,
    UserRegister,
    UserCreate,
    UserLogin,
    TokenResponse,
    UserProfileResponse,
    ProfileUpdate,
    UserStatusUpdate,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["User Management"])
portal_router = APIRouter(prefix="/portal", tags=["Customer Portal"])


# ----------------- Authentication Routes -----------------

@auth_router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def register_endpoint(
    data: UserRegister,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.register_user(conn, data)


@auth_router.post("/login", response_model=TokenResponse)
def login_endpoint(
    data: UserLogin,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    user = services.authenticate_user(conn, data)
    token = create_access_token(
        {
            "sub": str(user["id"]),
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
        }
    )
    return TokenResponse(access_token=token)


@auth_router.post("/password-reset", response_model=MessageResponse)
def request_password_reset_endpoint(
    data: PasswordResetRequest,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    services.request_password_reset(conn, data.email)
    return MessageResponse(
        message="If an account with that email exists, a password reset token has been generated."
    )


@auth_router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset_endpoint(
    data: PasswordResetConfirm,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    services.confirm_password_reset(conn, data.token, data.new_password)
    return MessageResponse(message="Password has been reset successfully.")


# ----------------- User Management Routes (Admin) -----------------

@users_router.get("/me", response_model=UserProfileResponse)
def get_me_endpoint(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return current_user


@users_router.get("", response_model=List[UserProfileResponse])
def list_users_endpoint(
    role: Optional[Role] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db_session),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    return services.list_users(
        conn,
        skip=skip,
        limit=limit,
        role=role,
        is_active=is_active,
    )


@users_router.post("", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    data: UserCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    return services.create_user_as_admin(conn, data)


@users_router.get("/{user_id}", response_model=UserProfileResponse)
def get_user_endpoint(
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    user = services.get_user_by_id(conn, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@users_router.patch("/{user_id}/status", response_model=UserProfileResponse)
def set_user_status_endpoint(
    user_id: int,
    data: UserStatusUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    return services.set_user_active(conn, user_id, data.is_active)


# ----------------- Customer Portal Routes -----------------

@portal_router.get("/profile", response_model=UserProfileResponse)
def get_portal_profile_endpoint(
    current_user: Dict[str, Any] = Depends(require_customer),
):
    return current_user


@portal_router.put("/profile", response_model=UserProfileResponse)
def update_portal_profile_endpoint(
    data: ProfileUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    return services.update_user_profile(conn, current_user["id"], data)


# ----------------- Master Part 1 Router -----------------

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(portal_router)
