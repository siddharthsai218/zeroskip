import os
import sys
import tempfile
import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.db import init_db, get_db
from src.part1_auth.router import router as part1_router
from src.part1_auth.dependencies import get_db_session

ADMIN_PASSWORD = "AdminPass1!"
CUSTOMER_PASSWORD = "Customer9#"
STAFF_PASSWORD = "StaffPass2@"
NEW_PASSWORD = "NewPass123$"


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client(temp_db):
    app = FastAPI(title="Test Part 1 Auth API")
    app.include_router(part1_router, prefix="/api/v1")

    def override_get_db():
        with get_db(temp_db) as conn:
            yield conn

    app.dependency_overrides[get_db_session] = override_get_db
    return TestClient(app)


def _register(client, email, password, full_name="Test User"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )


def _login(client, email, password):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def _token(client, email, password):
    response = _login(client, email, password)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin(client):
    response = _register(client, "admin@example.com", ADMIN_PASSWORD, "Admin")
    assert response.status_code == 201, response.text
    return _token(client, "admin@example.com", ADMIN_PASSWORD)


def _create_customer(client, admin_token, email="customer@example.com"):
    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": CUSTOMER_PASSWORD,
            "full_name": "Customer",
            "role": "CUSTOMER",
        },
        headers=_headers(admin_token),
    )
    assert response.status_code == 201, response.text
    return _token(client, email, CUSTOMER_PASSWORD)


def _latest_reset_token(temp_db):
    with get_db(temp_db) as conn:
        row = conn.execute(
            "SELECT token FROM password_resets ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row["token"] if row else None


# ----------------- Registration & password policy -----------------

def test_register_first_user_becomes_admin(client):
    response = _register(client, "admin@example.com", ADMIN_PASSWORD, "Admin")
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "ADMIN"
    assert body["is_active"] is True
    assert body["email"] == "admin@example.com"
    assert "password_hash" not in body


def test_register_subsequent_user_is_customer(client):
    _register(client, "admin@example.com", ADMIN_PASSWORD, "Admin")
    response = _register(client, "second@example.com", CUSTOMER_PASSWORD, "Second")
    assert response.status_code == 201
    assert response.json()["role"] == "CUSTOMER"


def test_register_normalizes_email_case(client):
    response = _register(client, "  MixedCase@Example.com ", CUSTOMER_PASSWORD, "Mixed")
    assert response.status_code == 201
    assert response.json()["email"] == "mixedcase@example.com"


@pytest.mark.parametrize(
    "weak_password",
    [
        "Aa1!",              # too short
        "alllowercase1!",    # no uppercase
        "ALLUPPERCASE1!",    # no lowercase
        "NoSpecial123",      # no special character
        "ValidPass1",        # still no special character
    ],
)
def test_register_rejects_weak_passwords(client, weak_password):
    response = _register(client, "weak@example.com", weak_password)
    assert response.status_code == 400


def test_register_rejects_duplicate_email(client):
    assert _register(client, "dup@example.com", CUSTOMER_PASSWORD).status_code == 201
    response = _register(client, "DUP@example.com", CUSTOMER_PASSWORD)
    assert response.status_code == 409


def test_register_rejects_invalid_email(client):
    response = _register(client, "not-an-email", ADMIN_PASSWORD)
    assert response.status_code == 422


# ----------------- Login & JWT -----------------

def test_login_returns_token_and_me(client):
    admin_token = _bootstrap_admin(client)
    me = client.get("/api/v1/users/me", headers=_headers(admin_token))
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"
    assert me.json()["role"] == "ADMIN"


def test_login_rejects_wrong_password(client):
    _bootstrap_admin(client)
    response = _login(client, "admin@example.com", "WrongPass1!")
    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = _login(client, "nobody@example.com", ADMIN_PASSWORD)
    assert response.status_code == 401


def test_inactive_user_cannot_login(client):
    admin_token = _bootstrap_admin(client)
    customer_token = _create_customer(client, admin_token)
    me = client.get("/api/v1/users/me", headers=_headers(customer_token))
    customer_id = me.json()["id"]

    disable = client.patch(
        f"/api/v1/users/{customer_id}/status",
        json={"is_active": False},
        headers=_headers(admin_token),
    )
    assert disable.status_code == 200
    assert disable.json()["is_active"] is False

    response = _login(client, "customer@example.com", CUSTOMER_PASSWORD)
    assert response.status_code == 401

    blocked = client.get("/api/v1/users/me", headers=_headers(customer_token))
    assert blocked.status_code == 403


# ----------------- RBAC -----------------

def test_unauthenticated_requests_rejected(client):
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users").status_code == 401
    assert client.get("/api/v1/portal/profile").status_code == 401


def test_customer_cannot_access_admin_endpoints(client):
    admin_token = _bootstrap_admin(client)
    customer_token = _create_customer(client, admin_token)

    assert client.get("/api/v1/users", headers=_headers(customer_token)).status_code == 403
    assert (
        client.post(
            "/api/v1/users",
            json={
                "email": "x@example.com",
                "password": STAFF_PASSWORD,
                "full_name": "X",
                "role": "STAFF",
            },
            headers=_headers(customer_token),
        ).status_code
        == 403
    )


def test_admin_can_create_staff_and_list_users(client):
    admin_token = _bootstrap_admin(client)
    created = client.post(
        "/api/v1/users",
        json={
            "email": "staff@example.com",
            "password": STAFF_PASSWORD,
            "full_name": "Staff Member",
            "role": "STAFF",
        },
        headers=_headers(admin_token),
    )
    assert created.status_code == 201
    assert created.json()["role"] == "STAFF"

    listing = client.get("/api/v1/users", headers=_headers(admin_token))
    assert listing.status_code == 200
    emails = {user["email"] for user in listing.json()}
    assert {"admin@example.com", "staff@example.com"} <= emails

    staff_only = client.get("/api/v1/users?role=STAFF", headers=_headers(admin_token))
    assert staff_only.status_code == 200
    assert all(user["role"] == "STAFF" for user in staff_only.json())


def test_admin_can_get_single_user(client):
    admin_token = _bootstrap_admin(client)
    created = client.post(
        "/api/v1/users",
        json={
            "email": "staff@example.com",
            "password": STAFF_PASSWORD,
            "full_name": "Staff Member",
            "role": "STAFF",
        },
        headers=_headers(admin_token),
    )
    user_id = created.json()["id"]

    response = client.get(f"/api/v1/users/{user_id}", headers=_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["id"] == user_id

    missing = client.get("/api/v1/users/99999", headers=_headers(admin_token))
    assert missing.status_code == 404


# ----------------- Password reset -----------------

def test_password_reset_flow(client, temp_db):
    _bootstrap_admin(client)

    request_response = client.post(
        "/api/v1/auth/password-reset",
        json={"email": "admin@example.com"},
    )
    assert request_response.status_code == 200

    token = _latest_reset_token(temp_db)
    assert token is not None

    confirm = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert confirm.status_code == 200

    assert _login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 401
    assert _login(client, "admin@example.com", NEW_PASSWORD).status_code == 200


def test_password_reset_does_not_reveal_token(client):
    _bootstrap_admin(client)
    response = client.post(
        "/api/v1/auth/password-reset",
        json={"email": "admin@example.com"},
    )
    assert response.status_code == 200
    assert "token" not in response.json()
    assert set(response.json().keys()) == {"message"}


def test_password_reset_unknown_email_is_generic(client):
    response = client.post(
        "/api/v1/auth/password-reset",
        json={"email": "nobody@example.com"},
    )
    assert response.status_code == 200
    assert set(response.json().keys()) == {"message"}


def test_password_reset_invalid_token(client):
    _bootstrap_admin(client)
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400


def test_password_reset_token_single_use(client, temp_db):
    _bootstrap_admin(client)
    client.post("/api/v1/auth/password-reset", json={"email": "admin@example.com"})
    token = _latest_reset_token(temp_db)

    first = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "AnotherPass3&"},
    )
    assert second.status_code == 400


