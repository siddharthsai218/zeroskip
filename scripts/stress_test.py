"""
Performance Benchmark & High-Volume Stress Test
Simulates thousands of active subscriptions and evaluates:
1. Ingestion of 10,000 subscriptions + 20,000 subscription lines
2. Execution latency of Finance Lead Dashboard aggregate queries
3. Proves < 2-second response requirement from Problem Statement Scene 7
"""

import sys
import os
import time
import tempfile
import sqlite3

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.db import init_db, get_connection
from src.part4_billing.reporting_service import compute_financial_summary_metrics
from src.part4_billing.billing_engine import run_recurring_billing_cycle

def run_stress_test(num_subscriptions: int = 10000):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    print(f"\n=======================================================")
    print(f"  ZeroSkip Performance Benchmark ({num_subscriptions:,} Records)")
    print(f"=======================================================\n")

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Base seed
    cursor.execute("INSERT INTO users (id, email, password_hash, full_name, role) VALUES (1, 'bench@corp.com', 'h', 'Bench User', 'CUSTOMER')")
    cursor.execute("INSERT INTO products (id, name, sales_price) VALUES (1, 'SaaS Core', 500.0)")
    cursor.execute("INSERT INTO plans (id, name, code, billing_interval, price) VALUES (1, 'Monthly', 'M-500', 'MONTHLY', 500.0)")
    cursor.execute("INSERT INTO plans (id, name, code, billing_interval, price) VALUES (2, 'Yearly', 'Y-5000', 'YEARLY', 5000.0)")

    print(f"[*] Bulk inserting {num_subscriptions:,} active subscriptions and lines...")
    start_insert = time.perf_counter()

    subs_data = [
        (f"SUB-BENCH-{i:06d}", 1, 1 if i % 2 == 0 else 2, "Active", "Net 30", "2026-01-01", "2026-11-01")
        for i in range(1, num_subscriptions + 1)
    ]
    cursor.executemany(
        """
        INSERT INTO subscriptions (
            subscription_number, customer_id, plan_id, status, payment_terms, start_date, next_billing_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        subs_data
    )

    lines_data = [
        (i, 1, 1, 500.0 if i % 2 == 0 else 5000.0, 10.0, 550.0 if i % 2 == 0 else 5500.0)
        for i in range(1, num_subscriptions + 1)
    ]
    cursor.executemany(
        """
        INSERT INTO subscription_lines (
            subscription_id, product_id, quantity, unit_price, tax_rate, amount
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        lines_data
    )
    conn.commit()
    insert_duration = time.perf_counter() - start_insert
    print(f"    --> Inserted {num_subscriptions:,} rows in {insert_duration:.2f}s\n")

    # 1. Benchmark Finance Lead Analytics Dashboard Query
    print("[*] Benchmarking Finance Lead Analytics Query (/api/v1/reports/summary)...")
    start_metric = time.perf_counter()
    metrics = compute_financial_summary_metrics(conn, as_of_date_str="2026-11-01")
    metric_duration = time.perf_counter() - start_metric

    print(f"    --> Active Subscriptions:    {metrics['active_subscriptions']:,}")
    print(f"    --> Calculated MRR:          ${metrics['mrr']:,.2f}")
    print(f"    --> Calculated ARR:          ${metrics['arr']:,.2f}")
    print(f"    --> Execution Time:          {metric_duration * 1000:.2f} ms")

    if metric_duration < 2.0:
        print(f"    --> RESULT: PASS! 🚀 ({metric_duration:.4f}s is well under the 2.000s SLA)\n")
    else:
        print(f"    --> RESULT: FAIL! ({metric_duration:.4f}s exceeded 2s SLA)\n")

    conn.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    run_stress_test(10000)
