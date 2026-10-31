import os
from typing import Optional, Dict, Any, Generator
import sqlite3
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.common.db import get_db
from src.common.security import decode_access_token

security_bearer = HTTPBearer(auto_error=False)

def get_db_session() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a managed SQLite connection."""
    with get_db() as conn:
        yield conn

try:
    from src.part1_auth.dependencies import (
        get_current_user,
        require_admin,
        require_staff,
        require_customer,
    )
except ImportError:
    # Standalone implementations for decoupled development & testing
    async def get_current_user(
        token_auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    ) -> Dict[str, Any]:
        if not token_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        payload = decode_access_token(token_auth.credentials)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "id": payload.get("sub") or payload.get("id"),
            "email": payload.get("email"),
            "role": payload.get("role", "CUSTOMER"),
        }

    async def require_admin(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if current_user.get("role") != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )
        return current_user

    async def require_staff(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if current_user.get("role") not in ("ADMIN", "STAFF"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff privileges required",
            )
        return current_user

    async def require_customer(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        return current_user