def test_password_reset_expired_token(client, temp_db):
    _bootstrap_admin(client)
    client.post("/api/v1/auth/password-reset", json={"email": "admin@example.com"})
    token = _latest_reset_token(temp_db)

    past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
    with get_db(temp_db) as conn:
        conn.execute(
            "UPDATE password_resets SET expires_at = ? WHERE token = ?",
            (past, token),
        )

    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400


def test_password_reset_rejects_weak_new_password(client, temp_db):
    _bootstrap_admin(client)
    client.post("/api/v1/auth/password-reset", json={"email": "admin@example.com"})
    token = _latest_reset_token(temp_db)

    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "weakpass"},
    )
    assert response.status_code == 400


# ----------------- Customer portal -----------------

def test_portal_profile_get_and_update(client):
    admin_token = _bootstrap_admin(client)
    customer_token = _create_customer(client, admin_token)

    profile = client.get("/api/v1/portal/profile", headers=_headers(customer_token))
    assert profile.status_code == 200
    assert profile.json()["role"] == "CUSTOMER"

    updated = client.put(
        "/api/v1/portal/profile",
        json={"full_name": "Updated Name", "password": NEW_PASSWORD},
        headers=_headers(customer_token),
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Updated Name"

    assert _login(client, "customer@example.com", CUSTOMER_PASSWORD).status_code == 401
    assert _login(client, "customer@example.com", NEW_PASSWORD).status_code == 200


def test_portal_rejects_weak_password_update(client):
    admin_token = _bootstrap_admin(client)
    customer_token = _create_customer(client, admin_token)

    response = client.put(
        "/api/v1/portal/profile",
        json={"password": "weakpass"},
        headers=_headers(customer_token),
    )
    assert response.status_code == 400
