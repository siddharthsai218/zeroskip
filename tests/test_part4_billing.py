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
from src.part4_billing.router import router as billing_master_router
from src.part4_billing.dependencies import (
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
    app = FastAPI(title="Test Billing API")
    app.include_router(billing_master_router, prefix="/api/v1")

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

        # Products
        cursor.execute("INSERT INTO products (id, name, product_type, sales_price, cost_price) VALUES (101, 'CRM Software', 'SOFTWARE', 1000.0, 200.0)")
        cursor.execute("INSERT INTO products (id, name, product_type, sales_price, cost_price) VALUES (102, 'Analytics Addon', 'ADDON', 200.0, 50.0)")

        # Plans
        cursor.execute("""
        INSERT INTO plans (id, name, code, billing_interval, price, min_quantity, auto_close, allow_early_close, allow_pause, allow_renew)
        VALUES (1, 'Pro Monthly', 'PLAN-MONTHLY', 'MONTHLY', 1000.0, 1, 0, 1, 1, 1)
        """)
        cursor.execute("""
        INSERT INTO plans (id, name, code, billing_interval, price, min_quantity, auto_close, allow_early_close, allow_pause, allow_renew)
        VALUES (2, 'Enterprise Yearly', 'PLAN-YEARLY', 'YEARLY', 10000.0, 1, 1, 1, 1, 1)
        """)
        cursor.execute("""
        INSERT INTO plans (id, name, code, billing_interval, price, min_quantity, auto_close, allow_early_close, allow_pause, allow_renew)
        VALUES (3, 'Daily Pass', 'PLAN-DAILY', 'DAILY', 50.0, 1, 0, 1, 1, 1)
        """)
        conn.commit()


# ============================================================================
# Test Cases
# ============================================================================

def test_billing_engine_monthly_cycle(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date, next_billing_date)
        VALUES (1, 'SUB-2026-001', 10, 1, 'Active', 'Net 30', '2026-11-01', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_rate, amount)
        VALUES (1, 101, 2, 1000.0, 10.0, 2200.0)
        """)
        conn.commit()

    # Trigger billing run
    response = client.post("/api/v1/billing/trigger", json={"run_date": "2026-11-01"})
    assert response.status_code == 200
    data = response.json()
    assert data["subscriptions_evaluated"] == 1
    assert data["invoices_generated"] == 1
    assert data["total_billed_amount"] == 2200.0

    # Verify subscription next_billing_date advanced by 1 month to 2026-12-01
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT next_billing_date, last_billed_date FROM subscriptions WHERE id = 1")
        sub_row = cursor.fetchone()
        assert sub_row["next_billing_date"] == "2026-12-01"
        assert sub_row["last_billed_date"] == "2026-11-01"

        # Verify generated invoice
        cursor.execute("SELECT * FROM invoices WHERE subscription_id = 1")
        inv = cursor.fetchone()
        assert inv is not None
        assert inv["customer_id"] == 10
        assert inv["status"] == "Draft"
        assert inv["subtotal"] == 2000.0
        assert inv["tax_total"] == 200.0
        assert inv["total_amount"] == 2200.0
        assert inv["due_date"] == "2026-12-01"  # Net 30 from 2026-11-01


def test_billing_engine_idempotency_zero_skip(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date, next_billing_date)
        VALUES (2, 'SUB-2026-002', 10, 1, 'Active', 'Net 30', '2026-11-01', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_rate, amount)
        VALUES (2, 101, 1, 1000.0, 0.0, 1000.0)
        """)
        conn.commit()

    # First run: generates 1 invoice
    resp1 = client.post("/api/v1/billing/trigger", json={"run_date": "2026-11-01"})
    assert resp1.status_code == 200
    assert resp1.json()["invoices_generated"] == 1

    # Second run immediately on same date: 0 duplicate invoices!
    resp2 = client.post("/api/v1/billing/trigger", json={"run_date": "2026-11-01"})
    assert resp2.status_code == 200
    assert resp2.json()["invoices_generated"] == 0

    # Ensure only 1 invoice in DB
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE subscription_id = 2")
        assert cursor.fetchone()[0] == 1


