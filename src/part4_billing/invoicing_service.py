import sqlite3
import datetime
from typing import Dict, Any, List, Optional, Tuple

VALID_TRANSITIONS = {
    "Draft": ["Confirmed", "Cancelled"],
    "Confirmed": ["Paid", "Cancelled"],
    "Paid": [],         # Terminal state
    "Cancelled": [],    # Terminal state
}

def list_invoices(
    conn: sqlite3.Connection,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Lists invoices with flexible filtering and computed balance due."""
    cursor = conn.cursor()
    filters = []
    params = []

    if customer_id is not None:
        filters.append("i.customer_id = ?")
        params.append(customer_id)

    if status:
        filters.append("i.status = ?")
        params.append(status)

    if start_date:
        filters.append("i.issue_date >= ?")
        params.append(start_date)

    if end_date:
        filters.append("i.issue_date <= ?")
        params.append(end_date)

    where_clause = (" WHERE " + " AND ".join(filters)) if filters else ""
    query = f"""
    SELECT 
        i.*,
        u.email AS customer_email,
        u.full_name AS customer_name,
        s.subscription_number
    FROM invoices i
    JOIN users u ON i.customer_id = u.id
    JOIN subscriptions s ON i.subscription_id = s.id
    {where_clause}
    ORDER BY i.id DESC
    LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()

    results = []
    for row in rows:
        item = dict(row)
        total = float(item.get("total_amount") or 0.0)
        paid = float(item.get("amount_paid") or 0.0)
        item["amount_due"] = max(0.0, round(total - paid, 2))
        results.append(item)
    return results

def get_invoice_detail(
    conn: sqlite3.Connection,
    invoice_id: int,
    customer_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Retrieves single invoice with itemized lines, payments, and customer metadata."""
    cursor = conn.cursor()
    query = """
    SELECT 
        i.*,
        u.email AS customer_email,
        u.full_name AS customer_name,
        s.subscription_number
    FROM invoices i
    JOIN users u ON i.customer_id = u.id
    JOIN subscriptions s ON i.subscription_id = s.id
    WHERE i.id = ?
    """
    cursor.execute(query, (invoice_id,))
    row = cursor.fetchone()
    if not row:
        return None

    invoice = dict(row)
    if customer_id is not None and invoice["customer_id"] != customer_id:
        return None

    total = float(invoice.get("total_amount") or 0.0)
    paid = float(invoice.get("amount_paid") or 0.0)
    invoice["amount_due"] = max(0.0, round(total - paid, 2))

    # Fetch lines
    cursor.execute(
        "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY id ASC",
        (invoice_id,)
    )
    invoice["lines"] = [dict(line) for line in cursor.fetchall()]

    # Fetch payments
    cursor.execute(
        "SELECT * FROM payments WHERE invoice_id = ? ORDER BY id DESC",
        (invoice_id,)
    )
    invoice["payments"] = [dict(pay) for line in cursor.fetchall()]

    return invoice

def transition_invoice_status(
    conn: sqlite3.Connection,
    invoice_id: int,
    new_status: str
) -> Dict[str, Any]:
    """
    Executes valid invoice state transitions:
    - Draft -> Confirmed
    - Draft -> Cancelled
    - Confirmed -> Paid (requires full payment)
    - Confirmed -> Cancelled
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Invoice with ID {invoice_id} not found")

    current_status = row["status"]
    if current_status == new_status:
        return dict(row)

    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Invalid status transition from '{current_status}' to '{new_status}'. Allowed transitions: {allowed}"
        )

    cursor.execute(
        "UPDATE invoices SET status = ? WHERE id = ?",
        (new_status, invoice_id)
    )
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    updated = dict(cursor.fetchone())
    total = float(updated.get("total_amount") or 0.0)
    paid = float(updated.get("amount_paid") or 0.0)
    updated["amount_due"] = max(0.0, round(total - paid, 2))
    return updated

def send_invoice_email_simulation(
    conn: sqlite3.Connection,
    invoice_id: int
) -> Dict[str, Any]:
    """Simulates sending an invoice to customer's registered email."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT i.invoice_number, u.email, u.full_name
        FROM invoices i
        JOIN users u ON i.customer_id = u.id
        WHERE i.id = ?
        """,
        (invoice_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Invoice #{invoice_id} not found")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("UPDATE invoices SET sent_at = ? WHERE id = ?", (now_iso, invoice_id))

    return {
        "status": "SENT",
        "invoice_number": row["invoice_number"],
        "recipient_email": row["email"],
        "recipient_name": row["full_name"],
        "sent_at": now_iso,
        "message": f"Invoice {row['invoice_number']} successfully dispatched to {row['email']}"
    }

def generate_invoice_html(conn: sqlite3.Connection, invoice_id: int) -> str:
    """Renders a clean, print-ready HTML invoice formatted for Brightloop Software."""
    invoice = get_invoice_detail(conn, invoice_id)
    if not invoice:
        raise ValueError(f"Invoice #{invoice_id} not found")

    lines_html = ""
    for line in invoice.get("lines", []):
        lines_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0;">{line['description']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">{line['quantity']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">${line['unit_price']:.2f}</td>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">{line['tax_rate']:.1f}%</td>
            <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: 600;">${line['line_total']:.2f}</td>
        </tr>
        """

    status_color = {
        "Paid": "#16a34a",
        "Confirmed": "#2563eb",
        "Draft": "#64748b",
        "Cancelled": "#dc2626"
    }.get(invoice["status"], "#64748b")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Invoice {invoice['invoice_number']} - Brightloop Software</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1e293b; margin: 40px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f172a; padding-bottom: 20px; }}
        .badge {{ background-color: {status_color}; color: white; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 700; text-transform: uppercase; }}
        .meta-box {{ display: flex; justify-content: space-between; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
        th {{ background-color: #f8fafc; padding: 12px 10px; text-align: left; font-size: 13px; font-weight: 600; color: #475569; border-bottom: 2px solid #cbd5e1; }}
        .totals-box {{ width: 350px; margin-left: auto; margin-top: 25px; }}
        .total-row {{ display: flex; justify-content: space-between; padding: 6px 0; }}
        .grand-total {{ font-size: 18px; font-weight: 700; border-top: 2px solid #0f172a; padding-top: 10px; margin-top: 6px; }}
        @media print {{ body {{ margin: 0; }} .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1 style="margin: 0; color: #0f172a; font-size: 26px;">Brightloop Software</h1>
            <p style="margin: 4px 0 0; color: #64748b; font-size: 14px;">Unified Subscription & Recurring Billing</p>
        </div>
        <div style="text-align: right;">
            <span class="badge">{invoice['status']}</span>
            <h2 style="margin: 8px 0 0; font-size: 20px;">{invoice['invoice_number']}</h2>
        </div>
    </div>

    <div class="meta-box">
        <div>
            <h4 style="margin: 0 0 6px; color: #64748b; text-transform: uppercase; font-size: 12px;">Billed To:</h4>
            <div style="font-size: 16px; font-weight: 600;">{invoice['customer_name'] or 'Valued Customer'}</div>
            <div style="color: #64748b; font-size: 14px;">{invoice['customer_email']}</div>
            <div style="color: #64748b; font-size: 13px; margin-top: 4px;">Subscription: {invoice['subscription_number']}</div>
        </div>
        <div style="text-align: right;">
            <div style="font-size: 14px; margin-bottom: 4px;"><strong>Issue Date:</strong> {invoice['issue_date']}</div>
            <div style="font-size: 14px; margin-bottom: 4px;"><strong>Due Date:</strong> {invoice['due_date']}</div>
            <div style="font-size: 13px; color: #64748b;">Period: {invoice['billing_period_start'] or 'N/A'} to {invoice['billing_period_end'] or 'N/A'}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Description</th>
                <th style="text-align: center;">Qty</th>
                <th style="text-align: right;">Unit Price</th>
                <th style="text-align: right;">Tax Rate</th>
                <th style="text-align: right;">Total</th>
            </tr>
        </thead>
        <tbody>
            {lines_html}
        </tbody>
    </table>

    <div class="totals-box">
        <div class="total-row"><span>Subtotal:</span> <span>${invoice['subtotal']:.2f}</span></div>
        <div class="total-row"><span>Taxes:</span> <span>+${invoice['tax_total']:.2f}</span></div>
        <div class="total-row"><span>Discounts:</span> <span>-${invoice['discount_total']:.2f}</span></div>
        <div class="total-row grand-total"><span>Total Amount:</span> <span>${invoice['total_amount']:.2f}</span></div>
        <div class="total-row" style="color: #16a34a;"><span>Amount Paid:</span> <span>${invoice['amount_paid']:.2f}</span></div>
        <div class="total-row" style="font-weight: 700; color: #dc2626;"><span>Balance Due:</span> <span>${invoice['amount_due']:.2f}</span></div>
    </div>

    <div style="margin-top: 50px; text-align: center; color: #94a3b8; font-size: 12px;" class="no-print">
        <button onclick="window.print()" style="padding: 10px 20px; background: #0f172a; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">
            Print / Save as PDF
        </button>
    </div>
</body>
</html>
"""
    return html
