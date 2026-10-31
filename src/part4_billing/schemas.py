from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict

# --- Invoice Line Schemas ---

class InvoiceLineBase(BaseModel):
    product_id: Optional[int] = None
    description: str
    quantity: int = Field(ge=1, default=1)
    unit_price: float = Field(ge=0.0, default=0.0)
    tax_rate: float = Field(ge=0.0, default=0.0)
    tax_amount: float = Field(ge=0.0, default=0.0)
    line_total: float = Field(ge=0.0, default=0.0)

class InvoiceLineCreate(InvoiceLineBase):
    pass

class InvoiceLineResponse(InvoiceLineBase):
    id: int
    invoice_id: int

    model_config = ConfigDict(from_attributes=True)


# --- Invoice Schemas ---

InvoiceStatus = Literal["Draft", "Confirmed", "Paid", "Cancelled"]

class InvoiceBase(BaseModel):
    subscription_id: int
    customer_id: int
    issue_date: str
    due_date: str
    subtotal: float = Field(ge=0.0, default=0.0)
    tax_total: float = Field(ge=0.0, default=0.0)
    discount_total: float = Field(ge=0.0, default=0.0)
    total_amount: float = Field(ge=0.0, default=0.0)
    billing_period_start: Optional[str] = None
    billing_period_end: Optional[str] = None

class InvoiceResponse(InvoiceBase):
    id: int
    invoice_number: str
    status: InvoiceStatus
    amount_paid: float = 0.0
    amount_due: float = 0.0
    sent_at: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)

class InvoiceDetailResponse(InvoiceResponse):
    lines: List[InvoiceLineResponse] = []
    payments: List["PaymentResponse"] = []
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    subscription_number: Optional[str] = None

class InvoiceStatusUpdate(BaseModel):
    status: InvoiceStatus


# --- Payment Schemas ---

PaymentMethod = Literal["Credit Card", "Bank Transfer", "Stripe", "Cash", "Check"]

class PaymentCreate(BaseModel):
    invoice_id: int
    amount: float = Field(gt=0.0, description="Payment amount must be greater than zero")
    payment_method: PaymentMethod = "Bank Transfer"
    payment_date: Optional[str] = Field(default=None, description="ISO Date (YYYY-MM-DD); defaults to current date if omitted")
    transaction_ref: Optional[str] = None
    notes: Optional[str] = None

class PaymentResponse(BaseModel):
    id: int
    invoice_id: int
    customer_id: int
    amount: float
    payment_method: str
    payment_date: str
    transaction_ref: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    remaining_balance: Optional[float] = None
    invoice_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Update forward reference for InvoiceDetailResponse
InvoiceDetailResponse.model_rebuild()


# --- Billing Run Schemas ---

class BillingRunTriggerRequest(BaseModel):
    run_date: Optional[str] = Field(default=None, description="ISO Date (YYYY-MM-DD); defaults to current date if omitted")

class BillingRunResponse(BaseModel):
    id: int
    run_date: str
    subscriptions_evaluated: int
    invoices_generated: int
    total_billed_amount: float
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


# --- Financial Reporting Schemas ---

class AgingBracket(BaseModel):
    bracket: str
    count: int
    amount: float

class FinancialSummaryResponse(BaseModel):
    active_subscriptions: int
    mrr: float = Field(description="Monthly Recurring Revenue normalized across plan intervals")
    arr: float = Field(description="Annual Recurring Revenue (MRR * 12)")
    total_revenue_collected: float = Field(description="Total payments recorded to date")
    total_invoiced_amount: float = Field(description="Total amount of confirmed/paid invoices")
    total_outstanding_amount: float = Field(description="Unpaid balance across confirmed invoices")
    total_overdue_amount: float = Field(description="Balance past due date across confirmed invoices")
    paid_invoices_count: int
    outstanding_invoices_count: int
    overdue_invoices_count: int

class OverdueInvoiceItem(BaseModel):
    invoice_id: int
    invoice_number: str
    customer_id: int
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    issue_date: str
    due_date: str
    days_overdue: int
    total_amount: float
    amount_paid: float
    balance_due: float

class OverdueReportResponse(BaseModel):
    as_of_date: str
    total_overdue_amount: float
    overdue_count: int
    aging_summary: List[AgingBracket]
    overdue_invoices: List[OverdueInvoiceItem]
