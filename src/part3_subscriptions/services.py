import sqlite3
import datetime
from typing import Dict, Any, List, Optional, Tuple
from src.part3_subscriptions.schemas import (
    QuotationCreateCustom,
    QuotationCreateFromTemplate,
    SubscriptionUpdate,
    SubscriptionLineCreate,
)

VALID_SUBSCRIPTION_TRANSITIONS = {
    "Draft": ["Quotation", "Closed"],
    "Quotation": ["Confirmed", "Closed"],
    "Confirmed": ["Active", "Closed"],
    "Active": ["Paused", "Closed"],
    "Paused": ["Active", "Closed"],
    "Closed": [],  # Terminal state
}

def parse_iso_date(date_str: str) -> datetime.date:
    """Parse YYYY-MM-DD string to date object."""
    return datetime.date.fromisoformat(date_str.split("T")[0])

def format_iso_date(d: datetime.date) -> str:
    """Format date object to YYYY-MM-DD string."""
    return d.isoformat()

def generate_subscription_number(conn: sqlite3.Connection, year_prefix: Optional[int] = None) -> str:
    """Generates unique, sequenced subscription identifier (e.g. SUB-2026-00001)."""
    if not year_prefix:
        year_prefix = datetime.date.today().year
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE subscription_number LIKE ?",
        (f"SUB-{year_prefix}-%",)
    )
    count = cursor.fetchone()[0] + 1
    return f"SUB-{year_prefix}-{count:05d}"

def calculate_period_extension(
    base_date: datetime.date,
    interval: str,
    multiplier: int = 1
) -> datetime.date:
    """Calculates future date after extending by given interval multiplier."""
    interval_upper = interval.strip().upper()
    current = base_date
    for _ in range(multiplier):
        if interval_upper == "DAILY":
            current += datetime.timedelta(days=1)
        elif interval_upper == "WEEKLY":
            current += datetime.timedelta(days=7)
        elif interval_upper == "MONTHLY":
            year = current.year + (current.month // 12)
            month = (current.month % 12) + 1
            day = current.day
            if month in (4, 6, 9, 11):
                max_day = 30
            elif month == 2:
                is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
                max_day = 29 if is_leap else 28
            else:
                max_day = 31
            current = datetime.date(year, month, min(day, max_day))
        elif interval_upper == "YEARLY":
            try:
                current = current.replace(year=current.year + 1)
            except ValueError:
                current = current.replace(year=current.year + 1, day=28)
        else:
            current += datetime.timedelta(days=30)
    return current

def resolve_line_pricing(
    conn: sqlite3.Connection,
    product_id: int,
    variant_id: Optional[int] = None,
    override_price: Optional[float] = None,
    tax_rate: Optional[float] = None
) -> Tuple[float, float]:
    """
    Computes effective unit price and tax rate for a subscription line item:
    Base Product Sales Price + Variant Extra Price (if applicable).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT sales_price, is_active FROM products WHERE id = ?", (product_id,))
    prod = cursor.fetchone()
    if not prod:
        raise ValueError(f"Product #{product_id} does not exist.")
    if not prod["is_active"]:
        raise ValueError(f"Product #{product_id} is inactive.")

    if override_price is not None:
        unit_price = float(override_price)
    else:
        unit_price = float(prod["sales_price"])
        if variant_id:
            cursor.execute(
                "SELECT price_extra FROM product_variants WHERE id = ? AND product_id = ?",
                (variant_id, product_id)
            )
            v = cursor.fetchone()
            if not v:
                raise ValueError(f"Variant #{variant_id} does not belong to product #{product_id}.")
            unit_price += float(v["price_extra"] or 0.0)

    # Determine tax rate
    if tax_rate is not None and tax_rate > 0.0:
        eff_tax = float(tax_rate)
    else:
        cursor.execute("SELECT rate_percent FROM tax_rules WHERE is_default = 1 AND is_active = 1 LIMIT 1")
        default_tax = cursor.fetchone()
        eff_tax = float(default_tax["rate_percent"]) if default_tax else 0.0

    return round(unit_price, 2), round(eff_tax, 2)

def log_subscription_event(
    conn: sqlite3.Connection,
    subscription_id: int,
    from_status: Optional[str],
    to_status: str,
    user_id: Optional[int] = None,
    reason: Optional[str] = None
) -> None:
    """Records state transition audit record in subscription_events."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO subscription_events (subscription_id, from_status, to_status, user_id, reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (subscription_id, from_status, to_status, user_id, reason)
    )

