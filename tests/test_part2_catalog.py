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
from src.part2_catalog.router import router as catalog_router
from src.part2_catalog.dependencies import get_db_session, require_admin, require_staff, get_current_user
from src.part2_catalog.schemas import (
    ProductCreate, ProductUpdate,
    ProductVariantCreate, ProductVariantUpdate,
    PlanCreate, PlanUpdate,
    QuotationTemplateCreate, QuotationTemplateUpdate, QuotationTemplateLineCreate,
    TaxRuleCreate, TaxRuleUpdate,
    DiscountRuleCreate, DiscountRuleUpdate,
)
from src.part2_catalog import services

# Dummy auth entities
ADMIN_USER = {"id": 1, "email": "admin@brightloop.io", "role": "ADMIN"}
STAFF_USER = {"id": 2, "email": "staff@brightloop.io", "role": "STAFF"}
CUSTOMER_USER = {"id": 3, "email": "customer@brightloop.io", "role": "CUSTOMER"}

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def db_conn(temp_db):
    with get_db(temp_db) as conn:
        yield conn

@pytest.fixture
def client(temp_db):
    app = FastAPI(title="Test Catalog API")
    app.include_router(catalog_router, prefix="/api/v1")

    # Dependency overrides for isolated testing
    def override_get_db():
        with get_db(temp_db) as conn:
            yield conn

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    app.dependency_overrides[require_staff] = lambda: STAFF_USER
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER

    return TestClient(app)

# -------------------------------------------------------------
# Unit / Service Tests
# -------------------------------------------------------------

def test_product_crud(db_conn):
    prod = services.create_product(db_conn, ProductCreate(
        name="CRM Software",
        product_type="SOFTWARE",
        sales_price=100.0,
        cost_price=40.0,
        notes="Enterprise CRM",
        is_active=True
    ))
    assert prod["id"] is not None
    assert prod["name"] == "CRM Software"
    assert prod["sales_price"] == 100.0
    assert prod["is_active"] is True
    assert prod["variants"] == []

    # Update product
    updated = services.update_product(db_conn, prod["id"], ProductUpdate(sales_price=120.0))
    assert updated["sales_price"] == 120.0

    # List products
    products = services.list_products(db_conn, is_active=True)
    assert len(products) == 1
    assert products[0]["id"] == prod["id"]

    # Filter by product_type
    filtered = services.list_products(db_conn, product_type="SOFTWARE")
    assert len(filtered) == 1
    filtered_empty = services.list_products(db_conn, product_type="SERVICE")
    assert len(filtered_empty) == 0

    # Search filter
    searched = services.list_products(db_conn, search="CRM")
    assert len(searched) == 1

    # Delete product
    assert services.delete_product(db_conn, prod["id"]) is True
    assert services.get_product(db_conn, prod["id"]) is None

def test_product_variants(db_conn):
    prod = services.create_product(db_conn, ProductCreate(
        name="ERP Suite",
        product_type="SOFTWARE",
        sales_price=500.0
    ))
    variant = services.create_variant(db_conn, prod["id"], ProductVariantCreate(
        attribute_name="Tier",
        attribute_value="Enterprise",
        price_extra=250.0
    ))
    assert variant["id"] is not None
    assert variant["product_id"] == prod["id"]
    assert variant["price_extra"] == 250.0

    # Fetch product with variants
    prod_with_var = services.get_product(db_conn, prod["id"], include_variants=True)
    assert len(prod_with_var["variants"]) == 1
    assert prod_with_var["variants"][0]["attribute_value"] == "Enterprise"

    # Update variant
    upd_var = services.update_variant(db_conn, variant["id"], ProductVariantUpdate(price_extra=300.0))
    assert upd_var["price_extra"] == 300.0

    # Delete variant
    assert services.delete_variant(db_conn, variant["id"]) is True
    assert services.get_variant(db_conn, variant["id"]) is None

