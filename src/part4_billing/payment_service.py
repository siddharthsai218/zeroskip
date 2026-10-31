import sqlite3
import datetime
from typing import Dict, Any, List, Optional

VALID_PAYMENT_METHODS = {"Credit Card", "Bank Transfer", "Stripe", "Cash", "Check"}

def record_invoice_payment(
    conn: sqlite3.Connection,
    invoice_id: int,
    amount: float,
    payment_method: str = "Bank Transfer",
    payment_date: Optional[str] = None,
    transaction_ref: Optional[str] = None,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Records a payment against an invoice with automatic balance settlement:
    - Enforces valid payment method
    - Verifies invoice existence and active status
    - Inserts payment transaction record
    - Updates invoice `amount_paid`
    - Automatically transitions invoice to 'Paid' if fully satisfied
    """
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValueError(
            f"Invalid payment method '{payment_method}'. Allowed methods: {sorted(list(VALID_PAYMENT_METHODS))}"
        )

    if not payment_date:
        payment_date = datetime.date.today().isoformat()
    else:
        # Validate ISO date format
        payment_date = datetime.date.fromisoformat(payment_date.split("T")[0]).isoformat()

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    invoice = cursor.fetchone()
    if not invoice:
        raise ValueError(f"Invoice with ID {invoice_id} does not exist.")

    if invoice["status"] == "Cancelled":
        raise ValueError("Cannot record payment against a Cancelled invoice.")

    customer_id = invoice["customer_id"]
    total_amount = float(invoice["total_amount"])
    current_paid = float(invoice["amount_paid"] or 0.0)

    # Insert payment record
    cursor.execute(
        """
        INSERT INTO payments (
            invoice_id, customer_id, amount, payment_method,
            payment_date, transaction_ref, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (invoice_id, customer_id, amount, payment_method, payment_date, transaction_ref, notes)
    )
    payment_id = cursor.lastrowid

    # Update invoice paid balance
    new_paid = round(current_paid + amount, 2)
    new_status = invoice["status"]

    # Auto-settle to 'Paid' if balance is fully paid off
    if new_paid >= total_amount:
        new_status = "Paid"
    elif invoice["status"] == "Draft":
        # Any payment received activates/confirms the draft
        new_status = "Confirmed"

    cursor.execute(
        "UPDATE invoices SET amount_paid = ?, status = ? WHERE id = ?",
        (new_paid, new_status, invoice_id)
    )

    # Return created payment record
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    payment_row = dict(cursor.fetchone())
    payment_row["invoice_status"] = new_status
    payment_row["remaining_balance"] = max(0.0, round(total_amount - new_paid, 2))
    return payment_row

def list_payments(
    conn: sqlite3.Connection,
    invoice_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Lists payments with optional filtering by invoice or customer."""
    cursor = conn.cursor()
    filters = []
    params = []

    if invoice_id is not None:
        filters.append("p.invoice_id = ?")
        params.append(invoice_id)

    if customer_id is not None:
        filters.append("p.customer_id = ?")
        params.append(customer_id)

    where_clause = (" WHERE " + " AND ".join(filters)) if filters else ""
    query = f"""
    SELECT 
        p.*,
        i.invoice_number,
        u.email AS customer_email,
        u.full_name AS customer_name
    FROM payments p
    JOIN invoices i ON p.invoice_id = i.id
    JOIN users u ON p.customer_id = u.id
    {where_clause}
    ORDER BY p.id DESC
    LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    cursor.execute(query, tuple(params))
    return [dict(r) for r in cursor.fetchall()]

def get_overdue_aging_report(
    conn: sqlite3.Connection,
    as_of_date_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes real-time Accounts Receivable Overdue & Aging Report:
    - Finds all uncancelled, unpaid invoices with due_date < as_of_date
    - Aggregates by aging buckets (1-30 days, 31-60 days, 61-90 days, 90+ days)
    - Returns itemized overdue records
    """
    if not as_of_date_str:
        as_of_date = datetime.date.today()
        as_of_date_str = as_of_date.isoformat()
    else:
        as_of_date = datetime.date.fromisoformat(as_of_date_str.split("T")[0])
        as_of_date_str = as_of_date.isoformat()

    cursor = conn.cursor()
    query = """
    SELECT 
        i.id AS invoice_id,
        i.invoice_number,
        i.customer_id,
        i.issue_date,
        i.due_date,
        i.total_amount,
        i.amount_paid,
        u.full_name AS customer_name,
        u.email AS customer_email
    FROM invoices i
    JOIN users u ON i.customer_id = u.id
    WHERE i.status != 'Paid' 
      AND i.status != 'Cancelled'
      AND i.due_date < ?
      AND (i.total_amount - i.amount_paid) > 0.001
    ORDER BY i.due_date ASC
    """
    cursor.execute(query, (as_of_date_str,))
    rows = cursor.fetchall()

    aging_buckets = {
        "1-30 days": {"count": 0, "amount": 0.0},
        "31-60 days": {"count": 0, "amount": 0.0},
        "61-90 days": {"count": 0, "amount": 0.0},
        "90+ days": {"count": 0, "amount": 0.0},
    }

    total_overdue = 0.0
    overdue_items = []

    for row in rows:
        due_date = datetime.date.fromisoformat(row["due_date"])
        days_overdue = max(1, (as_of_date - due_date).days)
        balance = max(0.0, round(float(row["total_amount"]) - float(row["amount_paid"]), 2))

        total_overdue += balance

        if days_overdue <= 30:
            bucket = "1-30 days"
        elif days_overdue <= 60:
            bucket = "31-60 days"
        elif days_overdue <= 90:
            bucket = "61-90 days"
        else:
            bucket = "90+ days"

        aging_buckets[bucket]["count"] += 1
        aging_buckets[bucket]["amount"] = round(aging_buckets[bucket]["amount"] + balance, 2)

        overdue_items.append({
            "invoice_id": row["invoice_id"],
            "invoice_number": row["invoice_number"],
            "customer_id": row["customer_id"],
            "customer_name": row["customer_name"],
            "customer_email": row["customer_email"],
            "issue_date": row["issue_date"],
            "due_date": row["due_date"],
            "days_overdue": days_overdue,
            "total_amount": float(row["total_amount"]),
            "amount_paid": float(row["amount_paid"]),
            "balance_due": balance,
        })

    summary_list = [
        {"bracket": k, "count": v["count"], "amount": round(v["amount"], 2)}
        for k, v in aging_buckets.items()
    ]

    return {
        "as_of_date": as_of_date_str,
        "total_overdue_amount": round(total_overdue, 2),
        "overdue_count": len(overdue_items),
        "aging_summary": summary_list,
        "overdue_invoices": overdue_items
    }