def test_billing_with_discount_rules(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO discount_rules (id, code, name, discount_type, discount_value, min_purchase_amount, is_active, times_used, max_uses)
        VALUES (1, 'OFF20', '20 Percent Off', 'PERCENTAGE', 20.0, 500.0, 1, 0, 5)
        """)
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date, next_billing_date, discount_rule_id)
        VALUES (3, 'SUB-2026-003', 10, 1, 'Active', 'Net 15', '2026-11-01', '2026-11-01', 1)
        """)
        cursor.execute("""
        INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_rate, amount)
        VALUES (3, 101, 1, 1000.0, 10.0, 1100.0)
        """)
        conn.commit()

    resp = client.post("/api/v1/billing/trigger", json={"run_date": "2026-11-01"})
    assert resp.status_code == 200

    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE subscription_id = 3")
        inv = cursor.fetchone()
        assert inv["subtotal"] == 1000.0
        assert inv["tax_total"] == 100.0
        assert inv["discount_total"] == 200.0  # 20% of 1000
        assert inv["total_amount"] == 900.0    # 1000 + 100 - 200

        # Verify discount times_used was incremented
        cursor.execute("SELECT times_used FROM discount_rules WHERE id = 1")
        assert cursor.fetchone()[0] == 1


def test_billing_auto_close_on_expiry(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date, expiry_date, next_billing_date)
        VALUES (4, 'SUB-2026-004', 10, 2, 'Active', 'Net 30', '2025-11-01', '2026-11-01', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_rate, amount)
        VALUES (4, 101, 1, 10000.0, 0.0, 10000.0)
        """)
        conn.commit()

    resp = client.post("/api/v1/billing/trigger", json={"run_date": "2026-11-01"})
    assert resp.status_code == 200

    # Subscription should transition to Closed
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM subscriptions WHERE id = 4")
        assert cursor.fetchone()[0] == "Closed"


def test_invoice_lifecycle_and_state_machine(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (5, 'SUB-2026-005', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, subtotal, tax_total, discount_total, total_amount, amount_paid)
        VALUES (100, 'INV-20261101-00100', 5, 10, 'Draft', '2026-11-01', '2026-12-01', 500.0, 0.0, 0.0, 500.0, 0.0)
        """)
        conn.commit()

    # 1. Transition Draft -> Confirmed
    resp = client.patch("/api/v1/invoices/100/status", json={"status": "Confirmed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "Confirmed"

    # 2. Invalid Transition: Confirmed -> Draft (rejected)
    resp_invalid = client.patch("/api/v1/invoices/100/status", json={"status": "Draft"})
    assert resp_invalid.status_code == 400

    # 3. Transition Confirmed -> Cancelled
    resp_cancel = client.patch("/api/v1/invoices/100/status", json={"status": "Cancelled"})
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "Cancelled"


def test_invoice_send_and_print(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (6, 'SUB-2026-006', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, subtotal, tax_total, discount_total, total_amount, amount_paid)
        VALUES (101, 'INV-20261101-00101', 6, 10, 'Confirmed', '2026-11-01', '2026-12-01', 500.0, 0.0, 0.0, 500.0, 0.0)
        """)
        cursor.execute("""
        INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price, tax_rate, tax_amount, line_total)
        VALUES (101, 'CRM Monthly Seat', 1, 500.0, 0.0, 0.0, 500.0)
        """)
        conn.commit()

    # Test send simulation
    resp_send = client.post("/api/v1/invoices/101/send")
    assert resp_send.status_code == 200
    assert resp_send.json()["status"] == "SENT"

    # Test print HTML
    resp_print = client.get("/api/v1/invoices/101/print")
    assert resp_print.status_code == 200
    assert "Brightloop Software" in resp_print.text
    assert "INV-20261101-00101" in resp_print.text


def test_payment_recording_and_auto_settlement(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (7, 'SUB-2026-007', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, subtotal, tax_total, discount_total, total_amount, amount_paid)
        VALUES (102, 'INV-20261101-00102', 7, 10, 'Confirmed', '2026-11-01', '2026-12-01', 1000.0, 0.0, 0.0, 1000.0, 0.0)
        """)
        conn.commit()

    # 1. Partial payment: $400
    pay1 = client.post("/api/v1/payments", json={
        "invoice_id": 102,
        "amount": 400.0,
        "payment_method": "Credit Card",
        "notes": "First installment"
    })
    assert pay1.status_code == 201
    assert pay1.json()["remaining_balance"] == 600.0
    assert pay1.json()["invoice_status"] == "Confirmed"

    # 2. Final payment: $600 -> should auto-transition invoice to 'Paid'
    pay2 = client.post("/api/v1/payments", json={
        "invoice_id": 102,
        "amount": 600.0,
        "payment_method": "Bank Transfer",
        "notes": "Final settlement"
    })
    assert pay2.status_code == 201
    assert pay2.json()["remaining_balance"] == 0.0
    assert pay2.json()["invoice_status"] == "Paid"

    # Verify invoice in DB is Paid
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, amount_paid FROM invoices WHERE id = 102")
        inv = cursor.fetchone()
        assert inv["status"] == "Paid"
        assert inv["amount_paid"] == 1000.0


def test_overdue_aging_report(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (8, 'SUB-2026-008', 10, 1, 'Active', 'Net 30', '2026-01-01')
        """)
        # Inv 1: Due 2026-10-15 (17 days overdue -> 1-30 days bucket)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, total_amount, amount_paid)
        VALUES (201, 'INV-201', 8, 10, 'Confirmed', '2026-09-15', '2026-10-15', 300.0, 0.0)
        """)
        # Inv 2: Due 2026-09-15 (47 days overdue -> 31-60 days bucket)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, total_amount, amount_paid)
        VALUES (202, 'INV-202', 8, 10, 'Confirmed', '2026-08-15', '2026-09-15', 500.0, 100.0)
        """)
        conn.commit()

    resp = client.get("/api/v1/reports/overdue?as_of_date=2026-11-01")
    assert resp.status_code == 200
    data = resp.json()

    assert data["overdue_count"] == 2
    # Inv 1 balance: 300, Inv 2 balance: 400 -> Total: 700
    assert data["total_overdue_amount"] == 700.0

    summary_map = {item["bracket"]: item for item in data["aging_summary"]}
    assert summary_map["1-30 days"]["count"] == 1
    assert summary_map["1-30 days"]["amount"] == 300.0
    assert summary_map["31-60 days"]["count"] == 1
    assert summary_map["31-60 days"]["amount"] == 400.0


def test_financial_summary_metrics(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (9, 'SUB-2026-009', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_rate, amount)
        VALUES (9, 101, 1, 1000.0, 0.0, 1000.0)
        """)
        cursor.execute("""
        INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_rate, amount)
        VALUES (9, 102, 1, 200.0, 0.0, 200.0)
        """)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, total_amount, amount_paid)
        VALUES (301, 'INV-301', 9, 10, 'Confirmed', '2026-11-01', '2026-12-01', 1200.0, 500.0)
        """)
        cursor.execute("""
        INSERT INTO payments (invoice_id, customer_id, amount, payment_method, payment_date)
        VALUES (301, 10, 500.0, 'Stripe', '2026-11-01')
        """)
        conn.commit()

    resp = client.get("/api/v1/reports/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["active_subscriptions"] == 1
    assert data["mrr"] == 1200.0
    assert data["arr"] == 14400.0
    assert data["total_revenue_collected"] == 500.0
    assert data["total_outstanding_amount"] == 700.0  # 1200 - 500


def test_customer_portal_isolation(client, temp_db):
    seed_base_entities(temp_db)
    with get_db(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (10, 'SUB-2026-010', 10, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        cursor.execute("""
        INSERT INTO subscriptions (id, subscription_number, customer_id, plan_id, status, payment_terms, start_date)
        VALUES (11, 'SUB-2026-011', 20, 1, 'Active', 'Net 30', '2026-11-01')
        """)
        # Invoice for Customer 1 (id 10)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, total_amount, amount_paid)
        VALUES (401, 'INV-401', 10, 10, 'Confirmed', '2026-11-01', '2026-12-01', 500.0, 0.0)
        """)
        # Invoice for Customer 2 (id 20)
        cursor.execute("""
        INSERT INTO invoices (id, invoice_number, subscription_id, customer_id, status, issue_date, due_date, total_amount, amount_paid)
        VALUES (402, 'INV-402', 11, 20, 'Confirmed', '2026-11-01', '2026-12-01', 900.0, 0.0)
        """)
        conn.commit()

    # Authenticated as Customer 1 (id 10)
    resp = client.get("/api/v1/portal/invoices")
    assert resp.status_code == 200
    invoices = resp.json()
    assert len(invoices) == 1
    assert invoices[0]["id"] == 401

    # Customer 1 cannot access Customer 2's invoice (returns 404)
    resp_cross = client.get("/api/v1/portal/invoices/402")
    assert resp_cross.status_code == 404