def test_plan_crud(db_conn):
    plan = services.create_plan(db_conn, PlanCreate(
        name="Annual Growth",
        code="ANNUAL_GROWTH",
        billing_interval="YEARLY",
        price=1200.0,
        min_quantity=5,
        allow_pause=True,
        allow_early_close=False,
        is_active=True
    ))
    assert plan["id"] is not None
    assert plan["code"] == "ANNUAL_GROWTH"
    assert plan["min_quantity"] == 5
    assert plan["allow_early_close"] is False

    # Get by code
    by_code = services.get_plan_by_code(db_conn, "ANNUAL_GROWTH")
    assert by_code["id"] == plan["id"]

    # Update plan
    updated = services.update_plan(db_conn, plan["id"], PlanUpdate(price=1100.0))
    assert updated["price"] == 1100.0

    # List plans
    plans = services.list_plans(db_conn, billing_interval="YEARLY")
    assert len(plans) == 1
    assert plans[0]["id"] == plan["id"]

    # Duplicate code check
    with pytest.raises(Exception):
        services.create_plan(db_conn, PlanCreate(
            name="Another Plan",
            code="ANNUAL_GROWTH",
            billing_interval="MONTHLY",
            price=100.0
        ))

    # Delete plan
    assert services.delete_plan(db_conn, plan["id"]) is True
    assert services.get_plan(db_conn, plan["id"]) is None

def test_quotation_template(db_conn):
    prod = services.create_product(db_conn, ProductCreate(name="Database Tool", sales_price=50.0))
    var = services.create_variant(db_conn, prod["id"], ProductVariantCreate(
        attribute_name="Edition",
        attribute_value="Pro",
        price_extra=25.0
    ))
    plan = services.create_plan(db_conn, PlanCreate(
        name="Monthly Standard",
        code="MONTHLY_STD",
        billing_interval="MONTHLY",
        price=20.0
    ))

    tmpl = services.create_template(db_conn, QuotationTemplateCreate(
        name="Standard DB Package",
        plan_id=plan["id"],
        validity_days=15,
        notes="Template notes",
        lines=[
            QuotationTemplateLineCreate(product_id=prod["id"], variant_id=var["id"], quantity=2)
        ]
    ))
    assert tmpl["id"] is not None
    assert tmpl["name"] == "Standard DB Package"
    assert len(tmpl["lines"]) == 1
    assert tmpl["lines"][0]["product_name"] == "Database Tool"
    assert tmpl["lines"][0]["attribute_value"] == "Pro"
    assert tmpl["lines"][0]["quantity"] == 2

    # Add line to template
    prod2 = services.create_product(db_conn, ProductCreate(name="Support Add-on", sales_price=30.0))
    new_line = services.add_template_line(db_conn, tmpl["id"], QuotationTemplateLineCreate(
        product_id=prod2["id"],
        quantity=1
    ))
    assert new_line["product_name"] == "Support Add-on"

    tmpl_refetched = services.get_template(db_conn, tmpl["id"])
    assert len(tmpl_refetched["lines"]) == 2

    # Update template with new lines
    updated_tmpl = services.update_template(db_conn, tmpl["id"], QuotationTemplateUpdate(
        validity_days=45,
        lines=[
            QuotationTemplateLineCreate(product_id=prod["id"], quantity=5)
        ]
    ))
    assert updated_tmpl["validity_days"] == 45
    assert len(updated_tmpl["lines"]) == 1
    assert updated_tmpl["lines"][0]["quantity"] == 5

    # Delete template
    assert services.delete_template(db_conn, tmpl["id"]) is True
    assert services.get_template(db_conn, tmpl["id"]) is None

