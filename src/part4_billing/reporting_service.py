import sqlite3
import datetime
from typing import Dict, Any, Optional

def compute_financial_summary_metrics(
    conn: sqlite3.Connection,
    as_of_date_str: Optional[str] = None,
    customer_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    High-Performance Financial Analytics Engine (< 2-second SLA guarantee):
    Aggregates active subscription count, normalized MRR & ARR, cash collections,
    and outstanding Accounts Receivable balances.
    """
    cursor = conn.cursor()

    if not as_of_date_str:
        as_of_date = datetime.date.today()
        as_of_date_str = as_of_date.isoformat()
    else:
        as_of_date = datetime.date.fromisoformat(as_of_date_str.split("T")[0])
        as_of_date_str = as_of_date.isoformat()

    customer_sub_filter = "AND s.customer_id = ?" if customer_id else ""
    customer_inv_filter = "AND i.customer_id = ?" if customer_id else ""
    customer_pay_filter = "AND p.customer_id = ?" if customer_id else ""
    params_single = (customer_id,) if customer_id else ()

    # 1. Active Subscriptions Count
    query_active_subs = f"SELECT COUNT(*) FROM subscriptions s WHERE s.status = 'Active' {customer_sub_filter}"
    cursor.execute(query_active_subs, params_single)
    active_subscriptions = cursor.fetchone()[0] or 0

    # 2. Normalized Monthly Recurring Revenue (MRR) & ARR
    # Computes line totals per active subscription weighted by plan billing interval
    query_mrr = f"""
    SELECT 
        p.billing_interval,
        COALESCE(SUM(sl.amount), 0.0) AS interval_line_sum
    FROM subscriptions s
    JOIN plans p ON s.plan_id = p.id
    JOIN subscription_lines sl ON s.id = sl.subscription_id
    WHERE s.status = 'Active' {customer_sub_filter}
    GROUP BY p.billing_interval
    """
    cursor.execute(query_mrr, params_single)
    mrr_rows = cursor.fetchall()

    mrr = 0.0
    for row in mrr_rows:
        interval = (row["billing_interval"] or "MONTHLY").upper()
        amount = float(row["interval_line_sum"] or 0.0)
        if interval == "DAILY":
            mrr += amount * 30.0
        elif interval == "WEEKLY":
            mrr += amount * (52.0 / 12.0)
        elif interval == "MONTHLY":
            mrr += amount * 1.0
        elif interval == "YEARLY":
            mrr += amount / 12.0
        else:
            mrr += amount

    mrr = round(mrr, 2)
    arr = round(mrr * 12.0, 2)

    # 3. Total Cash Collections (Payments)
    query_payments = f"SELECT COALESCE(SUM(p.amount), 0.0) FROM payments p WHERE 1=1 {customer_pay_filter}"
    cursor.execute(query_payments, params_single)
    total_revenue_collected = round(float(cursor.fetchone()[0] or 0.0), 2)

    # 4. Total Invoiced Amount (Non-Cancelled)
    query_invoiced = f"SELECT COALESCE(SUM(i.total_amount), 0.0) FROM invoices i WHERE i.status != 'Cancelled' {customer_inv_filter}"
    cursor.execute(query_invoiced, params_single)
    total_invoiced_amount = round(float(cursor.fetchone()[0] or 0.0), 2)

    # 5. Total Outstanding Amount (Confirmed & Unpaid/Partially Paid)
    query_outstanding = f"""
    SELECT COALESCE(SUM(i.total_amount - i.amount_paid), 0.0), COUNT(*)
    FROM invoices i
    WHERE i.status = 'Confirmed' {customer_inv_filter}
    """
    cursor.execute(query_outstanding, params_single)
    res_outstanding = cursor.fetchone()
    total_outstanding_amount = round(float(res_outstanding[0] or 0.0), 2)
    outstanding_invoices_count = res_outstanding[1] or 0

    # 6. Total Overdue Amount (Due date < as_of_date and unpaid)
    query_overdue = f"""
    SELECT COALESCE(SUM(i.total_amount - i.amount_paid), 0.0), COUNT(*)
    FROM invoices i
    WHERE i.status != 'Paid'
      AND i.status != 'Cancelled'
      AND i.due_date < ?
      AND (i.total_amount - i.amount_paid) > 0.001
      {customer_inv_filter}
    """
    params_overdue = (as_of_date_str, customer_id) if customer_id else (as_of_date_str,)
    cursor.execute(query_overdue, params_overdue)
    res_overdue = cursor.fetchone()
    total_overdue_amount = round(float(res_overdue[0] or 0.0), 2)
    overdue_invoices_count = res_overdue[1] or 0

    # 7. Paid Invoices Count
    query_paid_count = f"SELECT COUNT(*) FROM invoices i WHERE i.status = 'Paid' {customer_inv_filter}"
    cursor.execute(query_paid_count, params_single)
    paid_invoices_count = cursor.fetchone()[0] or 0

    return {
        "active_subscriptions": active_subscriptions,
        "mrr": mrr,
        "arr": arr,
        "total_revenue_collected": total_revenue_collected,
        "total_invoiced_amount": total_invoiced_amount,
        "total_outstanding_amount": total_outstanding_amount,
        "total_overdue_amount": total_overdue_amount,
        "paid_invoices_count": paid_invoices_count,
        "outstanding_invoices_count": outstanding_invoices_count,
        "overdue_invoices_count": overdue_invoices_count,
    }
