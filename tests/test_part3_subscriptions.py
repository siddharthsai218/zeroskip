import os
import sys
import tempfile
import datetime
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.db import init_db, get_db
from src.part3_subscriptions.router import router as subscriptions_master_router
from src.part3_subscriptions.dependencies import (
    get_db_session,
    require_admin,
    require_staff,
    require_customer,
    get_current_user,
)

ADMIN_USER = {"id": 1, "email": "admin@brightloop.io", "role": "ADMIN"}
STAFF_USER = {"id": 2, "email": "staff@brightloop.io", "role": "STAFF"}
CUSTOMER_1 = {"id": 10, "email": "customer1@brightloop.io", "role": "CUSTOMER"}
CUSTOMER_2 = {"id": 20, "email": "customer2@brightloop.io", "role": "CUSTOMER"}

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
    app = FastAPI(title="Test Subscriptions API")
    app.include_router(subscriptions_master_router, prefix="/api/v1")

    def override_get_db():
        with get_db(temp_db) as conn:
            yield conn

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    app.dependency_overrides[require_staff] = lambda: STAFF_USER
    app.dependency_overrides[require_customer] = lambda: CUSTOMER_1
    app.dependency_overrides[get_current_user] = lambda: STAFF_USER

    return TestClient(app)

def seed_base_entities(db_path: str):
    """Seeds test users, products, variants, and plans and commits immediately."""
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        # Users
        cursor.execute("INSERT INTO users (id, email, password_hash, full_name, role) VALUES (1, 'admin@brightloop.io', 'hash', 'Admin', 'ADMIN')")
        cursor.execute("INSERT INTO users (id, email, password_hash, full_name, role) VALUES (2, 'staff@brightloop.io', 'hash', 'Staff', 'STAFF')")
        cursor.execute("INSERT INTO users (id, email, password_hash, full_name, role) VALUES (10, 'customer1@brightloop.io', 'hash', 'Alice Corp', 'CUSTOMER')")
        cursor.execute("INSERT INTO users (id, email, password_hash, full_name, role) VALUES (20, 'customer2@brightloop.io', 'hash', 'Bob LLC', 'CUSTOMER')")

        # Products & Variants
        cursor.execute("INSERT INTO products (id, name, product_type, sales_price, cost_price, is_active) VALUES (101, 'CRM Software', 'SOFTWARE', 1000.0, 200.0, 1)")
        cursor.execute("INSERT INTO products (id, name, product_type, sales_price, cost_price, is_active) VALUES (102, 'Analytics Addon', 'ADDON', 200.0, 50.0, 1)")
        cursor.execute("INSERT INTO product_variants (id, product_id, attribute_name, attribute_value, price_extra) VALUES (1, 101, 'Brand', 'Odoo', 560.0)")

        # Plans
        cursor.execute("""
        INSERT INTO plans (id, name, code, billing_interval, price, min_quantity, auto_close, allow_early_close, allow_pause, allow_renew, is_active)
        VALUES (1, 'Pro Monthly', 'PLAN-MONTHLY', 'MONTHLY', 1000.0, 1, 0, 1, 1, 1, 1)
        """)
        cursor.execute("""
        INSERT INTO plans (id, name, code, billing_interval, price, min_quantity, auto_close, allow_early_close, allow_pause, allow_renew, is_active)
        VALUES (2, 'Fixed Yearly Lock', 'PLAN-LOCKED', 'YEARLY', 10000.0, 1, 1, 0, 0, 0, 1)
        """)

        # Tax rules
        cursor.execute("INSERT INTO tax_rules (id, name, rate_percent, is_default, is_active) VALUES (1, 'Standard VAT', 10.0, 1, 1)")

        # Quotation Templates
        cursor.execute("""
        INSERT INTO quotation_templates (id, name, plan_id, validity_days, notes)
        VALUES (1, 'Standard Software Offer', 1, 30, 'Standard 30-day quote template')
        """)
        cursor.execute("INSERT INTO quotation_template_lines (template_id, product_id, variant_id, quantity) VALUES (1, 101, 1, 2)")
        cursor.execute("INSERT INTO quotation_template_lines (template_id, product_id, variant_id, quantity) VALUES (1, 102, NULL, 1)")

        conn.commit()


# ============================================================================
# Test Cases
# ============================================================================