def test_tax_and_discount_rules(db_conn):
    tax = services.create_tax_rule(db_conn, TaxRuleCreate(
        name="VAT Standard",
        rate_percent=18.0,
        country_code="IN",
        is_default=True
    ))
    assert tax["id"] is not None
    assert tax["rate_percent"] == 18.0

    default_tax = services.get_default_tax_rule(db_conn, country_code="IN")
    assert default_tax["id"] == tax["id"]

    discount = services.create_discount_rule(db_conn, DiscountRuleCreate(
        code="SAVE20",
        name="Save 20 percent",
        discount_type="PERCENTAGE",
        discount_value=20.0,
        min_purchase_amount=100.0,
        min_quantity=2,
        max_uses=10
    ))
    assert discount["id"] is not None
    assert discount["code"] == "SAVE20"

    # Test usage recording
    services.record_discount_usage(db_conn, discount["id"])
    refreshed = services.get_discount_rule(db_conn, discount["id"])
    assert refreshed["times_used"] == 1

def test_pricing_calculator_comprehensive(db_conn):
    # Setup product with variant
    prod = services.create_product(db_conn, ProductCreate(
        name="Analytics Platform",
        sales_price=200.0
    ))
    var = services.create_variant(db_conn, prod["id"], ProductVariantCreate(
        attribute_name="Brand",
        attribute_value="Brightloop",
        price_extra=50.0
    ))

    # Setup plan with min_quantity = 2
    plan = services.create_plan(db_conn, PlanCreate(
        name="Pro Monthly",
        code="PRO_MONTHLY",
        billing_interval="MONTHLY",
        price=10.0,
        min_quantity=2
    ))

    # Setup tax rule (10%)
    tax = services.create_tax_rule(db_conn, TaxRuleCreate(
        name="Tech Tax",
        rate_percent=10.0,
        is_default=True
    ))

    # Setup discount rule (20% off with min_quantity 2)
    discount = services.create_discount_rule(db_conn, DiscountRuleCreate(
        code="PROMO20",
        name="Promo 20%",
        discount_type="PERCENTAGE",
        discount_value=20.0,
        min_quantity=2
    ))

    # Successful calculation:
    # Base = 200, Variant extra = 50 -> unit_price = 250
    # Quantity = 2 -> subtotal = 500
    # Discount 20% -> discount_amount = 100
    # Taxable = 400
    # Tax 10% -> tax_amount = 40
    # Total = 440
    result = services.compute_line_pricing(
        conn=db_conn,
        product_id=prod["id"],
        variant_id=var["id"],
        plan_id=plan["id"],
        quantity=2,
        discount_id=discount["id"],
        tax_id=tax["id"]
    )

    assert result["base_unit_price"] == 200.0
    assert result["variant_price_extra"] == 50.0
    assert result["unit_price"] == 250.0
    assert result["subtotal"] == 500.0
    assert result["discount_applied"] is True
    assert result["discount_amount"] == 100.0
    assert result["taxable_amount"] == 400.0
    assert result["tax_rate"] == 10.0
    assert result["tax_amount"] == 40.0
    assert result["total_amount"] == 440.0

    # Test Plan min_quantity violation raises 400
    with pytest.raises(Exception):
        services.compute_line_pricing(
            conn=db_conn,
            product_id=prod["id"],
            plan_id=plan["id"],
            quantity=1  # Below min_quantity 2
        )

    # Test Mismatched variant raises 400
    prod2 = services.create_product(db_conn, ProductCreate(name="Other Prod", sales_price=10.0))
    with pytest.raises(Exception):
        services.compute_line_pricing(
            conn=db_conn,
            product_id=prod2["id"],
            variant_id=var["id"],  # belongs to prod, not prod2
            quantity=1
        )

    # Test Discount rejection when minimum purchase amount not met
    discount_min = services.create_discount_rule(db_conn, DiscountRuleCreate(
        code="BIGSPEND",
        name="Big Spender",
        discount_type="FIXED",
        discount_value=50.0,
        min_purchase_amount=1000.0
    ))
    res_min = services.compute_line_pricing(
        conn=db_conn,
        product_id=prod["id"],
        quantity=2, # subtotal = 400 < 1000
        discount_id=discount_min["id"]
    )
    assert res_min["discount_applied"] is False
    assert res_min["discount_amount"] == 0.0
    assert "Minimum purchase amount" in res_min["discount_rejection_reason"]

    # Test Discount rejection when product-specific constraint not met
    discount_prod_specific = services.create_discount_rule(db_conn, DiscountRuleCreate(
        code="PROD2ONLY",
        name="Prod 2 Only",
        discount_type="PERCENTAGE",
        discount_value=15.0,
        product_id=prod2["id"]
    ))
    res_spec = services.compute_line_pricing(
        conn=db_conn,
        product_id=prod["id"],
        quantity=1,
        discount_id=discount_prod_specific["id"]
    )
    assert res_spec["discount_applied"] is False
    assert "Discount applies only to product ID" in res_spec["discount_rejection_reason"]

    # Test Discount rejection when max uses reached
    discount_exhausted = services.create_discount_rule(db_conn, DiscountRuleCreate(
        code="LIMITED",
        name="Limited Uses",
        discount_type="PERCENTAGE",
        discount_value=50.0,
        max_uses=1
    ))
    services.record_discount_usage(db_conn, discount_exhausted["id"])
    res_exh = services.compute_line_pricing(
        conn=db_conn,
        product_id=prod["id"],
        quantity=1,
        discount_id=discount_exhausted["id"]
    )
    assert res_exh["discount_applied"] is False
    assert "maximum usage limit reached" in res_exh["discount_rejection_reason"]

