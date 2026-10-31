from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict

ProductType = Literal["SOFTWARE", "ADDON", "SERVICE"]
BillingInterval = Literal["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
DiscountType = Literal["PERCENTAGE", "FIXED"]

# ---------------- Product Variant Schemas ----------------

class ProductVariantBase(BaseModel):
    attribute_name: str = Field(..., description="e.g. Brand, Tier, Storage")
    attribute_value: str = Field(..., description="e.g. Odoo, Enterprise, 1TB")
    price_extra: float = Field(0.0, description="Additional price added to base product price")

class ProductVariantCreate(ProductVariantBase):
    pass

class ProductVariantUpdate(BaseModel):
    attribute_name: Optional[str] = None
    attribute_value: Optional[str] = None
    price_extra: Optional[float] = None

class ProductVariantResponse(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    created_at: str

# ---------------- Product Schemas ----------------

class ProductBase(BaseModel):
    name: str
    product_type: ProductType = "SOFTWARE"
    sales_price: float = Field(0.0, ge=0.0)
    cost_price: float = Field(0.0, ge=0.0)
    notes: Optional[str] = None
    is_active: bool = True

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    product_type: Optional[ProductType] = None
    sales_price: Optional[float] = Field(None, ge=0.0)
    cost_price: Optional[float] = Field(None, ge=0.0)
    notes: Optional[str] = None
    is_active: Optional[bool] = None

class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    variants: List[ProductVariantResponse] = []

# ---------------- Plan Schemas ----------------

class PlanBase(BaseModel):
    name: str
    code: str
    billing_interval: BillingInterval
    price: float = Field(..., ge=0.0)
    min_quantity: int = Field(1, ge=1)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    auto_close: bool = False
    allow_early_close: bool = True
    allow_pause: bool = True
    allow_renew: bool = True
    is_active: bool = True

class PlanCreate(PlanBase):
    pass

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    billing_interval: Optional[BillingInterval] = None
    price: Optional[float] = Field(None, ge=0.0)
    min_quantity: Optional[int] = Field(None, ge=1)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    auto_close: Optional[bool] = None
    allow_early_close: Optional[bool] = None
    allow_pause: Optional[bool] = None
    allow_renew: Optional[bool] = None
    is_active: Optional[bool] = None

class PlanResponse(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str

# ---------------- Quotation Template Schemas ----------------

class QuotationTemplateLineCreate(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int = Field(1, ge=1)

class QuotationTemplateLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    product_id: int
    variant_id: Optional[int] = None
    quantity: int
    product_name: Optional[str] = None
    product_sales_price: Optional[float] = None
    attribute_name: Optional[str] = None
    attribute_value: Optional[str] = None
    price_extra: Optional[float] = None

class QuotationTemplateBase(BaseModel):
    name: str
    plan_id: Optional[int] = None
    validity_days: int = Field(30, ge=1)
    notes: Optional[str] = None

class QuotationTemplateCreate(QuotationTemplateBase):
    lines: List[QuotationTemplateLineCreate] = []

class QuotationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    plan_id: Optional[int] = None
    validity_days: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None
    lines: Optional[List[QuotationTemplateLineCreate]] = None

class QuotationTemplateResponse(QuotationTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_name: Optional[str] = None
    created_at: str
    lines: List[QuotationTemplateLineResponse] = []

# ---------------- Tax Rule Schemas ----------------

class TaxRuleBase(BaseModel):
    name: str
    rate_percent: float = Field(..., ge=0.0)
    country_code: str = "GLOBAL"
    is_default: bool = True
    is_active: bool = True

class TaxRuleCreate(TaxRuleBase):
    pass

class TaxRuleUpdate(BaseModel):
    name: Optional[str] = None
    rate_percent: Optional[float] = Field(None, ge=0.0)
    country_code: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

class TaxRuleResponse(TaxRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str

# ---------------- Discount Rule Schemas ----------------

class DiscountRuleBase(BaseModel):
    code: str
    name: str
    discount_type: DiscountType
    discount_value: float = Field(..., ge=0.0)
    min_purchase_amount: float = Field(0.0, ge=0.0)
    min_quantity: int = Field(0, ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_uses: Optional[int] = Field(None, ge=1)
    product_id: Optional[int] = None
    is_active: bool = True

class DiscountRuleCreate(DiscountRuleBase):
    pass

class DiscountRuleUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[float] = Field(None, ge=0.0)
    min_purchase_amount: Optional[float] = Field(None, ge=0.0)
    min_quantity: Optional[int] = Field(None, ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_uses: Optional[int] = Field(None, ge=1)
    product_id: Optional[int] = None
    is_active: Optional[bool] = None

class DiscountRuleResponse(DiscountRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    times_used: int
    created_at: str

# ---------------- Pricing Engine Schemas ----------------

class PricingRequest(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    plan_id: Optional[int] = None
    quantity: int = Field(1, ge=1)
    discount_id: Optional[int] = None
    discount_code: Optional[str] = None
    tax_id: Optional[int] = None
    eval_date: Optional[str] = None

class PricingResponse(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    plan_id: Optional[int] = None
    quantity: int
    base_unit_price: float
    variant_price_extra: float
    unit_price: float
    subtotal: float
    discount_id: Optional[int] = None
    discount_code: Optional[str] = None
    discount_amount: float
    taxable_amount: float
    tax_id: Optional[int] = None
    tax_name: Optional[str] = None
    tax_rate: float
    tax_amount: float
    total_amount: float
    discount_applied: bool
    discount_rejection_reason: Optional[str] = None
