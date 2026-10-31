from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

SubscriptionStatus = Literal["Draft", "Quotation", "Confirmed", "Active", "Paused", "Closed"]

# --- Subscription Line Schemas ---

class SubscriptionLineCreate(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int = Field(ge=1, default=1)
    unit_price: Optional[float] = Field(default=None, ge=0.0, description="Override unit price. If omitted, looked up from product + variant price.")
    tax_rate: Optional[float] = Field(default=0.0, ge=0.0, description="Tax percentage applicable to line.")

class SubscriptionLineResponse(BaseModel):
    id: int
    subscription_id: int
    product_id: int
    product_name: Optional[str] = None
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    quantity: int
    unit_price: float
    tax_rate: float
    amount: float

    model_config = ConfigDict(from_attributes=True)


# --- Event Schemas ---

class SubscriptionEventResponse(BaseModel):
    id: int
    subscription_id: int
    from_status: Optional[str] = None
    to_status: str
    user_id: Optional[int] = None
    reason: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


# --- Quotation & Subscription Creation Schemas ---

class QuotationCreateCustom(BaseModel):
    customer_id: int
    plan_id: int
    start_date: Optional[str] = Field(default=None, description="ISO Date (YYYY-MM-DD); defaults to current date if omitted")
    expiry_date: Optional[str] = Field(default=None, description="ISO Date (YYYY-MM-DD); auto-calculated if omitted")
    payment_terms: str = Field(default="Net 30")
    discount_rule_id: Optional[int] = None
    notes: Optional[str] = None
    lines: List[SubscriptionLineCreate] = []

class QuotationCreateFromTemplate(BaseModel):
    template_id: int
    customer_id: int
    start_date: Optional[str] = Field(default=None, description="ISO Date (YYYY-MM-DD); defaults to current date if omitted")
    payment_terms: str = Field(default="Net 30")
    discount_rule_id: Optional[int] = None
    notes: Optional[str] = None

class SubscriptionUpdate(BaseModel):
    payment_terms: Optional[str] = None
    expiry_date: Optional[str] = None
    discount_rule_id: Optional[int] = None
    notes: Optional[str] = None

class StateTransitionRequest(BaseModel):
    target_status: SubscriptionStatus
    reason: Optional[str] = Field(default=None, description="Optional rationale for audit event logging")

class RenewalRequest(BaseModel):
    extension_periods: int = Field(default=1, ge=1, description="Number of plan intervals to extend subscription for")
    reason: Optional[str] = "Subscription renewal"


# --- Response Schemas ---

class SubscriptionResponse(BaseModel):
    id: int
    subscription_number: str
    customer_id: int
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    plan_id: int
    plan_name: Optional[str] = None
    plan_code: Optional[str] = None
    billing_interval: Optional[str] = None
    status: SubscriptionStatus
    payment_terms: str
    start_date: str
    expiry_date: Optional[str] = None
    next_billing_date: Optional[str] = None
    last_billed_date: Optional[str] = None
    discount_rule_id: Optional[int] = None
    notes: Optional[str] = None
    total_recurring_amount: float = 0.0
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)

class SubscriptionDetailResponse(SubscriptionResponse):
    lines: List[SubscriptionLineResponse] = []
    events: List[SubscriptionEventResponse] = []
    plan_policies: Optional[Dict[str, Any]] = None