# -------------------------------------------------------------
# HTTP API Tests via TestClient
# -------------------------------------------------------------

def test_api_products_flow(client):
    # 1. Create product
    res = client.post("/api/v1/catalog/products", json={
        "name": "Cloud Storage",
        "product_type": "SOFTWARE",
        "sales_price": 50.0,
        "cost_price": 20.0,
        "notes": "100GB Storage",
        "is_active": True
    })
    assert res.status_code == 201
    prod_data = res.json()
    prod_id = prod_data["id"]
    assert prod_data["name"] == "Cloud Storage"

    # 2. Add variant
    var_res = client.post(f"/api/v1/catalog/products/{prod_id}/variants", json={
        "attribute_name": "Capacity",
        "attribute_value": "1TB",
        "price_extra": 100.0
    })
    assert var_res.status_code == 201
    var_id = var_res.json()["id"]

    # 3. Get product
    get_res = client.get(f"/api/v1/catalog/products/{prod_id}")
    assert get_res.status_code == 200
    assert len(get_res.json()["variants"]) == 1

    # 4. List products
    list_res = client.get("/api/v1/catalog/products?q=Storage")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 5. Delete variant and product
    del_var = client.delete(f"/api/v1/catalog/variants/{var_id}")
    assert del_var.status_code == 204

    del_prod = client.delete(f"/api/v1/catalog/products/{prod_id}")
    assert del_prod.status_code == 204

def test_api_plans_flow(client):
    res = client.post("/api/v1/plans", json={
        "name": "Enterprise Annual",
        "code": "ENT_ANNUAL",
        "billing_interval": "YEARLY",
        "price": 5000.0,
        "min_quantity": 10,
        "auto_close": False,
        "allow_early_close": True,
        "allow_pause": True,
        "allow_renew": True,
        "is_active": True
    })
    assert res.status_code == 201
    plan_id = res.json()["id"]

    # Duplicate code check
    dup_res = client.post("/api/v1/plans", json={
        "name": "Duplicate",
        "code": "ENT_ANNUAL",
        "billing_interval": "YEARLY",
        "price": 5000.0
    })
    assert dup_res.status_code == 400

    # Get by code
    code_res = client.get("/api/v1/plans/code/ENT_ANNUAL")
    assert code_res.status_code == 200
    assert code_res.json()["id"] == plan_id

    # Update
    upd_res = client.put(f"/api/v1/plans/{plan_id}", json={"price": 4500.0})
    assert upd_res.status_code == 200
    assert upd_res.json()["price"] == 4500.0

    # Delete
    del_res = client.delete(f"/api/v1/plans/{plan_id}")
    assert del_res.status_code == 204

