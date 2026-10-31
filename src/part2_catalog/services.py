import sqlite3
import datetime
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, status
from src.part2_catalog.schemas import (
    ProductCreate, ProductUpdate,
    ProductVariantCreate, ProductVariantUpdate,
    PlanCreate, PlanUpdate,
    QuotationTemplateCreate, QuotationTemplateUpdate, QuotationTemplateLineCreate,
    TaxRuleCreate, TaxRuleUpdate,
    DiscountRuleCreate, DiscountRuleUpdate,
)

# ----------------- Helper Functions -----------------

def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)

# ----------------- Product & Variant Services -----------------

def create_product(conn: sqlite3.Connection, data: ProductCreate) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name, product_type, sales_price, cost_price, notes, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data.name,
        data.product_type,
        data.sales_price,
        data.cost_price,
        data.notes,
        1 if data.is_active else 0
    ))
    product_id = cursor.lastrowid
    return get_product(conn, product_id, include_variants=True)

def get_product(conn: sqlite3.Connection, product_id: int, include_variants: bool = True) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    if not row:
        return None
    res = dict(row)
    res["is_active"] = bool(res["is_active"])
    if include_variants:
        res["variants"] = list_variants(conn, product_id)
    else:
        res["variants"] = []
    return res

def list_products(
    conn: sqlite3.Connection,
    is_active: Optional[bool] = None,
    product_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    query = "SELECT * FROM products WHERE 1=1"
    params: List[Any] = []

    if is_active is not None:
        query += " AND is_active = ?"
        params.append(1 if is_active else 0)
    if product_type is not None:
        query += " AND product_type = ?"
        params.append(product_type)
    if search:
        query += " AND (name LIKE ? OR notes LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["is_active"] = bool(d["is_active"])
        d["variants"] = list_variants(conn, d["id"])
        results.append(d)
    return results

def update_product(conn: sqlite3.Connection, product_id: int, data: ProductUpdate) -> Optional[Dict[str, Any]]:
    existing = get_product(conn, product_id, include_variants=False)
    if not existing:
        return None

    update_fields = []
    params: List[Any] = []

    if data.name is not None:
        update_fields.append("name = ?")
        params.append(data.name)
    if data.product_type is not None:
        update_fields.append("product_type = ?")
        params.append(data.product_type)
    if data.sales_price is not None:
        update_fields.append("sales_price = ?")
        params.append(data.sales_price)
    if data.cost_price is not None:
        update_fields.append("cost_price = ?")
        params.append(data.cost_price)
    if data.notes is not None:
        update_fields.append("notes = ?")
        params.append(data.notes)
    if data.is_active is not None:
        update_fields.append("is_active = ?")
        params.append(1 if data.is_active else 0)

    if update_fields:
        query = f"UPDATE products SET {', '.join(update_fields)} WHERE id = ?"
        params.append(product_id)
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_product(conn, product_id, include_variants=True)

def delete_product(conn: sqlite3.Connection, product_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return cursor.rowcount > 0

def create_variant(conn: sqlite3.Connection, product_id: int, data: ProductVariantCreate) -> Dict[str, Any]:
    prod = get_product(conn, product_id, include_variants=False)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO product_variants (product_id, attribute_name, attribute_value, price_extra)
        VALUES (?, ?, ?, ?)
    """, (
        product_id,
        data.attribute_name,
        data.attribute_value,
        data.price_extra
    ))
    variant_id = cursor.lastrowid
    return get_variant(conn, variant_id)

def get_variant(conn: sqlite3.Connection, variant_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM product_variants WHERE id = ?", (variant_id,))
    row = cursor.fetchone()
    return _row_to_dict(row)

def list_variants(conn: sqlite3.Connection, product_id: int) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM product_variants WHERE product_id = ? ORDER BY id ASC", (product_id,))
    return [dict(r) for r in cursor.fetchall()]

def update_variant(conn: sqlite3.Connection, variant_id: int, data: ProductVariantUpdate) -> Optional[Dict[str, Any]]:
    existing = get_variant(conn, variant_id)
    if not existing:
        return None

    update_fields = []
    params: List[Any] = []

    if data.attribute_name is not None:
        update_fields.append("attribute_name = ?")
        params.append(data.attribute_name)
    if data.attribute_value is not None:
        update_fields.append("attribute_value = ?")
        params.append(data.attribute_value)
    if data.price_extra is not None:
        update_fields.append("price_extra = ?")
        params.append(data.price_extra)

    if update_fields:
        query = f"UPDATE product_variants SET {', '.join(update_fields)} WHERE id = ?"
        params.append(variant_id)
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_variant(conn, variant_id)

def delete_variant(conn: sqlite3.Connection, variant_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM product_variants WHERE id = ?", (variant_id,))
    return cursor.rowcount > 0

# ----------------- Subscription Plan Services -----------------

def create_plan(conn: sqlite3.Connection, data: PlanCreate) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM plans WHERE code = ?", (data.code,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan code '{data.code}' already exists"
        )

    cursor.execute("""
        INSERT INTO plans (
            name, code, billing_interval, price, min_quantity,
            start_date, end_date, auto_close, allow_early_close,
            allow_pause, allow_renew, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.name,
        data.code,
        data.billing_interval,
        data.price,
        data.min_quantity,
        data.start_date,
        data.end_date,
        1 if data.auto_close else 0,
        1 if data.allow_early_close else 0,
        1 if data.allow_pause else 0,
        1 if data.allow_renew else 0,
        1 if data.is_active else 0
    ))
    plan_id = cursor.lastrowid
    return get_plan(conn, plan_id)

def get_plan(conn: sqlite3.Connection, plan_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["auto_close"] = bool(d["auto_close"])
    d["allow_early_close"] = bool(d["allow_early_close"])
    d["allow_pause"] = bool(d["allow_pause"])
    d["allow_renew"] = bool(d["allow_renew"])
    d["is_active"] = bool(d["is_active"])
    return d

def get_plan_by_code(conn: sqlite3.Connection, code: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans WHERE code = ?", (code,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["auto_close"] = bool(d["auto_close"])
    d["allow_early_close"] = bool(d["allow_early_close"])
    d["allow_pause"] = bool(d["allow_pause"])
    d["allow_renew"] = bool(d["allow_renew"])
    d["is_active"] = bool(d["is_active"])
    return d

def list_plans(
    conn: sqlite3.Connection,
    is_active: Optional[bool] = None,
    billing_interval: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    query = "SELECT * FROM plans WHERE 1=1"
    params: List[Any] = []

    if is_active is not None:
        query += " AND is_active = ?"
        params.append(1 if is_active else 0)
    if billing_interval is not None:
        query += " AND billing_interval = ?"
        params.append(billing_interval)

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    results = []
    for r in cursor.fetchall():
        d = dict(r)
        d["auto_close"] = bool(d["auto_close"])
        d["allow_early_close"] = bool(d["allow_early_close"])
        d["allow_pause"] = bool(d["allow_pause"])
        d["allow_renew"] = bool(d["allow_renew"])
        d["is_active"] = bool(d["is_active"])
        results.append(d)
    return results

def update_plan(conn: sqlite3.Connection, plan_id: int, data: PlanUpdate) -> Optional[Dict[str, Any]]:
    existing = get_plan(conn, plan_id)
    if not existing:
        return None

    if data.code is not None and data.code != existing["code"]:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM plans WHERE code = ? AND id != ?", (data.code, plan_id))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Plan code '{data.code}' already exists"
            )

    update_fields = []
    params: List[Any] = []

    field_map = {
        "name": data.name,
        "code": data.code,
        "billing_interval": data.billing_interval,
        "price": data.price,
        "min_quantity": data.min_quantity,
        "start_date": data.start_date,
        "end_date": data.end_date,
    }
    for k, v in field_map.items():
        if v is not None:
            update_fields.append(f"{k} = ?")
            params.append(v)

    bool_fields = {
        "auto_close": data.auto_close,
        "allow_early_close": data.allow_early_close,
        "allow_pause": data.allow_pause,
        "allow_renew": data.allow_renew,
        "is_active": data.is_active,
    }
    for k, v in bool_fields.items():
        if v is not None:
            update_fields.append(f"{k} = ?")
            params.append(1 if v else 0)

    if update_fields:
        query = f"UPDATE plans SET {', '.join(update_fields)} WHERE id = ?"
        params.append(plan_id)
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_plan(conn, plan_id)

def delete_plan(conn: sqlite3.Connection, plan_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    return cursor.rowcount > 0

# ----------------- Quotation Template Services -----------------

def create_template(conn: sqlite3.Connection, data: QuotationTemplateCreate) -> Dict[str, Any]:
    cursor = conn.cursor()
    if data.plan_id is not None:
        cursor.execute("SELECT id FROM plans WHERE id = ?", (data.plan_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    cursor.execute("""
        INSERT INTO quotation_templates (name, plan_id, validity_days, notes)
        VALUES (?, ?, ?, ?)
    """, (
        data.name,
        data.plan_id,
        data.validity_days,
        data.notes
    ))
    template_id = cursor.lastrowid

    for line in data.lines:
        add_template_line(conn, template_id, line)

    return get_template(conn, template_id)

def add_template_line(conn: sqlite3.Connection, template_id: int, line: QuotationTemplateLineCreate) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM products WHERE id = ?", (line.product_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {line.product_id} not found")

    if line.variant_id is not None:
        cursor.execute("SELECT id FROM product_variants WHERE id = ? AND product_id = ?", (line.variant_id, line.product_id))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant {line.variant_id} does not belong to product {line.product_id}"
            )

    cursor.execute("""
        INSERT INTO quotation_template_lines (template_id, product_id, variant_id, quantity)
        VALUES (?, ?, ?, ?)
    """, (
        template_id,
        line.product_id,
        line.variant_id,
        line.quantity
    ))
    line_id = cursor.lastrowid
    return get_template_line(conn, line_id)

def get_template_line(conn: sqlite3.Connection, line_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT qtl.id, qtl.template_id, qtl.product_id, qtl.variant_id, qtl.quantity,
               p.name AS product_name, p.sales_price AS product_sales_price,
               pv.attribute_name, pv.attribute_value, pv.price_extra
        FROM quotation_template_lines qtl
        JOIN products p ON qtl.product_id = p.id
        LEFT JOIN product_variants pv ON qtl.variant_id = pv.id
        WHERE qtl.id = ?
    """, (line_id,))
    row = cursor.fetchone()
    return _row_to_dict(row)

def get_template(conn: sqlite3.Connection, template_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT qt.id, qt.name, qt.plan_id, qt.validity_days, qt.notes, qt.created_at,
               p.name AS plan_name
        FROM quotation_templates qt
        LEFT JOIN plans p ON qt.plan_id = p.id
        WHERE qt.id = ?
    """, (template_id,))
    row = cursor.fetchone()
    if not row:
        return None
    res = dict(row)

    cursor.execute("""
        SELECT qtl.id, qtl.template_id, qtl.product_id, qtl.variant_id, qtl.quantity,
               p.name AS product_name, p.sales_price AS product_sales_price,
               pv.attribute_name, pv.attribute_value, pv.price_extra
        FROM quotation_template_lines qtl
        JOIN products p ON qtl.product_id = p.id
        LEFT JOIN product_variants pv ON qtl.variant_id = pv.id
        WHERE qtl.template_id = ?
        ORDER BY qtl.id ASC
    """, (template_id,))
    res["lines"] = [dict(lr) for lr in cursor.fetchall()]
    return res

def list_templates(conn: sqlite3.Connection, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT qt.id, qt.name, qt.plan_id, qt.validity_days, qt.notes, qt.created_at,
               p.name AS plan_name
        FROM quotation_templates qt
        LEFT JOIN plans p ON qt.plan_id = p.id
        ORDER BY qt.id DESC LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = cursor.fetchall()
    templates = []
    for r in rows:
        tid = r["id"]
        t_dict = dict(r)
        cursor.execute("""
            SELECT qtl.id, qtl.template_id, qtl.product_id, qtl.variant_id, qtl.quantity,
                   p.name AS product_name, p.sales_price AS product_sales_price,
                   pv.attribute_name, pv.attribute_value, pv.price_extra
            FROM quotation_template_lines qtl
            JOIN products p ON qtl.product_id = p.id
            LEFT JOIN product_variants pv ON qtl.variant_id = pv.id
            WHERE qtl.template_id = ?
            ORDER BY qtl.id ASC
        """, (tid,))
        t_dict["lines"] = [dict(lr) for lr in cursor.fetchall()]
        templates.append(t_dict)
    return templates

def update_template(conn: sqlite3.Connection, template_id: int, data: QuotationTemplateUpdate) -> Optional[Dict[str, Any]]:
    existing = get_template(conn, template_id)
    if not existing:
        return None

    update_fields = []
    params: List[Any] = []

    if data.name is not None:
        update_fields.append("name = ?")
        params.append(data.name)
    if data.plan_id is not None:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM plans WHERE id = ?", (data.plan_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
        update_fields.append("plan_id = ?")
        params.append(data.plan_id)
    if data.validity_days is not None:
        update_fields.append("validity_days = ?")
        params.append(data.validity_days)
    if data.notes is not None:
        update_fields.append("notes = ?")
        params.append(data.notes)

    cursor = conn.cursor()
    if update_fields:
        query = f"UPDATE quotation_templates SET {', '.join(update_fields)} WHERE id = ?"
        params.append(template_id)
        cursor.execute(query, params)

    if data.lines is not None:
        cursor.execute("DELETE FROM quotation_template_lines WHERE template_id = ?", (template_id,))
        for line in data.lines:
            add_template_line(conn, template_id, line)

    return get_template(conn, template_id)

def delete_template(conn: sqlite3.Connection, template_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM quotation_templates WHERE id = ?", (template_id,))
    return cursor.rowcount > 0

def remove_template_line(conn: sqlite3.Connection, line_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM quotation_template_lines WHERE id = ?", (line_id,))
    return cursor.rowcount > 0

# ----------------- Tax Rule Services -----------------

def create_tax_rule(conn: sqlite3.Connection, data: TaxRuleCreate) -> Dict[str, Any]:
    cursor = conn.cursor()
    if data.is_default:
        cursor.execute("UPDATE tax_rules SET is_default = 0 WHERE country_code = ?", (data.country_code,))

    cursor.execute("""
        INSERT INTO tax_rules (name, rate_percent, country_code, is_default, is_active)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data.name,
        data.rate_percent,
        data.country_code,
        1 if data.is_default else 0,
        1 if data.is_active else 0
    ))
    tax_id = cursor.lastrowid
    return get_tax_rule(conn, tax_id)

def get_tax_rule(conn: sqlite3.Connection, tax_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tax_rules WHERE id = ?", (tax_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_default"] = bool(d["is_default"])
    d["is_active"] = bool(d["is_active"])
    return d

def get_default_tax_rule(conn: sqlite3.Connection, country_code: Optional[str] = "GLOBAL") -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    if country_code:
        cursor.execute(
            "SELECT * FROM tax_rules WHERE country_code = ? AND is_default = 1 AND is_active = 1 LIMIT 1",
            (country_code,)
        )
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["is_default"] = bool(d["is_default"])
            d["is_active"] = bool(d["is_active"])
            return d

    cursor.execute("SELECT * FROM tax_rules WHERE is_default = 1 AND is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_default"] = bool(d["is_default"])
    d["is_active"] = bool(d["is_active"])
    return d

def list_tax_rules(
    conn: sqlite3.Connection,
    is_active: Optional[bool] = None,
    country_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    query = "SELECT * FROM tax_rules WHERE 1=1"
    params: List[Any] = []

    if is_active is not None:
        query += " AND is_active = ?"
        params.append(1 if is_active else 0)
    if country_code is not None:
        query += " AND country_code = ?"
        params.append(country_code)

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    results = []
    for r in cursor.fetchall():
        d = dict(r)
        d["is_default"] = bool(d["is_default"])
        d["is_active"] = bool(d["is_active"])
        results.append(d)
    return results

def update_tax_rule(conn: sqlite3.Connection, tax_id: int, data: TaxRuleUpdate) -> Optional[Dict[str, Any]]:
    existing = get_tax_rule(conn, tax_id)
    if not existing:
        return None

    if data.is_default:
        country = data.country_code or existing["country_code"]
        cursor = conn.cursor()
        cursor.execute("UPDATE tax_rules SET is_default = 0 WHERE country_code = ? AND id != ?", (country, tax_id))

    update_fields = []
    params: List[Any] = []

    if data.name is not None:
        update_fields.append("name = ?")
        params.append(data.name)
    if data.rate_percent is not None:
        update_fields.append("rate_percent = ?")
        params.append(data.rate_percent)
    if data.country_code is not None:
        update_fields.append("country_code = ?")
        params.append(data.country_code)
    if data.is_default is not None:
        update_fields.append("is_default = ?")
        params.append(1 if data.is_default else 0)
    if data.is_active is not None:
        update_fields.append("is_active = ?")
        params.append(1 if data.is_active else 0)

    if update_fields:
        query = f"UPDATE tax_rules SET {', '.join(update_fields)} WHERE id = ?"
        params.append(tax_id)
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_tax_rule(conn, tax_id)

def delete_tax_rule(conn: sqlite3.Connection, tax_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tax_rules WHERE id = ?", (tax_id,))
    return cursor.rowcount > 0

# ----------------- Discount Rule Services -----------------

def create_discount_rule(conn: sqlite3.Connection, data: DiscountRuleCreate) -> Dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM discount_rules WHERE code = ?", (data.code,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Discount code '{data.code}' already exists"
        )

    if data.product_id is not None:
        cursor.execute("SELECT id FROM products WHERE id = ?", (data.product_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target product not found")

    cursor.execute("""
        INSERT INTO discount_rules (
            code, name, discount_type, discount_value,
            min_purchase_amount, min_quantity, start_date, end_date,
            max_uses, times_used, product_id, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
    """, (
        data.code,
        data.name,
        data.discount_type,
        data.discount_value,
        data.min_purchase_amount,
        data.min_quantity,
        data.start_date,
        data.end_date,
        data.max_uses,
        data.product_id,
        1 if data.is_active else 0
    ))
    discount_id = cursor.lastrowid
    return get_discount_rule(conn, discount_id)

def get_discount_rule(conn: sqlite3.Connection, discount_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM discount_rules WHERE id = ?", (discount_id,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(d["is_active"])
    return d

def get_discount_rule_by_code(conn: sqlite3.Connection, code: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM discount_rules WHERE code = ?", (code,))
    row = cursor.fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_active"] = bool(d["is_active"])
    return d

def list_discount_rules(
    conn: sqlite3.Connection,
    is_active: Optional[bool] = None,
    product_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    query = "SELECT * FROM discount_rules WHERE 1=1"
    params: List[Any] = []

    if is_active is not None:
        query += " AND is_active = ?"
        params.append(1 if is_active else 0)
    if product_id is not None:
        query += " AND (product_id = ? OR product_id IS NULL)"
        params.append(product_id)

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    results = []
    for r in cursor.fetchall():
        d = dict(r)
        d["is_active"] = bool(d["is_active"])
        results.append(d)
    return results

def update_discount_rule(conn: sqlite3.Connection, discount_id: int, data: DiscountRuleUpdate) -> Optional[Dict[str, Any]]:
    existing = get_discount_rule(conn, discount_id)
    if not existing:
        return None

    if data.code is not None and data.code != existing["code"]:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM discount_rules WHERE code = ? AND id != ?", (data.code, discount_id))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Discount code '{data.code}' already exists"
            )

    if data.product_id is not None:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products WHERE id = ?", (data.product_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target product not found")

    update_fields = []
    params: List[Any] = []

    field_map = {
        "code": data.code,
        "name": data.name,
        "discount_type": data.discount_type,
        "discount_value": data.discount_value,
        "min_purchase_amount": data.min_purchase_amount,
        "min_quantity": data.min_quantity,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "max_uses": data.max_uses,
        "product_id": data.product_id,
    }
    for k, v in field_map.items():
        if v is not None:
            update_fields.append(f"{k} = ?")
            params.append(v)

    if data.is_active is not None:
        update_fields.append("is_active = ?")
        params.append(1 if data.is_active else 0)

    if update_fields:
        query = f"UPDATE discount_rules SET {', '.join(update_fields)} WHERE id = ?"
        params.append(discount_id)
        cursor = conn.cursor()
        cursor.execute(query, params)

    return get_discount_rule(conn, discount_id)

def delete_discount_rule(conn: sqlite3.Connection, discount_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM discount_rules WHERE id = ?", (discount_id,))
    return cursor.rowcount > 0

def record_discount_usage(conn: sqlite3.Connection, discount_id: int) -> bool:
    """Atomically increments times_used for a discount rule."""
    cursor = conn.cursor()
    cursor.execute("UPDATE discount_rules SET times_used = times_used + 1 WHERE id = ?", (discount_id,))
    return cursor.rowcount > 0

def evaluate_discount(
    rule: Dict[str, Any],
    product_id: Optional[int],
    quantity: int,
    subtotal: float,
    eval_date: Optional[str] = None
) -> Tuple[bool, float, Optional[str]]:
    """
    Evaluates discount eligibility and calculates discount amount.
    Returns: (is_valid, discount_amount, reason_if_invalid)
    """
    if not rule.get("is_active"):
        return False, 0.0, "Discount rule is inactive"

    today_str = eval_date or datetime.date.today().isoformat()

    if rule.get("start_date") and today_str < rule["start_date"]:
        return False, 0.0, f"Discount not active until {rule['start_date']}"

    if rule.get("end_date") and today_str > rule["end_date"]:
        return False, 0.0, f"Discount expired on {rule['end_date']}"

    if rule.get("max_uses") is not None and rule.get("times_used", 0) >= rule["max_uses"]:
        return False, 0.0, "Discount maximum usage limit reached"

    rule_prod_id = rule.get("product_id")
    if rule_prod_id is not None and rule_prod_id != product_id:
        return False, 0.0, f"Discount applies only to product ID {rule_prod_id}"

    if quantity < (rule.get("min_quantity") or 0):
        return False, 0.0, f"Minimum quantity requirement of {rule['min_quantity']} not met"

    if subtotal < (rule.get("min_purchase_amount") or 0.0):
        return False, 0.0, f"Minimum purchase amount of {rule['min_purchase_amount']} not met"

    # Calculation
    dtype = rule.get("discount_type")
    dval = rule.get("discount_value", 0.0)

    if dtype == "PERCENTAGE":
        calc_amount = subtotal * (dval / 100.0)
    elif dtype == "FIXED":
        calc_amount = min(dval, subtotal)
    else:
        return False, 0.0, f"Unknown discount type {dtype}"

    discount_amount = max(0.0, min(calc_amount, subtotal))
    return True, round(discount_amount, 2), None

# ----------------- Pricing Engine Service -----------------

def compute_line_pricing(
    conn: sqlite3.Connection,
    product_id: int,
    variant_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    quantity: int = 1,
    discount_id: Optional[int] = None,
    discount_code: Optional[str] = None,
    tax_id: Optional[int] = None,
    eval_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Self-contained calculator: compute_line_pricing(product_id, variant_id, plan_id, quantity, discount_id, tax_id)
    Calculates exact subtotal, discount, taxes, and net totals.
    """
    if quantity < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be at least 1"
        )

    # 1. Product validation
    product = get_product(conn, product_id, include_variants=False)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found"
        )

    base_unit_price = float(product["sales_price"])
    variant_price_extra = 0.0

    # 2. Variant validation
    if variant_id is not None:
        variant = get_variant(conn, variant_id)
        if not variant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Variant with ID {variant_id} not found"
            )
        if variant["product_id"] != product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Variant {variant_id} does not belong to product {product_id}"
            )
        variant_price_extra = float(variant["price_extra"])

    # 3. Plan validation (if applicable)
    if plan_id is not None:
        plan = get_plan(conn, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan with ID {plan_id} not found"
            )
        if not plan["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Plan '{plan['name']}' is not active"
            )
        if quantity < plan["min_quantity"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Quantity {quantity} is less than plan minimum quantity {plan['min_quantity']}"
            )

    unit_price = round(base_unit_price + variant_price_extra, 2)
    subtotal = round(unit_price * quantity, 2)

    # 4. Discount resolution and calculation
    discount_rule = None
    if discount_id is not None:
        discount_rule = get_discount_rule(conn, discount_id)
    elif discount_code is not None:
        discount_rule = get_discount_rule_by_code(conn, discount_code)

    discount_applied = False
    discount_amount = 0.0
    discount_rejection_reason = None
    resolved_discount_id = None
    resolved_discount_code = None

    if discount_rule:
        resolved_discount_id = discount_rule["id"]
        resolved_discount_code = discount_rule["code"]
        is_valid, d_amount, reason = evaluate_discount(
            rule=discount_rule,
            product_id=product_id,
            quantity=quantity,
            subtotal=subtotal,
            eval_date=eval_date
        )
        if is_valid:
            discount_applied = True
            discount_amount = d_amount
        else:
            discount_rejection_reason = reason
    elif discount_id is not None or discount_code is not None:
        discount_rejection_reason = "Discount rule not found"

    taxable_amount = max(0.0, round(subtotal - discount_amount, 2))

    # 5. Tax resolution and calculation
    tax_rule = None
    if tax_id is not None:
        tax_rule = get_tax_rule(conn, tax_id)
    else:
        tax_rule = get_default_tax_rule(conn)

    tax_rate = 0.0
    tax_name = None
    resolved_tax_id = None
    tax_amount = 0.0

    if tax_rule and tax_rule.get("is_active"):
        resolved_tax_id = tax_rule["id"]
        tax_name = tax_rule["name"]
        tax_rate = float(tax_rule["rate_percent"])
        tax_amount = round(taxable_amount * (tax_rate / 100.0), 2)

    total_amount = round(taxable_amount + tax_amount, 2)

    return {
        "product_id": product_id,
        "variant_id": variant_id,
        "plan_id": plan_id,
        "quantity": quantity,
        "base_unit_price": base_unit_price,
        "variant_price_extra": variant_price_extra,
        "unit_price": unit_price,
        "subtotal": subtotal,
        "discount_id": resolved_discount_id,
        "discount_code": resolved_discount_code,
        "discount_amount": discount_amount,
        "taxable_amount": taxable_amount,
        "tax_id": resolved_tax_id,
        "tax_name": tax_name,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total_amount": total_amount,
        "discount_applied": discount_applied,
        "discount_rejection_reason": discount_rejection_reason,
    }