def test_create_quotation_from_template(client, temp_db):
    seed_base_entities(temp_db)

    resp = client.post("/api/v1/quotations/template", json={
        "template_id": 1,
        "customer_id": 10,
        "payment_terms": "Net 30",
        "notes": "Customized quote for Alice"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["subscription_number"].startswith("SUB-")
    assert data["status"] == "Draft"
    assert data["customer_id"] == 10
    assert data["plan_id"] == 1
    assert len(data["lines"]) == 2

    # Check variant price addition: base CRM 1000 + Odoo variant 560 = 1560
    # Qty 2 -> Subtotal 3120 + 10% tax = 3432
    crm_line = next(l for l in data["lines"] if l["product_id"] == 101)
    assert crm_line["unit_price"] == 1560.0
    assert crm_line["quantity"] == 2
    assert crm_line["amount"] == 3432.0

    # Event log exists
    assert len(data["events"]) >= 1
    assert data["events"][0]["to_status"] == "Draft"


def test_create_custom_quotation(client, temp_db):
    seed_base_entities(temp_db)

    resp = client.post("/api/v1/quotations/custom", json={
        "customer_id": 10,
        "plan_id": 1,
        "payment_terms": "Net 15",
        "lines": [
            {"product_id": 102, "quantity": 3, "unit_price": 180.0, "tax_rate": 5.0}
        ]
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "Draft"
    assert data["payment_terms"] == "Net 15"
    assert len(data["lines"]) == 1
    # 3 * 180 = 540 + 5% = 567
    assert data["lines"][0]["amount"] == 567.0


def test_list_quotations_and_subscriptions(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (1, 'SUB-2026-001', 10, 1, 'Draft', 'Net 30', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (2, 'SUB-2026-002', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        conn.commit()

    # Quotations endpoint lists only Draft / Quotation
    resp_quotes = client.get("/api/v1/quotations")
    assert resp_quotes.status_code == 200
    quotes = resp_quotes.json()
    assert len(quotes) == 1
    assert quotes[0]["id"] == 1

    # Subscriptions endpoint lists all or filtered
    resp_all = client.get("/api/v1/subscriptions")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) == 2

    resp_active = client.get("/api/v1/subscriptions?status=Active")
    assert resp_active.status_code == 200
    assert len(resp_active.json()) == 1
    assert resp_active.json()[0]["id"] == 2


def test_subscription_state_machine_transitions(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (3, 'SUB-2026-003', 10, 1, 'Draft', 'Net 30', '2026-11-01')
        """)
        conn.commit()

    # 1. Draft -> Quotation
    r1 = client.patch("/api/v1/subscriptions/3/status", json={"target_status": "Quotation", "reason": "Sent to prospect"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "Quotation"

    # 2. Quotation -> Confirmed
    r2 = client.patch("/api/v1/subscriptions/3/status", json={"target_status": "Confirmed", "reason": "Customer agreed"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "Confirmed"

    # 3. Confirmed -> Active
    r3 = client.patch("/api/v1/subscriptions/3/status", json={"target_status": "Active"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "Active"

    # 4. Invalid Transition: Active -> Quotation (rejected)
    r_bad = client.patch("/api/v1/subscriptions/3/status", json={"target_status": "Quotation"})
    assert r_bad.status_code == 400


def test_pause_and_resume_policy(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        # Plan 1 allows pause
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (4, 'SUB-2026-004', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        # Plan 2 does NOT allow pause
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (5, 'SUB-2026-005', 10, 2, 'Active', 'Net 30', '2026-11-01')
        """)
        conn.commit()

    # Allowed pause
    r_pause = client.post("/api/v1/subscriptions/4/pause?reason=Vacation")
    assert r_pause.status_code == 200
    assert r_pause.json()["status"] == "Paused"

    # Resume back
    r_resume = client.post("/api/v1/subscriptions/4/resume")
    assert r_resume.status_code == 200
    assert r_resume.json()["status"] == "Active"

    # Disallowed pause on plan 2
    r_disallowed = client.post("/api/v1/subscriptions/5/pause")
    assert r_disallowed.status_code == 400
    assert "does not permit pausing" in r_disallowed.json()["detail"]


def test_early_close_and_renewal_policy(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        # Plan 1 allows early close and renewal
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date, expiry_date)
        VALUES (6, 'SUB-2026-006', 10, 1, 'Active', 'Net 30', '2026-11-01', '2026-12-01')
        """)
        # Plan 2 does NOT allow renewal or early close
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date, expiry_date)
        VALUES (7, 'SUB-2026-007', 10, 2, 'Active', 'Net 30', '2026-11-01', '2027-11-01')
        """)
        conn.commit()

    # Renewal on Plan 1: extends expiry from 2026-12-01 by 1 month to 2027-01-01
    r_renew = client.post("/api/v1/subscriptions/6/renew", json={"extension_periods": 1})
    assert r_renew.status_code == 200
    assert r_renew.json()["expiry_date"] == "2027-01-01"

    # Renewal on Plan 2: rejected by policy
    r_renew_bad = client.post("/api/v1/subscriptions/7/renew", json={"extension_periods": 1})
    assert r_renew_bad.status_code == 400
    assert "does not permit renewal" in r_renew_bad.json()["detail"]


def test_customer_portal_subscriptions_isolation(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        # Sub for Customer 1 (id 10)
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (8, 'SUB-2026-008', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        # Sub for Customer 2 (id 20)
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (9, 'SUB-2026-009', 20, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        conn.commit()

    # Authenticated as Customer 1
    r_list = client.get("/api/v1/portal/subscriptions")
    assert r_list.status_code == 200
    subs = r_list.json()
    assert len(subs) == 1
    assert subs[0]["id"] == 8

    # Customer 1 cannot access Customer 2's sub
    r_cross = client.get("/api/v1/portal/subscriptions/9")
    assert r_cross.status_code == 404

    # Customer 1 can pause own sub
    r_pause = client.post("/api/v1/portal/subscriptions/8/pause")
    assert r_pause.status_code == 200
    assert r_pause.json()["status"] == "Paused"
