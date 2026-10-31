import sqlite3
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse

from src.part4_billing.dependencies import (
    get_db_session,
    require_admin,
    require_staff,
    require_customer,
    get_current_user,
)
from src.part4_billing.schemas import (
    InvoiceResponse,
    InvoiceDetailResponse,
    InvoiceStatusUpdate,
    PaymentCreate,
    PaymentResponse,
    BillingRunTriggerRequest,
    BillingRunResponse,
    FinancialSummaryResponse,
    OverdueReportResponse,
)
from src.part4_billing import billing_engine, invoicing_service, payment_service, reporting_service

# --- Sub-Routers ---
billing_router = APIRouter(prefix="/billing", tags=["Recurring Billing Engine"])
invoices_router = APIRouter(prefix="/invoices", tags=["Invoice Management"])
payments_router = APIRouter(prefix="/payments", tags=["Payment Reconciliation"])
reports_router = APIRouter(prefix="/reports", tags=["Financial Analytics & Reporting"])
portal_invoices_router = APIRouter(prefix="/portal/invoices", tags=["Customer Portal Invoices"])


# ============================================================================
# 1. Billing Engine Routes
# ============================================================================

@billing_router.post("/trigger", response_model=BillingRunResponse, status_code=status.HTTP_200_OK)
def trigger_billing_cycle_endpoint(
    payload: BillingRunTriggerRequest = BillingRunTriggerRequest(),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """
    Executes the ZeroSkip automated recurring billing cycle:
    - Queries active subscriptions due on or before `run_date`
    - Prevents duplicate billing (Idempotency)
    - Advances next_billing_date automatically
    - Generates itemized invoices with taxes and discounts
    """
    try:
        result = billing_engine.run_recurring_billing_cycle(conn, payload.run_date)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Billing cycle failed: {str(exc)}"
        )

@billing_router.get("/history", response_model=List[BillingRunResponse])
def get_billing_history_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Retrieves audit trail of recurring billing execution logs."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM billing_runs ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset)
    )
    return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# 2. Invoice Management Routes (Staff / Admin)
# ============================================================================

