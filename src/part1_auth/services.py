import os
import sqlite3
import secrets
import datetime
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status

from src.common.security import (
    validate_password_strength,
    hash_password,
    verify_password,
)
from src.part1_auth.schemas import (
    UserRegister,
    UserCreate,
    UserLogin,
    ProfileUpdate,
)

PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "60"))


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(value: datetime.datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _parse_dt(value: str) -> datetime.datetime:
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _row_to_public(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    user = dict(row)
    user.pop("password_hash", None)
    user["is_active"] = bool(user.get("is_active"))
    return user


def _fetch_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None


def _fetch_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def _count_users(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    return int(row["total"]) if row else 0


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_public(row)


def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return _row_to_public(row)


def _ensure_password_strength(password: str) -> None:
    valid, message = validate_password_strength(password)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _insert_user(
    conn: sqlite3.Connection,
    email: str,
    password: str,
    full_name: str,
    role: str,
) -> Dict[str, Any]:
    email = email.strip().lower()
    if _fetch_user_by_email(conn, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    _ensure_password_strength(password)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (email, password_hash, full_name, role, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (email, hash_password(password), full_name.strip(), role),
    )
    created = get_user_by_id(conn, cursor.lastrowid)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )
    return created


def register_user(conn: sqlite3.Connection, data: UserRegister) -> Dict[str, Any]:
    role = "ADMIN" if _count_users(conn) == 0 else "CUSTOMER"
    return _insert_user(conn, data.email, data.password, data.full_name, role)


def create_user_as_admin(conn: sqlite3.Connection, data: UserCreate) -> Dict[str, Any]:
    return _insert_user(conn, data.email, data.password, data.full_name, data.role)


def authenticate_user(conn: sqlite3.Connection, data: UserLogin) -> Dict[str, Any]:
    row = _fetch_user_by_email(conn, data.email)
    if row is None or not bool(row["is_active"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(data.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _row_to_public(row)


def list_users(
    conn: sqlite3.Connection,
    skip: int = 0,
    limit: int = 100,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM users"
    clauses: List[str] = []
    params: List[Any] = []
    if role is not None:
        clauses.append("role = ?")
        params.append(role)
    if is_active is not None:
        clauses.append("is_active = ?")
        params.append(1 if is_active else 0)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id LIMIT ? OFFSET ?"
    params.extend([limit, skip])
    rows = conn.execute(query, params).fetchall()
    return [_row_to_public(row) for row in rows]


def set_user_active(conn: sqlite3.Connection, user_id: int, is_active: bool) -> Dict[str, Any]:
    if _fetch_user_by_id(conn, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    conn.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, user_id),
    )
    updated = get_user_by_id(conn, user_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated


def update_user_profile(
    conn: sqlite3.Connection,
    user_id: int,
    data: ProfileUpdate,
) -> Dict[str, Any]:
    current = _fetch_user_by_id(conn, user_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates: List[str] = []
    params: List[Any] = []
    if data.full_name is not None:
        updates.append("full_name = ?")
        params.append(data.full_name.strip())
    if data.password is not None:
        _ensure_password_strength(data.password)
        updates.append("password_hash = ?")
        params.append(hash_password(data.password))

    if updates:
        params.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)

    updated = get_user_by_id(conn, user_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated


def create_password_reset(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = _iso(_utcnow() + datetime.timedelta(minutes=PASSWORD_RESET_TTL_MINUTES))
    conn.execute(
        "INSERT INTO password_resets (user_id, token, expires_at, used) VALUES (?, ?, ?, 0)",
        (user_id, token, expires_at),
    )
    return token


def request_password_reset(conn: sqlite3.Connection, email: str) -> Optional[str]:
    user = get_user_by_email(conn, email)
    if user is None or not user["is_active"]:
        return None
    return create_password_reset(conn, user["id"])


def confirm_password_reset(
    conn: sqlite3.Connection,
    token: str,
    new_password: str,
) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM password_resets WHERE token = ?",
        (token,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    reset = dict(row)
    if bool(reset["used"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used",
        )
    if _parse_dt(reset["expires_at"]) < _utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )

    _ensure_password_strength(new_password)
    user = _fetch_user_by_id(conn, reset["user_id"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user["id"]),
    )
    conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset["id"],))

    updated = get_user_by_id(conn, user["id"])
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated
