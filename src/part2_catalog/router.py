import sqlite3
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from src.part2_catalog.dependencies import (
    get_db_session,
    require_admin,
    require_staff,
    get_current_user,
)
from src.part2_catalog.schemas import (
    ProductCreate, ProductUpdate, ProductResponse,
    ProductVariantCreate, ProductVariantUpdate, ProductVariantResponse,
    PlanCreate, PlanUpdate, PlanResponse,
    QuotationTemplateCreate, QuotationTemplateUpdate, QuotationTemplateResponse,
    QuotationTemplateLineCreate, QuotationTemplateLineResponse,
    TaxRuleCreate, TaxRuleUpdate, TaxRuleResponse,
    DiscountRuleCreate, DiscountRuleUpdate, DiscountRuleResponse,
    PricingRequest, PricingResponse,
)
from src.part2_catalog import services

# Sub-routers
catalog_router = APIRouter(prefix="/catalog", tags=["Catalog & Products"])
plans_router = APIRouter(prefix="/plans", tags=["Subscription Plans"])
templates_router = APIRouter(prefix="/templates", tags=["Quotation Templates"])
taxes_router = APIRouter(prefix="/taxes", tags=["Tax Rules"])
discounts_router = APIRouter(prefix="/discounts", tags=["Discount Rules"])

# ----------------- Products & Variants Routes -----------------