@invoices_router.get("", response_model=List[InvoiceResponse])
def list_invoices_endpoint(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    status: Optional[str] = Query(None, description="Filter by status (Draft, Confirmed, Paid, Cancelled)"),
    start_date: Optional[str] = Query(None, description="Filter issue_date >= start_date"),
    end_date: Optional[str] = Query(None, description="Filter issue_date <= end_date"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Lists invoices across the platform with filtering and balance calculations."""
    return invoicing_service.list_invoices(
        conn,
        customer_id=customer_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )

@invoices_router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
def get_invoice_detail_endpoint(
    invoice_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Retrieves full invoice details including lines, tax breakdown, and payment history."""
    invoice = invoicing_service.get_invoice_detail(conn, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice #{invoice_id} not found."
        )
    return invoice

@invoices_router.patch("/{invoice_id}/status", response_model=InvoiceResponse)
def update_invoice_status_endpoint(
    invoice_id: int,
    status_update: InvoiceStatusUpdate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Transitions invoice state (Draft -> Confirmed, Draft/Confirmed -> Cancelled)."""
    try:
        updated = invoicing_service.transition_invoice_status(conn, invoice_id, status_update.status)
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@invoices_router.post("/{invoice_id}/send")
def send_invoice_endpoint(
    invoice_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Dispatches invoice notification simulation to the customer's registered email."""
    try:
        return invoicing_service.send_invoice_email_simulation(conn, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

@invoices_router.get("/{invoice_id}/print", response_class=HTMLResponse)
def print_invoice_endpoint(
    invoice_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Renders print-ready, professional HTML invoice for Brightloop Software."""
    try:
        html = invoicing_service.generate_invoice_html(conn, invoice_id)
        return HTMLResponse(content=html, status_code=200)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ============================================================================
# 3. Payments & Reconciliation Routes
# ============================================================================

@payments_router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def record_payment_endpoint(
    payment: PaymentCreate,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """
    Records a payment against an invoice:
    - Supports multiple methods (Credit Card, Bank Transfer, Stripe, Cash, Check)
    - Automatically updates invoice amount_paid
    - Auto-transitions invoice status to 'Paid' when balance is settled
    """
    try:
        result = payment_service.record_invoice_payment(
            conn,
            invoice_id=payment.invoice_id,
            amount=payment.amount,
            payment_method=payment.payment_method,
            payment_date=payment.payment_date,
            transaction_ref=payment.transaction_ref,
            notes=payment.notes
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@payments_router.get("", response_model=List[PaymentResponse])
def list_payments_endpoint(
    invoice_id: Optional[int] = Query(None, description="Filter by invoice ID"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Lists payment transactions across invoices and customers."""
    return payment_service.list_payments(
        conn,
        invoice_id=invoice_id,
        customer_id=customer_id,
        limit=limit,
        offset=offset
    )


# ============================================================================
# 4. Financial Analytics & Reporting Routes
# ============================================================================

@reports_router.get("/summary", response_model=FinancialSummaryResponse)
def get_finance_summary_metrics_endpoint(
    as_of_date: Optional[str] = Query(None, description="ISO Date (YYYY-MM-DD)"),
    customer_id: Optional[int] = Query(None, description="Optional customer filter"),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """
    Finance Lead Executive Dashboard (< 2s latency guarantee):
    Returns real-time Active Subscriptions, normalized MRR, ARR, Cash Collections,
    and Outstanding Balance metrics.
    """
    return reporting_service.compute_financial_summary_metrics(
        conn,
        as_of_date_str=as_of_date,
        customer_id=customer_id
    )

@reports_router.get("/overdue", response_model=OverdueReportResponse)
def get_overdue_aging_report_endpoint(
    as_of_date: Optional[str] = Query(None, description="ISO Date (YYYY-MM-DD)"),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """
    Accounts Receivable Overdue & Aging Report:
    Categorizes unpaid overdue invoices into 1-30, 31-60, 61-90, and 90+ day aging buckets.
    """
    return payment_service.get_overdue_aging_report(conn, as_of_date_str=as_of_date)


# ============================================================================
# 5. Customer Portal Invoices Routes
# ============================================================================

@portal_invoices_router.get("", response_model=List[InvoiceResponse])
def get_customer_portal_invoices_endpoint(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service endpoint to view their own invoice history."""
    customer_id = current_user.get("id")
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid customer session")
    return invoicing_service.list_invoices(
        conn,
        customer_id=int(customer_id),
        limit=limit,
        offset=offset
    )

@portal_invoices_router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
def get_customer_portal_invoice_detail_endpoint(
    invoice_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service endpoint to inspect lines and payment status of an invoice."""
    customer_id = current_user.get("id")
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid customer session")

    invoice = invoicing_service.get_invoice_detail(conn, invoice_id, customer_id=int(customer_id))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice #{invoice_id} not found."
        )
    return invoice

@portal_invoices_router.get("/{invoice_id}/print", response_class=HTMLResponse)
def get_customer_portal_invoice_print_endpoint(
    invoice_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service endpoint to download/print their official invoice."""
    customer_id = current_user.get("id")
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid customer session")

    invoice = invoicing_service.get_invoice_detail(conn, invoice_id, customer_id=int(customer_id))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice #{invoice_id} not found."
        )
    html = invoicing_service.generate_invoice_html(conn, invoice_id)
    return HTMLResponse(content=html, status_code=200)


# ============================================================================
# Master Part 4 Router
# ============================================================================

router = APIRouter()
router.include_router(billing_router)
router.include_router(invoices_router)
router.include_router(payments_router)
router.include_router(reports_router)
router.include_router(portal_invoices_router)
