import sqlite3
import datetime
from typing import Dict, Any, List, Optional, Tuple

def parse_iso_date(date_str: str) -> datetime.date:
    """Parse YYYY-MM-DD string to datetime.date object."""
    return datetime.date.fromisoformat(date_str.split("T")[0])

def format_iso_date(d: datetime.date) -> str:
    """Format datetime.date to YYYY-MM-DD string."""
    return d.isoformat()

def calculate_next_billing_date(current_date: datetime.date, interval: str) -> datetime.date:
    """
    Computes the next billing date based on the plan billing interval:
    - DAILY: +1 day
    - WEEKLY: +7 days
    - MONTHLY: +1 calendar month (properly handles month boundaries)
    - YEARLY: +1 calendar year (properly handles leap years)
    """
    interval_upper = interval.strip().upper()
    if interval_upper == "DAILY":
        return current_date + datetime.timedelta(days=1)
    elif interval_upper == "WEEKLY":
        return current_date + datetime.timedelta(days=7)
    elif interval_upper == "MONTHLY":
        # Handle month advancement with day clipping
        year = current_date.year + (current_date.month // 12)
        month = (current_date.month % 12) + 1
        day = current_date.day
        # Determine maximum days in target month
        if month in (4, 6, 9, 11):
            max_day = 30
        elif month == 2:
            is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
            max_day = 29 if is_leap else 28
        else:
            max_day = 31
        return datetime.date(year, month, min(day, max_day))
    elif interval_upper == "YEARLY":
        try:
            return current_date.replace(year=current_date.year + 1)
        except ValueError:
            # Handles Feb 29 leap year rolling into Feb 28
            return current_date.replace(year=current_date.year + 1, day=28)
    else:
        # Default fallback to monthly (30 days)
        return current_date + datetime.timedelta(days=30)

def parse_payment_terms_days(terms: Optional[str]) -> int:
    """Extracts payment due days from standard ERP payment terms (e.g. Net 30 -> 30)."""
    if not terms:
        return 30
    terms_clean = terms.strip().lower()
    if "immediate" in terms_clean or "receipt" in terms_clean or "net 0" in terms_clean:
        return 0
    if "net 15" in terms_clean:
        return 15
    if "net 30" in terms_clean:
        return 30
    if "net 60" in terms_clean:
        return 60
    if "net 90" in terms_clean:
        return 90
    # Try generic digit extraction
    digits = "".join(ch for ch in terms if ch.isdigit())
    if digits:
        return int(digits)
    return 30

def generate_invoice_number(conn: sqlite3.Connection, date_prefix: str) -> str:
    """Generates unique, sequenced invoice number format: INV-YYYYMMDD-00001"""
    clean_date = date_prefix.replace("-", "")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM invoices WHERE invoice_number LIKE ?",
        (f"INV-{clean_date}-%",)
    )
    count = cursor.fetchone()[0] + 1
    return f"INV-{clean_date}-{count:05d}"

def evaluate_discount_for_invoice(
    conn: sqlite3.Connection,
    discount_id: Optional[int],
    subtotal: float,
    total_quantity: int,
    run_date_obj: datetime.date
) -> Tuple[float, Optional[int]]:
    """
    Evaluates discount validity against discount_rules:
    - Active status
    - Date validity (start_date <= run_date <= end_date)
    - Max uses limit
    - Min purchase amount & min quantity
    Returns: (discount_amount, validated_rule_id_or_None)
    """
    if not discount_id:
        return 0.0, None

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM discount_rules WHERE id = ?", (discount_id,))
    rule = cursor.fetchone()
    if not rule or not rule["is_active"]:
        return 0.0, None

    # Check date range
    if rule["start_date"]:
        start_dt = parse_iso_date(rule["start_date"])
        if run_date_obj < start_dt:
            return 0.0, None
    if rule["end_date"]:
        end_dt = parse_iso_date(rule["end_date"])
        if run_date_obj > end_dt:
            return 0.0, None

    # Check max uses
    max_uses = rule["max_uses"]
    times_used = rule["times_used"] or 0
    if max_uses is not None and times_used >= max_uses:
        return 0.0, None

    # Check minimum thresholds
    min_amount = rule["min_purchase_amount"] or 0.0
    if subtotal < min_amount:
        return 0.0, None

    min_qty = rule["min_quantity"] or 0
    if total_quantity < min_qty:
        return 0.0, None

    # Calculate discount amount
    disc_type = rule["discount_type"].strip().upper()
    disc_val = float(rule["discount_value"])
    if disc_type == "PERCENTAGE":
        discount_amount = round(subtotal * (disc_val / 100.0), 2)
    else:  # FIXED
        discount_amount = round(min(subtotal, disc_val), 2)

    return discount_amount, rule["id"]