@catalog_router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product_endpoint(
    product: ProductCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    return services.create_product(conn, product)

@catalog_router.get("/products", response_model=List[ProductResponse])
def list_products_endpoint(
    is_active: Optional[bool] = None,
    product_type: Optional[str] = None,
    q: Optional[str] = Query(None, description="Search by name or notes"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.list_products(
        conn,
        is_active=is_active,
        product_type=product_type,
        search=q,
        limit=limit,
        offset=offset
    )

@catalog_router.get("/products/{product_id}", response_model=ProductResponse)
def get_product_endpoint(
    product_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    product = services.get_product(conn, product_id, include_variants=True)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product

@catalog_router.put("/products/{product_id}", response_model=ProductResponse)
def update_product_endpoint(
    product_id: int,
    data: ProductUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    updated = services.update_product(conn, product_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return updated

@catalog_router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_endpoint(
    product_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    success = services.delete_product(conn, product_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return None

@catalog_router.post("/products/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
def create_variant_endpoint(
    product_id: int,
    variant: ProductVariantCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    return services.create_variant(conn, product_id, variant)

@catalog_router.get("/products/{product_id}/variants", response_model=List[ProductVariantResponse])
def list_variants_endpoint(
    product_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    prod = services.get_product(conn, product_id, include_variants=False)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return services.list_variants(conn, product_id)

@catalog_router.get("/variants/{variant_id}", response_model=ProductVariantResponse)
def get_variant_endpoint(
    variant_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    variant = services.get_variant(conn, variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant

@catalog_router.put("/variants/{variant_id}", response_model=ProductVariantResponse)
def update_variant_endpoint(
    variant_id: int,
    data: ProductVariantUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    updated = services.update_variant(conn, variant_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return updated

@catalog_router.delete("/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant_endpoint(
    variant_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    success = services.delete_variant(conn, variant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return None

# ----------------- Pricing Engine Route -----------------

@catalog_router.post("/pricing/calculate", response_model=PricingResponse)
def calculate_pricing_endpoint(
    req: PricingRequest,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.compute_line_pricing(
        conn=conn,
        product_id=req.product_id,
        variant_id=req.variant_id,
        plan_id=req.plan_id,
        quantity=req.quantity,
        discount_id=req.discount_id,
        discount_code=req.discount_code,
        tax_id=req.tax_id,
        eval_date=req.eval_date
    )

# ----------------- Subscription Plans Routes -----------------

@plans_router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan_endpoint(
    plan: PlanCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    return services.create_plan(conn, plan)

@plans_router.get("", response_model=List[PlanResponse])
def list_plans_endpoint(
    is_active: Optional[bool] = None,
    billing_interval: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.list_plans(
        conn,
        is_active=is_active,
        billing_interval=billing_interval,
        limit=limit,
        offset=offset
    )

@plans_router.get("/{plan_id}", response_model=PlanResponse)
def get_plan_endpoint(
    plan_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    plan = services.get_plan(conn, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan

@plans_router.get("/code/{code}", response_model=PlanResponse)
def get_plan_by_code_endpoint(
    code: str,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    plan = services.get_plan_by_code(conn, code)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan

@plans_router.put("/{plan_id}", response_model=PlanResponse)
def update_plan_endpoint(
    plan_id: int,
    data: PlanUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    updated = services.update_plan(conn, plan_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return updated

@plans_router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan_endpoint(
    plan_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    success = services.delete_plan(conn, plan_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return None

# ----------------- Quotation Templates Routes -----------------

@templates_router.post("", response_model=QuotationTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template_endpoint(
    template: QuotationTemplateCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    return services.create_template(conn, template)

@templates_router.get("", response_model=List[QuotationTemplateResponse])
def list_templates_endpoint(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.list_templates(conn, limit=limit, offset=offset)

@templates_router.get("/{template_id}", response_model=QuotationTemplateResponse)
def get_template_endpoint(
    template_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    tmpl = services.get_template(conn, template_id)
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation template not found")
    return tmpl

@templates_router.put("/{template_id}", response_model=QuotationTemplateResponse)
def update_template_endpoint(
    template_id: int,
    data: QuotationTemplateUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    updated = services.update_template(conn, template_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation template not found")
    return updated

@templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_endpoint(
    template_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    success = services.delete_template(conn, template_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation template not found")
    return None

@templates_router.post("/{template_id}/lines", response_model=QuotationTemplateLineResponse, status_code=status.HTTP_201_CREATED)
def add_template_line_endpoint(
    template_id: int,
    line: QuotationTemplateLineCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    tmpl = services.get_template(conn, template_id)
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation template not found")
    return services.add_template_line(conn, template_id, line)

@templates_router.delete("/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_template_line_endpoint(
    line_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    success = services.remove_template_line(conn, line_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quotation template line not found")
    return None

# ----------------- Tax Rules Routes -----------------

@taxes_router.post("", response_model=TaxRuleResponse, status_code=status.HTTP_201_CREATED)
def create_tax_rule_endpoint(
    tax: TaxRuleCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    return services.create_tax_rule(conn, tax)

@taxes_router.get("", response_model=List[TaxRuleResponse])
def list_tax_rules_endpoint(
    is_active: Optional[bool] = None,
    country_code: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.list_tax_rules(conn, is_active=is_active, country_code=country_code)

@taxes_router.get("/default", response_model=TaxRuleResponse)
def get_default_tax_rule_endpoint(
    country_code: Optional[str] = Query("GLOBAL"),
    conn: sqlite3.Connection = Depends(get_db_session),
):
    rule = services.get_default_tax_rule(conn, country_code=country_code)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Default tax rule not found")
    return rule

@taxes_router.get("/{tax_id}", response_model=TaxRuleResponse)
def get_tax_rule_endpoint(
    tax_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    rule = services.get_tax_rule(conn, tax_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax rule not found")
    return rule

@taxes_router.put("/{tax_id}", response_model=TaxRuleResponse)
def update_tax_rule_endpoint(
    tax_id: int,
    data: TaxRuleUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    updated = services.update_tax_rule(conn, tax_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax rule not found")
    return updated

@taxes_router.delete("/{tax_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tax_rule_endpoint(
    tax_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    success = services.delete_tax_rule(conn, tax_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax rule not found")
    return None

# ----------------- Discount Rules Routes -----------------

@discounts_router.post("", response_model=DiscountRuleResponse, status_code=status.HTTP_201_CREATED)
def create_discount_rule_endpoint(
    discount: DiscountRuleCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    return services.create_discount_rule(conn, discount)

@discounts_router.get("", response_model=List[DiscountRuleResponse])
def list_discount_rules_endpoint(
    is_active: Optional[bool] = None,
    product_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    return services.list_discount_rules(conn, is_active=is_active, product_id=product_id)

@discounts_router.get("/code/{code}", response_model=DiscountRuleResponse)
def get_discount_rule_by_code_endpoint(
    code: str,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    rule = services.get_discount_rule_by_code(conn, code)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Discount rule '{code}' not found")
    return rule

@discounts_router.get("/{discount_id}", response_model=DiscountRuleResponse)
def get_discount_rule_endpoint(
    discount_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
):
    rule = services.get_discount_rule(conn, discount_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount rule not found")
    return rule

@discounts_router.put("/{discount_id}", response_model=DiscountRuleResponse)
def update_discount_rule_endpoint(
    discount_id: int,
    data: DiscountRuleUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    updated = services.update_discount_rule(conn, discount_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount rule not found")
    return updated

@discounts_router.delete("/{discount_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discount_rule_endpoint(
    discount_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_admin),
):
    success = services.delete_discount_rule(conn, discount_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount rule not found")
    return None

@discounts_router.post("/{discount_id}/use", status_code=status.HTTP_200_OK)
def use_discount_endpoint(
    discount_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    rule = services.get_discount_rule(conn, discount_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount rule not found")
    if not rule["is_active"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Discount is inactive")
    if rule["max_uses"] is not None and rule["times_used"] >= rule["max_uses"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Discount max uses reached")
    services.record_discount_usage(conn, discount_id)
    return {"message": "Discount usage recorded successfully", "discount_id": discount_id}

# ----------------- Master Part 2 Router -----------------

router = APIRouter()
router.include_router(catalog_router)
router.include_router(plans_router)
router.include_router(templates_router)
router.include_router(taxes_router)
router.include_router(discounts_router)
