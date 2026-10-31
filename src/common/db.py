import sqlite3
import os
from contextlib import contextmanager
from typing import Generator
from src.config import DB_PATH

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

@contextmanager
def get_db(db_path: str = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(db_path: str = DB_PATH) -> None:
    with get_db(db_path) as conn:
        cursor = conn.cursor()

        # Part 1: Users, Auth, Password Resets
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'CUSTOMER', -- 'ADMIN', 'STAFF', 'CUSTOMER'
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Part 2: Catalog, Variants, Plans, Templates, Taxes, Discounts
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            product_type TEXT NOT NULL DEFAULT 'SOFTWARE', -- 'SOFTWARE', 'ADDON', 'SERVICE'
            sales_price REAL NOT NULL DEFAULT 0.0,
            cost_price REAL NOT NULL DEFAULT 0.0,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            attribute_name TEXT NOT NULL,  -- e.g. 'Brand'
            attribute_value TEXT NOT NULL, -- e.g. 'Odoo'
            price_extra REAL NOT NULL DEFAULT 0.0, -- e.g. 560.0
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            billing_interval TEXT NOT NULL, -- 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'
            price REAL NOT NULL,
            min_quantity INTEGER NOT NULL DEFAULT 1,
            start_date TEXT,
            end_date TEXT,
            auto_close INTEGER NOT NULL DEFAULT 0,
            allow_early_close INTEGER NOT NULL DEFAULT 1,
            allow_pause INTEGER NOT NULL DEFAULT 1,
            allow_renew INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotation_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL,
            validity_days INTEGER NOT NULL DEFAULT 30,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotation_template_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL REFERENCES quotation_templates(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            variant_id INTEGER REFERENCES product_variants(id) ON DELETE SET NULL,
            quantity INTEGER NOT NULL DEFAULT 1
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tax_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rate_percent REAL NOT NULL,
            country_code TEXT DEFAULT 'GLOBAL',
            is_default INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS discount_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            discount_type TEXT NOT NULL, -- 'PERCENTAGE', 'FIXED'
            discount_value REAL NOT NULL,
            min_purchase_amount REAL DEFAULT 0.0,
            min_quantity INTEGER DEFAULT 0,
            start_date TEXT,
            end_date TEXT,
            max_uses INTEGER,
            times_used INTEGER NOT NULL DEFAULT 0,
            product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Part 3: Subscriptions Lifecycle & State Machine
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_number TEXT UNIQUE NOT NULL,
            customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'Draft', -- 'Draft', 'Quotation', 'Confirmed', 'Active', 'Paused', 'Closed'
            payment_terms TEXT NOT NULL DEFAULT 'Net 30',
            start_date TEXT NOT NULL,
            expiry_date TEXT,
            next_billing_date TEXT,
            last_billed_date TEXT,
            discount_rule_id INTEGER REFERENCES discount_rules(id) ON DELETE SET NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscription_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            variant_id INTEGER REFERENCES product_variants(id) ON DELETE SET NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            amount REAL NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscription_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
            from_status TEXT,
            to_status TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Part 4: Billing Engine, Invoices, Payments & Financial Analytics
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE RESTRICT,
            customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'Draft', -- 'Draft', 'Confirmed', 'Paid', 'Cancelled'
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            subtotal REAL NOT NULL DEFAULT 0.0,
            tax_total REAL NOT NULL DEFAULT 0.0,
            discount_total REAL NOT NULL DEFAULT 0.0,
            total_amount REAL NOT NULL DEFAULT 0.0,
            amount_paid REAL NOT NULL DEFAULT 0.0,
            billing_period_start TEXT,
            billing_period_end TEXT,
            sent_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0.0,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            tax_amount REAL NOT NULL DEFAULT 0.0,
            line_total REAL NOT NULL DEFAULT 0.0
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE RESTRICT,
            customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL, -- 'Credit Card', 'Bank Transfer', 'Stripe', 'Cash', 'Check'
            payment_date TEXT NOT NULL,
            transaction_ref TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS billing_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            subscriptions_evaluated INTEGER NOT NULL DEFAULT 0,
            invoices_generated INTEGER NOT NULL DEFAULT 0,
            total_billed_amount REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'SUCCESS',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Indexes for ultra-fast query performance (< 2s even under 100k records)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plans_code ON plans(code);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subs_customer ON subscriptions(customer_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subs_status ON subscriptions(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subs_next_billing ON subscriptions(next_billing_date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_sub ON invoices(subscription_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_due ON invoices(due_date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);")
