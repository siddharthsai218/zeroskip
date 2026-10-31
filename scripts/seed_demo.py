"""
Demo Data Seeder for Brightloop Software
Seeds realistic data reflecting the exact problem statement narrative:
- Admin & Staff accounts
- Small shop and enterprise customers
- Products with the 'Odoo' brand variant (+560)
- Plans (Daily, Weekly, Monthly, Yearly)
- Quotation templates
- Discount rules and taxes
- Subscriptions in various lifecycle stages
- Billed invoices, payments, and overdue aging records
"""

import sys
import os
import datetime

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.db import init_db, get_db
from src.common.security import hash_password

def seed_demo():
    init_db()
    today = datetime.date.today()
    today_str = today.isoformat()
    yesterday_str = (today - datetime.timedelta(days=1)).isoformat()
    last_month_str = (today - datetime.timedelta(days=30)).isoformat()
    next_month_str = (today + datetime.timedelta(days=30)).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")

        # Clean slate for idempotent re-seeding
        for table in [
            "payments", "invoice_lines", "invoices", "billing_runs",
            "subscription_events", "subscription_lines", "subscriptions",
            "quotation_template_lines", "quotation_templates",
            "product_variants", "products", "plans", "discount_rules",
            "tax_rules", "password_resets", "users"
        ]:
            cursor.execute(f"DELETE FROM {table};")

        cursor.execute("PRAGMA foreign_keys = ON;")

        print("--> Seeding Brightloop Users...")
        # 1. Users (Admin, Staff, Customers)
        # Note: passwords satisfy: > 8 chars, 1 uppercase, 1 lowercase, 1 special char
        default_pwd_hash = hash_password("BrightloopPass123!")

        cursor.execute(
            """
            INSERT INTO users (email, password_hash, full_name, role) VALUES 
            ('admin@brightloop.io', ?, 'Elena Rostova (Admin)', 'ADMIN'),
            ('sales@brightloop.io', ?, 'Marcus Vance (Sales Rep)', 'STAFF'),
            ('alice@smallshop.com', ?, 'Alice Martin (Small Shop)', 'CUSTOMER'),
            ('bob@megacorp.com', ?, 'Robert Sterling (MegaCorp VP)', 'CUSTOMER')
            """,
            (default_pwd_hash, default_pwd_hash, default_pwd_hash, default_pwd_hash)
        )
        cursor.execute("SELECT id, email FROM users")
        user_map = {row["email"]: row["id"] for row in cursor.fetchall()}

        admin_id = user_map["admin@brightloop.io"]
        staff_id = user_map["sales@brightloop.io"]
        small_shop_id = user_map["alice@smallshop.com"]
        megacorp_id = user_map["bob@megacorp.com"]

        print("--> Seeding Catalog & Variants...")
        # 2. Products & Variants (including Odoo brand variant +560)
        cursor.execute(
            """
            INSERT INTO products (name, product_type, sales_price, cost_price, notes) VALUES 
            ('Brightloop ERP Core', 'SOFTWARE', 1200.0, 300.0, 'Flagship enterprise business software suite'),
            ('Analytics Pro', 'ADDON', 350.0, 50.0, 'Advanced AI-driven analytics add-on'),
            ('24/7 Premium Support', 'SERVICE', 500.0, 150.0, 'Dedicated SLA support engineer')
            """
        )
        cursor.execute("SELECT id, name FROM products")
        prod_map = {row["name"]: row["id"] for row in cursor.fetchall()}
        core_prod_id = prod_map["Brightloop ERP Core"]
        addon_prod_id = prod_map["Analytics Pro"]
        support_prod_id = prod_map["24/7 Premium Support"]

        # Variant: Brand = "Odoo" adds 560
        cursor.execute(
            """
            INSERT INTO product_variants (product_id, attribute_name, attribute_value, price_extra) VALUES
            (?, 'Brand', 'Odoo Edition', 560.0),
            (?, 'Brand', 'Standard Brightloop', 0.0)
            """,
            (core_prod_id, core_prod_id)
        )
        cursor.execute("SELECT id, attribute_value FROM product_variants WHERE product_id = ?", (core_prod_id,))
        var_map = {row["attribute_value"]: row["id"] for row in cursor.fetchall()}
        odoo_var_id = var_map["Odoo Edition"]

        print("--> Seeding Subscription Plans...")
        # 3. Plans
        cursor.execute(
            """
            INSERT INTO plans (name, code, billing_interval, price, min_quantity, auto_close, allow_early_close, allow_pause, allow_renew) VALUES
            ('Business Monthly', 'PLAN-MONTHLY-STD', 'MONTHLY', 1200.0, 1, 0, 1, 1, 1),
            ('Enterprise Annual', 'PLAN-ANNUAL-ENT', 'YEARLY', 12000.0, 5, 0, 0, 1, 1),
            ('Daily Developer Pass', 'PLAN-DAILY-TRIAL', 'DAILY', 75.0, 1, 1, 1, 0, 0)
            """
        )
        cursor.execute("SELECT id, code FROM plans")
        plan_map = {row["code"]: row["id"] for row in cursor.fetchall()}
        monthly_plan_id = plan_map["PLAN-MONTHLY-STD"]
        yearly_plan_id = plan_map["PLAN-ANNUAL-ENT"]

        print("--> Seeding Tax & Discount Rules...")
        # 4. Tax Rules
        cursor.execute(
            """
            INSERT INTO tax_rules (name, rate_percent, is_default, is_active) VALUES
            ('Global Standard VAT', 18.0, 1, 1),
            ('Zero Tax', 0.0, 0, 1)
            """
        )

        # 5. Discount Rules
        cursor.execute(
            """
            INSERT INTO discount_rules (code, name, discount_type, discount_value, min_purchase_amount, is_active, max_uses, times_used) VALUES
            ('SUMMER15', '15% Summer Discount', 'PERCENTAGE', 15.0, 500.0, 1, 100, 3),
            ('ENTERPRISE500', '$500 Enterprise Off', 'FIXED', 500.0, 2000.0, 1, 10, 1)
            """
        )
        cursor.execute("SELECT id, code FROM discount_rules WHERE code = 'SUMMER15'")
        discount_id = cursor.fetchone()["id"]

        print("--> Seeding Quotation Templates...")
        # 6. Quotation Templates
        cursor.execute(
            """
            INSERT INTO quotation_templates (name, plan_id, validity_days, notes) VALUES
            ('Enterprise Starter Offer', ?, 30, 'Includes ERP Core Odoo edition and 1 Analytics Add-on')
            """,
            (monthly_plan_id,)
        )
        template_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO quotation_template_lines (template_id, product_id, variant_id, quantity) VALUES
            (?, ?, ?, 2),
            (?, ?, NULL, 1)
            """,
            (template_id, core_prod_id, odoo_var_id, template_id, addon_prod_id)
        )

        print("--> Seeding Subscriptions & Lines...")
        # 7. Subscriptions in different lifecycle states
        # Sub 1: Active Monthly due for billing TODAY
        cursor.execute(
            """
            INSERT INTO subscriptions (
                subscription_number, customer_id, plan_id, status, payment_terms,
                start_date, next_billing_date, discount_rule_id, notes
            ) VALUES ('SUB-2026-00001', ?, ?, 'Active', 'Net 30', ?, ?, ?, 'Small shop primary subscription')
            """,
            (small_shop_id, monthly_plan_id, last_month_str, today_str, discount_id)
        )
        sub1_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO subscription_lines (subscription_id, product_id, variant_id, quantity, unit_price, tax_rate, amount) VALUES
            (?, ?, ?, 1, 1760.0, 18.0, 2076.80),
            (?, ?, NULL, 1, 350.0, 18.0, 413.00)
            """,
            (sub1_id, core_prod_id, odoo_var_id, sub1_id, addon_prod_id)
        )

        # Sub 2: Active Enterprise contract for MegaCorp
        cursor.execute(
            """
            INSERT INTO subscriptions (
                subscription_number, customer_id, plan_id, status, payment_terms,
                start_date, next_billing_date, expiry_date, notes
            ) VALUES ('SUB-2026-00002', ?, ?, 'Active', 'Net 60', ?, ?, ?, 'Annual enterprise contract')
            """,
            (megacorp_id, yearly_plan_id, last_month_str, next_month_str, next_month_str)
        )
        sub2_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO subscription_lines (subscription_id, product_id, variant_id, quantity, unit_price, tax_rate, amount) VALUES
            (?, ?, NULL, 10, 1200.0, 18.0, 14160.00),
            (?, ?, NULL, 2, 500.0, 18.0, 1180.00)
            """,
            (sub2_id, core_prod_id, sub2_id, support_prod_id)
        )

        print("--> Seeding Invoices & Payments...")
        # 8. Invoices: 1 Paid, 1 Confirmed, 1 Overdue
        # Invoice 1 (Paid)
        cursor.execute(
            """
            INSERT INTO invoices (
                invoice_number, subscription_id, customer_id, status,
                issue_date, due_date, subtotal, tax_total, discount_total,
                total_amount, amount_paid, billing_period_start, billing_period_end
            ) VALUES ('INV-20261001-00001', ?, ?, 'Paid', ?, ?, 2110.0, 379.80, 0.0, 2489.80, 2489.80, ?, ?)
            """,
            (sub1_id, small_shop_id, last_month_str, today_str, last_month_str, today_str)
        )
        inv1_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO payments (invoice_id, customer_id, amount, payment_method, payment_date, transaction_ref, notes) VALUES
            (?, ?, 2489.80, 'Stripe', ?, 'ch_3NzK81E8', 'Fully settled via Stripe')
            """,
            (inv1_id, small_shop_id, last_month_str)
        )

        # Invoice 2 (Overdue! Due 15 days ago)
        overdue_due_date = (today - datetime.timedelta(days=15)).isoformat()
        cursor.execute(
            """
            INSERT INTO invoices (
                invoice_number, subscription_id, customer_id, status,
                issue_date, due_date, subtotal, tax_total, discount_total,
                total_amount, amount_paid, billing_period_start, billing_period_end
            ) VALUES ('INV-20260915-00002', ?, ?, 'Confirmed', ?, ?, 15340.0, 2761.20, 500.0, 17601.20, 5000.0, ?, ?)
            """,
            (sub2_id, megacorp_id, last_month_str, overdue_due_date, last_month_str, overdue_due_date)
        )
        inv2_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO payments (invoice_id, customer_id, amount, payment_method, payment_date, transaction_ref, notes) VALUES
            (?, ?, 5000.0, 'Bank Transfer', ?, 'WT-881290', 'Partial downpayment')
            """,
            (inv2_id, megacorp_id, overdue_due_date)
        )

        conn.commit()

    print("\n✅ Brightloop Demo Database seeded successfully!")
    print("----------------------------------------------------------------")
    print("Demo Credentials:")
    print("  • Admin:    admin@brightloop.io   / BrightloopPass123!")
    print("  • Staff:    sales@brightloop.io   / BrightloopPass123!")
    print("  • Customer: alice@smallshop.com   / BrightloopPass123!")
    print("  • Customer: bob@megacorp.com      / BrightloopPass123!")
    print("----------------------------------------------------------------")

if __name__ == "__main__":
    seed_demo()