def run_recurring_billing_cycle(
    conn: sqlite3.Connection,
    run_date_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    The ZeroSkip Automated Recurring Billing Engine:
    1. Evaluates all Active subscriptions due for billing (next_billing_date <= run_date).
    2. Enforces IDEMPOTENCY: prevents duplicate invoices for the same subscription period.
    3. Builds itemized invoice lines with accurate tax & discount calculations.
    4. Automatically advances next_billing_date and updates last_billed_date.
    5. Closes expired subscriptions where auto_close is enabled.
    6. Logs the batch run into `billing_runs`.
    """
    cursor = conn.cursor()

    if not run_date_str:
        run_date_obj = datetime.date.today()
        run_date_str = format_iso_date(run_date_obj)
    else:
        run_date_obj = parse_iso_date(run_date_str)
        run_date_str = format_iso_date(run_date_obj)

    # Fetch active subscriptions due on or before run_date
    query = """
    SELECT 
        s.id AS sub_id,
        s.subscription_number,
        s.customer_id,
        s.plan_id,
        s.status,
        s.payment_terms,
        s.start_date,
        s.expiry_date,
        s.next_billing_date,
        s.last_billed_date,
        s.discount_rule_id,
        p.billing_interval,
        p.price AS plan_price,
        p.auto_close AS plan_auto_close
    FROM subscriptions s
    JOIN plans p ON s.plan_id = p.id
    WHERE s.status = 'Active'
      AND s.next_billing_date IS NOT NULL
      AND s.next_billing_date <= ?
    ORDER BY s.id ASC
    """
    cursor.execute(query, (run_date_str,))
    due_subscriptions = cursor.fetchall()

    subscriptions_evaluated = len(due_subscriptions)
    invoices_generated = 0
    total_billed_amount = 0.0

    for sub in due_subscriptions:
        sub_id = sub["sub_id"]
        cycle_start_str = sub["next_billing_date"]
        cycle_start_obj = parse_iso_date(cycle_start_str)
        interval = sub["billing_interval"]

        # Compute next cycle date and cycle end date
        next_cycle_obj = calculate_next_billing_date(cycle_start_obj, interval)
        cycle_end_obj = next_cycle_obj - datetime.timedelta(days=1)
        cycle_end_str = format_iso_date(cycle_end_obj)
        next_cycle_str = format_iso_date(next_cycle_obj)

        # IDEMPOTENCY CHECK:
        # Check if an active/valid invoice has already been issued for this subscription cycle
        cursor.execute(
            """
            SELECT id FROM invoices 
            WHERE subscription_id = ? 
              AND billing_period_start = ?
              AND status != 'Cancelled'
            """,
            (sub_id, cycle_start_str)
        )
        existing_invoice = cursor.fetchone()
        if existing_invoice:
            # Already billed for this cycle. Skip duplicate invoice generation.
            # Make sure subscription pointer is moved forward if it was lagging
            if sub["next_billing_date"] <= cycle_start_str:
                cursor.execute(
                    "UPDATE subscriptions SET next_billing_date = ?, last_billed_date = ? WHERE id = ?",
                    (next_cycle_str, cycle_start_str, sub_id)
                )
            continue

        # Fetch subscription lines
        cursor.execute(
            """
            SELECT sl.*, p.name AS product_name
            FROM subscription_lines sl
            LEFT JOIN products p ON sl.product_id = p.id
            WHERE sl.subscription_id = ?
            """,
            (sub_id,)
        )
        lines = cursor.fetchall()

        # Compute line totals, taxes, and subtotal
        subtotal = 0.0
        tax_total = 0.0
        total_quantity = 0
        computed_lines = []

        for line in lines:
            qty = line["quantity"] or 1
            unit_price = float(line["unit_price"] or 0.0)
            tax_rate = float(line["tax_rate"] or 0.0)

            line_subtotal = round(qty * unit_price, 2)
            line_tax = round(line_subtotal * (tax_rate / 100.0), 2)
            line_amount = round(line_subtotal + line_tax, 2)

            subtotal += line_subtotal
            tax_total += line_tax
            total_quantity += qty

            desc = line["product_name"] or f"Product #{line['product_id']}"
            computed_lines.append({
                "product_id": line["product_id"],
                "description": desc,
                "quantity": qty,
                "unit_price": unit_price,
                "tax_rate": tax_rate,
                "tax_amount": line_tax,
                "line_total": line_amount
            })

        # Evaluate discount rules
        discount_amount, valid_rule_id = evaluate_discount_for_invoice(
            conn,
            sub["discount_rule_id"],
            subtotal,
            total_quantity,
            run_date_obj
        )

        total_amount = max(0.0, round(subtotal + tax_total - discount_amount, 2))

        # Determine payment due date based on payment terms
        due_days = parse_payment_terms_days(sub["payment_terms"])
        due_date_obj = run_date_obj + datetime.timedelta(days=due_days)
        due_date_str = format_iso_date(due_date_obj)

        invoice_number = generate_invoice_number(conn, run_date_str)

        # Create Invoice Header in Draft status
        cursor.execute(
            """
            INSERT INTO invoices (
                invoice_number, subscription_id, customer_id, status,
                issue_date, due_date, subtotal, tax_total, discount_total,
                total_amount, amount_paid, billing_period_start, billing_period_end
            ) VALUES (?, ?, ?, 'Draft', ?, ?, ?, ?, ?, ?, 0.0, ?, ?)
            """,
            (
                invoice_number,
                sub_id,
                sub["customer_id"],
                run_date_str,
                due_date_str,
                subtotal,
                tax_total,
                discount_amount,
                total_amount,
                cycle_start_str,
                cycle_end_str
            )
        )
        invoice_id = cursor.lastrowid

        # Insert Invoice Lines
        for cline in computed_lines:
            cursor.execute(
                """
                INSERT INTO invoice_lines (
                    invoice_id, product_id, description, quantity,
                    unit_price, tax_rate, tax_amount, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    cline["product_id"],
                    cline["description"],
                    cline["quantity"],
                    cline["unit_price"],
                    cline["tax_rate"],
                    cline["tax_amount"],
                    cline["line_total"]
                )
            )

        # If discount applied, increment discount rule times_used
        if valid_rule_id:
            cursor.execute(
                "UPDATE discount_rules SET times_used = times_used + 1 WHERE id = ?",
                (valid_rule_id,)
            )

        # Advance subscription billing pointers
        # Check if subscription reaches or exceeds expiry
        new_status = "Active"
        if sub["expiry_date"]:
            expiry_obj = parse_iso_date(sub["expiry_date"])
            if next_cycle_obj > expiry_obj and sub["plan_auto_close"]:
                new_status = "Closed"

        cursor.execute(
            """
            UPDATE subscriptions 
            SET next_billing_date = ?,
                last_billed_date = ?,
                status = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (next_cycle_str, run_date_str, new_status, sub_id)
        )

        invoices_generated += 1
        total_billed_amount += total_amount

    # Log the billing run
    cursor.execute(
        """
        INSERT INTO billing_runs (
            run_date, subscriptions_evaluated, invoices_generated,
            total_billed_amount, status
        ) VALUES (?, ?, ?, ?, 'SUCCESS')
        """,
        (run_date_str, subscriptions_evaluated, invoices_generated, total_billed_amount)
    )
    billing_run_id = cursor.lastrowid

    return {
        "id": billing_run_id,
        "run_date": run_date_str,
        "subscriptions_evaluated": subscriptions_evaluated,
        "invoices_generated": invoices_generated,
        "total_billed_amount": round(total_billed_amount, 2),
        "status": "SUCCESS",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