def create_quotation_from_template(
    conn: sqlite3.Connection,
    data: QuotationCreateFromTemplate,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Instantiates a new quotation/subscription from a pre-configured template:
    - Verifies template and customer
    - Computes expiration date from template validity duration
    - Pre-fills itemized lines with catalog pricing
    - Initial status: 'Draft'
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (data.customer_id,))
    customer = cursor.fetchone()
    if not customer:
        raise ValueError(f"Customer #{data.customer_id} does not exist.")

    cursor.execute("SELECT * FROM quotation_templates WHERE id = ?", (data.template_id,))
    template = cursor.fetchone()
    if not template:
        raise ValueError(f"Quotation template #{data.template_id} does not exist.")

    plan_id = template["plan_id"]
    if not plan_id:
        raise ValueError("Quotation template is not associated with an active subscription plan.")

    cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    plan = cursor.fetchone()
    if not plan or not plan["is_active"]:
        raise ValueError("Plan associated with quotation template is inactive or missing.")

    start_date_obj = parse_iso_date(data.start_date) if data.start_date else datetime.date.today()
    start_date_str = format_iso_date(start_date_obj)

    # Expiry based on template validity days
    validity_days = template["validity_days"] or 30
    expiry_date_obj = start_date_obj + datetime.timedelta(days=validity_days)
    expiry_date_str = format_iso_date(expiry_date_obj)

    sub_number = generate_subscription_number(conn, start_date_obj.year)

    cursor.execute(
        """
        INSERT INTO subscriptions (
            subscription_number, customer_id, plan_id, status,
            payment_terms, start_date, expiry_date, next_billing_date,
            discount_rule_id, notes
        ) VALUES (?, ?, ?, 'Draft', ?, ?, ?, ?, ?, ?)
        """,
        (
            sub_number,
            data.customer_id,
            plan_id,
            data.payment_terms,
            start_date_str,
            expiry_date_str,
            start_date_str,
            data.discount_rule_id,
            data.notes or template["notes"]
        )
    )
    sub_id = cursor.lastrowid

    # Populate lines from template lines
    cursor.execute(
        "SELECT * FROM quotation_template_lines WHERE template_id = ?",
        (data.template_id,)
    )
    tlines = cursor.fetchall()

    for tl in tlines:
        unit_price, tax_rate = resolve_line_pricing(
            conn,
            tl["product_id"],
            tl["variant_id"]
        )
        qty = tl["quantity"] or 1
        line_subtotal = round(qty * unit_price, 2)
        line_tax = round(line_subtotal * (tax_rate / 100.0), 2)
        total_line_amount = round(line_subtotal + line_tax, 2)

        cursor.execute(
            """
            INSERT INTO subscription_lines (
                subscription_id, product_id, variant_id, quantity,
                unit_price, tax_rate, amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sub_id,
                tl["product_id"],
                tl["variant_id"],
                qty,
                unit_price,
                tax_rate,
                total_line_amount
            )
        )

    log_subscription_event(
        conn,
        sub_id,
        from_status=None,
        to_status="Draft",
        user_id=user_id,
        reason=f"Created quotation from template '{template['name']}'"
    )

    return get_subscription_detail(conn, sub_id)

def create_custom_quotation(
    conn: sqlite3.Connection,
    data: QuotationCreateCustom,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """Creates a custom quote / subscription with tailored line items."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (data.customer_id,))
    if not cursor.fetchone():
        raise ValueError(f"Customer #{data.customer_id} does not exist.")

    cursor.execute("SELECT * FROM plans WHERE id = ?", (data.plan_id,))
    plan = cursor.fetchone()
    if not plan or not plan["is_active"]:
        raise ValueError(f"Plan #{data.plan_id} does not exist or is inactive.")

    start_date_obj = parse_iso_date(data.start_date) if data.start_date else datetime.date.today()
    start_date_str = format_iso_date(start_date_obj)

    if data.expiry_date:
        expiry_date_str = format_iso_date(parse_iso_date(data.expiry_date))
    else:
        # Default expiry = 1 billing cycle ahead
        expiry_obj = calculate_period_extension(start_date_obj, plan["billing_interval"])
        expiry_date_str = format_iso_date(expiry_obj)

    sub_number = generate_subscription_number(conn, start_date_obj.year)

    cursor.execute(
        """
        INSERT INTO subscriptions (
            subscription_number, customer_id, plan_id, status,
            payment_terms, start_date, expiry_date, next_billing_date,
            discount_rule_id, notes
        ) VALUES (?, ?, ?, 'Draft', ?, ?, ?, ?, ?, ?)
        """,
        (
            sub_number,
            data.customer_id,
            data.plan_id,
            data.payment_terms,
            start_date_str,
            expiry_date_str,
            start_date_str,
            data.discount_rule_id,
            data.notes
        )
    )
    sub_id = cursor.lastrowid

    # Insert lines
    for item in data.lines:
        unit_price, tax_rate = resolve_line_pricing(
            conn,
            item.product_id,
            item.variant_id,
            override_price=item.unit_price,
            tax_rate=item.tax_rate
        )
        qty = item.quantity
        line_subtotal = round(qty * unit_price, 2)
        line_tax = round(line_subtotal * (tax_rate / 100.0), 2)
        total_line_amount = round(line_subtotal + line_tax, 2)

        cursor.execute(
            """
            INSERT INTO subscription_lines (
                subscription_id, product_id, variant_id, quantity,
                unit_price, tax_rate, amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sub_id,
                item.product_id,
                item.variant_id,
                qty,
                unit_price,
                tax_rate,
                total_line_amount
            )
        )

    log_subscription_event(
        conn,
        sub_id,
        from_status=None,
        to_status="Draft",
        user_id=user_id,
        reason="Created custom subscription quote"
    )

    return get_subscription_detail(conn, sub_id)

def list_subscriptions(
    conn: sqlite3.Connection,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    plan_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Lists subscriptions with filtering and recurring line totals."""
    cursor = conn.cursor()
    filters = []
    params = []

    if customer_id is not None:
        filters.append("s.customer_id = ?")
        params.append(customer_id)

    if status:
        filters.append("s.status = ?")
        params.append(status)

    if plan_id is not None:
        filters.append("s.plan_id = ?")
        params.append(plan_id)

    where_clause = (" WHERE " + " AND ".join(filters)) if filters else ""
    query = f"""
    SELECT 
        s.*,
        u.email AS customer_email,
        u.full_name AS customer_name,
        p.name AS plan_name,
        p.code AS plan_code,
        p.billing_interval,
        COALESCE((SELECT SUM(sl.amount) FROM subscription_lines sl WHERE sl.subscription_id = s.id), 0.0) AS total_recurring_amount
    FROM subscriptions s
    JOIN users u ON s.customer_id = u.id
    JOIN plans p ON s.plan_id = p.id
    {where_clause}
    ORDER BY s.id DESC
    LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    cursor.execute(query, tuple(params))
    return [dict(r) for r in cursor.fetchall()]

def get_subscription_detail(
    conn: sqlite3.Connection,
    subscription_id: int,
    customer_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Retrieves single subscription with itemized lines, audit events, and plan policy flags."""
    cursor = conn.cursor()
    query = """
    SELECT 
        s.*,
        u.email AS customer_email,
        u.full_name AS customer_name,
        p.name AS plan_name,
        p.code AS plan_code,
        p.billing_interval,
        p.allow_pause,
        p.allow_early_close,
        p.allow_renew,
        p.auto_close
    FROM subscriptions s
    JOIN users u ON s.customer_id = u.id
    JOIN plans p ON s.plan_id = p.id
    WHERE s.id = ?
    """
    cursor.execute(query, (subscription_id,))
    row = cursor.fetchone()
    if not row:
        return None

    sub = dict(row)
    if customer_id is not None and sub["customer_id"] != customer_id:
        return None

    # Attach policies dictionary
    sub["plan_policies"] = {
        "allow_pause": bool(sub.pop("allow_pause", 1)),
        "allow_early_close": bool(sub.pop("allow_early_close", 1)),
        "allow_renew": bool(sub.pop("allow_renew", 1)),
        "auto_close": bool(sub.pop("auto_close", 0)),
    }

    # Fetch lines
    cursor.execute(
        """
        SELECT 
            sl.*,
            p.name AS product_name,
            pv.attribute_value AS variant_name
        FROM subscription_lines sl
        JOIN products p ON sl.product_id = p.id
        LEFT JOIN product_variants pv ON sl.variant_id = pv.id
        WHERE sl.subscription_id = ?
        ORDER BY sl.id ASC
        """,
        (subscription_id,)
    )
    lines = [dict(lr) for lr in cursor.fetchall()]
    sub["lines"] = lines
    sub["total_recurring_amount"] = round(sum(l["amount"] for l in lines), 2)

    # Fetch audit events
    cursor.execute(
        "SELECT * FROM subscription_events WHERE subscription_id = ? ORDER BY id ASC",
        (subscription_id,)
    )
    sub["events"] = [dict(er) for er in cursor.fetchall()]

    return sub

def transition_subscription_status(
    conn: sqlite3.Connection,
    subscription_id: int,
    target_status: str,
    user_id: Optional[int] = None,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes valid subscription state transitions:
    - Draft -> Quotation
    - Quotation -> Confirmed
    - Confirmed -> Active (ensures next_billing_date is set)
    - Active -> Paused (checks allow_pause)
    - Paused -> Active (resumes)
    - Active -> Closed (checks allow_early_close)
    """
    cursor = conn.cursor()
    sub = get_subscription_detail(conn, subscription_id)
    if not sub:
        raise ValueError(f"Subscription #{subscription_id} not found.")

    current_status = sub["status"]
    if current_status == target_status:
        return sub

    allowed = VALID_SUBSCRIPTION_TRANSITIONS.get(current_status, [])
    if target_status not in allowed:
        raise ValueError(
            f"Invalid transition from '{current_status}' to '{target_status}'. Allowed transitions: {allowed}"
        )

    # Policy checks
    policies = sub.get("plan_policies", {})
    if target_status == "Paused" and not policies.get("allow_pause", True):
        raise ValueError("The subscription's plan does not permit pausing.")

    if target_status == "Closed" and current_status == "Active":
        # Early close check
        today = datetime.date.today()
        if sub["expiry_date"]:
            exp_date = parse_iso_date(sub["expiry_date"])
            if today < exp_date and not policies.get("allow_early_close", True):
                raise ValueError("The subscription's plan does not permit early closure.")

    # When transitioning to Active, set next_billing_date to start_date if not set
    next_billing = sub["next_billing_date"]
    if target_status == "Active" and not next_billing:
        next_billing = sub["start_date"]

    cursor.execute(
        """
        UPDATE subscriptions 
        SET status = ?,
            next_billing_date = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (target_status, next_billing, subscription_id)
    )

    log_subscription_event(
        conn,
        subscription_id,
        from_status=current_status,
        to_status=target_status,
        user_id=user_id,
        reason=reason or f"Status changed from {current_status} to {target_status}"
    )

    return get_subscription_detail(conn, subscription_id)

def renew_subscription(
    conn: sqlite3.Connection,
    subscription_id: int,
    extension_periods: int = 1,
    user_id: Optional[int] = None,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extends subscription expiry date according to plan interval policy:
    Requires plan allow_renew == 1.
    """
    cursor = conn.cursor()
    sub = get_subscription_detail(conn, subscription_id)
    if not sub:
        raise ValueError(f"Subscription #{subscription_id} not found.")

    if sub["status"] not in ("Active", "Closed"):
        raise ValueError(f"Cannot renew subscription in '{sub['status']}' status.")

    policies = sub.get("plan_policies", {})
    if not policies.get("allow_renew", True):
        raise ValueError("The subscription's plan does not permit renewal.")

    # Determine base date to extend from
    if sub["expiry_date"]:
        base_date = parse_iso_date(sub["expiry_date"])
    else:
        base_date = datetime.date.today()

    interval = sub["billing_interval"]
    new_expiry_obj = calculate_period_extension(base_date, interval, extension_periods)
    new_expiry_str = format_iso_date(new_expiry_obj)

    # If previously closed, re-activate
    new_status = "Active" if sub["status"] == "Closed" else sub["status"]

    cursor.execute(
        """
        UPDATE subscriptions 
        SET expiry_date = ?,
            status = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (new_expiry_str, new_status, subscription_id)
    )

    log_subscription_event(
        conn,
        subscription_id,
        from_status=sub["status"],
        to_status=new_status,
        user_id=user_id,
        reason=reason or f"Renewed for {extension_periods} period(s). New expiry: {new_expiry_str}"
    )

    return get_subscription_detail(conn, subscription_id)