def test_api_templates_flow(client):
    # Setup product
    p_res = client.post("/api/v1/catalog/products", json={"name": "Module A", "sales_price": 40.0})
    pid = p_res.json()["id"]

    # Create template
    t_res = client.post("/api/v1/templates", json={
        "name": "Startup Pack",
        "validity_days": 20,
        "lines": [{"product_id": pid, "quantity": 3}]
    })
    assert t_res.status_code == 201
    tid = t_res.json()["id"]

    # Get template
    get_t = client.get(f"/api/v1/templates/{tid}")
    assert get_t.status_code == 200
    assert len(get_t.json()["lines"]) == 1
    assert get_t.json()["lines"][0]["product_name"] == "Module A"

    # Add line
    p_res2 = client.post("/api/v1/catalog/products", json={"name": "Module B", "sales_price": 60.0})
    pid2 = p_res2.json()["id"]

    line_res = client.post(f"/api/v1/templates/{tid}/lines", json={
        "product_id": pid2,
        "quantity": 2
    })
    assert line_res.status_code == 201
    lid = line_res.json()["id"]

    # Remove line
    del_l = client.delete(f"/api/v1/templates/lines/{lid}")
    assert del_l.status_code == 204

    # Delete template
    del_t = client.delete(f"/api/v1/templates/{tid}")
    assert del_t.status_code == 204

def test_api_taxes_and_discounts_flow(client):
    # Taxes
    tax_res = client.post("/api/v1/taxes", json={
        "name": "Federal GST",
        "rate_percent": 12.0,
        "country_code": "GLOBAL",
        "is_default": True
    })
    assert tax_res.status_code == 201
    tax_id = tax_res.json()["id"]

    def_tax = client.get("/api/v1/taxes/default")
    assert def_tax.status_code == 200
    assert def_tax.json()["id"] == tax_id

    # Discounts
    disc_res = client.post("/api/v1/discounts", json={
        "code": "FLAT10",
        "name": "10 Flat Discount",
        "discount_type": "FIXED",
        "discount_value": 10.0
    })
    assert disc_res.status_code == 201
    disc_id = disc_res.json()["id"]

    disc_get = client.get(f"/api/v1/discounts/{disc_id}")
    assert disc_get.status_code == 200
    assert disc_get.json()["times_used"] == 0

    use_res = client.post(f"/api/v1/discounts/{disc_id}/use")
    assert use_res.status_code == 200

    disc_refreshed = client.get(f"/api/v1/discounts/{disc_id}")
    assert disc_refreshed.json()["times_used"] == 1

def test_api_pricing_calculate_endpoint(client):
    # Setup product
    p_res = client.post("/api/v1/catalog/products", json={
        "name": "Security Suite",
        "sales_price": 100.0
    })
    pid = p_res.json()["id"]

    # Setup variant
    v_res = client.post(f"/api/v1/catalog/products/{pid}/variants", json={
        "attribute_name": "Seats",
        "attribute_value": "5-User",
        "price_extra": 50.0
    })
    vid = v_res.json()["id"]

    # Setup tax rule
    client.post("/api/v1/taxes", json={
        "name": "GST",
        "rate_percent": 18.0,
        "country_code": "GLOBAL",
        "is_default": True
    })

    # Setup discount
    client.post("/api/v1/discounts", json={
        "code": "OFF50",
        "name": "50 Flat Off",
        "discount_type": "FIXED",
        "discount_value": 50.0,
        "min_purchase_amount": 100.0
    })

    # Calculate pricing via endpoint
    calc_res = client.post("/api/v1/catalog/pricing/calculate", json={
        "product_id": pid,
        "variant_id": vid,
        "quantity": 2,
        "discount_code": "OFF50"
    })
    assert calc_res.status_code == 200
    data = calc_res.json()
    assert data["unit_price"] == 150.0
    assert data["subtotal"] == 300.0
    assert data["discount_amount"] == 50.0
    assert data["taxable_amount"] == 250.0
    assert data["tax_rate"] == 18.0
    assert data["tax_amount"] == 45.0
    assert data["total_amount"] == 295.0
