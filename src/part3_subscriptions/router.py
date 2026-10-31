import sqlite3
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query

from src.part3_subscriptions.dependencies import (
    get_db_session,
    require_admin,
    require_staff,
    require_customer,
    get_current_user,
)
from src.part3_subscriptions.schemas import (
    QuotationCreateFromTemplate,
    QuotationCreateCustom,
    SubscriptionUpdate,
    StateTransitionRequest,
    RenewalRequest,
    SubscriptionResponse,
    SubscriptionDetailResponse,
)
from src.part3_subscriptions import services

quotations_router = APIRouter(prefix="/quotations", tags=["Quotation Management"])
subscriptions_router = APIRouter(prefix="/subscriptions", tags=["Subscription Lifecycle"])
portal_subscriptions_router = APIRouter(prefix="/portal/subscriptions", tags=["Customer Portal Subscriptions"])


# ============================================================================
# 1. Quotations Routes (Staff / Admin)
# ============================================================================

@quotations_router.post("/template", response_model=SubscriptionDetailResponse, status_code=status.HTTP_201_CREATED)
def create_quote_from_template_endpoint(
    payload: QuotationCreateFromTemplate,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Creates a new quotation / subscription pre-filled from an approved quotation template."""
    try:
        user_id = current_user.get("id")
        return services.create_quotation_from_template(conn, payload, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@quotations_router.post("/custom", response_model=SubscriptionDetailResponse, status_code=status.HTTP_201_CREATED)
def create_custom_quote_endpoint(
    payload: QuotationCreateCustom,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Creates a customized quotation with specific product and variant lines."""
    try:
        user_id = current_user.get("id")
        return services.create_custom_quotation(conn, payload, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@quotations_router.get("", response_model=List[SubscriptionResponse])
def list_quotations_endpoint(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Lists quotes in Draft or Quotation status."""
    cursor = conn.cursor()
    filters = ["s.status IN ('Draft', 'Quotation')"]
    params = []
    if customer_id is not None:
        filters.append("s.customer_id = ?")
        params.append(customer_id)

    where_clause = " WHERE " + " AND ".join(filters)
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


# ============================================================================
# 2. Subscriptions Routes (Staff / Admin)
# ============================================================================

@subscriptions_router.get("", response_model=List[SubscriptionResponse])
def list_subscriptions_endpoint(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    status: Optional[str] = Query(None, description="Filter by status (Draft, Quotation, Confirmed, Active, Paused, Closed)"),
    plan_id: Optional[int] = Query(None, description="Filter by plan ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Lists all subscriptions across customers with filtering."""
    return services.list_subscriptions(
        conn,
        customer_id=customer_id,
        status=status,
        plan_id=plan_id,
        limit=limit,
        offset=offset
    )

@subscriptions_router.get("/{subscription_id}", response_model=SubscriptionDetailResponse)
def get_subscription_detail_endpoint(
    subscription_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    _user: Dict[str, Any] = Depends(require_staff),
):
    """Retrieves full subscription details with lines, plan policy, and event history."""
    sub = services.get_subscription_detail(conn, subscription_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subscription #{subscription_id} not found.")
    return sub

@subscriptions_router.patch("/{subscription_id}/status", response_model=SubscriptionDetailResponse)
def transition_subscription_status_endpoint(
    subscription_id: int,
    transition: StateTransitionRequest,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Transitions subscription through its state machine (Draft -> Quotation -> Confirmed -> Active -> Closed)."""
    try:
        user_id = current_user.get("id")
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status=transition.target_status,
            user_id=user_id,
            reason=transition.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@subscriptions_router.post("/{subscription_id}/pause", response_model=SubscriptionDetailResponse)
def pause_subscription_endpoint(
    subscription_id: int,
    reason: Optional[str] = Query(None, description="Reason for pausing"),
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Pauses an active subscription if permitted by plan policy."""
    try:
        user_id = current_user.get("id")
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status="Paused",
            user_id=user_id,
            reason=reason or "Subscription paused by staff"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@subscriptions_router.post("/{subscription_id}/resume", response_model=SubscriptionDetailResponse)
def resume_subscription_endpoint(
    subscription_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Resumes a paused subscription back to Active."""
    try:
        user_id = current_user.get("id")
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status="Active",
            user_id=user_id,
            reason="Subscription resumed by staff"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@subscriptions_router.post("/{subscription_id}/close", response_model=SubscriptionDetailResponse)
def close_subscription_early_endpoint(
    subscription_id: int,
    reason: Optional[str] = Query(None, description="Reason for closing early"),
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Closes an active subscription early if permitted by plan policy."""
    try:
        user_id = current_user.get("id")
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status="Closed",
            user_id=user_id,
            reason=reason or "Subscription closed early by staff"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@subscriptions_router.post("/{subscription_id}/renew", response_model=SubscriptionDetailResponse)
def renew_subscription_endpoint(
    subscription_id: int,
    payload: RenewalRequest = RenewalRequest(),
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_staff),
):
    """Renews a subscription for specified intervals if permitted by plan policy."""
    try:
        user_id = current_user.get("id")
        return services.renew_subscription(
            conn,
            subscription_id=subscription_id,
            extension_periods=payload.extension_periods,
            user_id=user_id,
            reason=payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ============================================================================
# 3. Customer Portal Subscriptions Routes
# ============================================================================

@portal_subscriptions_router.get("", response_model=List[SubscriptionResponse])
def get_customer_portal_subscriptions_endpoint(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service endpoint to view their own subscriptions."""
    customer_id = current_user.get("id")
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid customer session")

    return services.list_subscriptions(
        conn,
        customer_id=int(customer_id),
        status=status,
        limit=limit,
        offset=offset
    )

@portal_subscriptions_router.get("/{subscription_id}", response_model=SubscriptionDetailResponse)
def get_customer_portal_subscription_detail_endpoint(
    subscription_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service endpoint to view itemized lines and status of their subscription."""
    customer_id = current_user.get("id")
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid customer session")

    sub = services.get_subscription_detail(conn, subscription_id, customer_id=int(customer_id))
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription #{subscription_id} not found."
        )
    return sub

@portal_subscriptions_router.post("/{subscription_id}/pause", response_model=SubscriptionDetailResponse)
def customer_pause_subscription_endpoint(
    subscription_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service action to pause subscription if permitted."""
    customer_id = current_user.get("id")
    sub = services.get_subscription_detail(conn, subscription_id, customer_id=int(customer_id))
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    try:
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status="Paused",
            user_id=int(customer_id),
            reason="Paused by customer via portal"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@portal_subscriptions_router.post("/{subscription_id}/resume", response_model=SubscriptionDetailResponse)
def customer_resume_subscription_endpoint(
    subscription_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service action to resume a paused subscription."""
    customer_id = current_user.get("id")
    sub = services.get_subscription_detail(conn, subscription_id, customer_id=int(customer_id))
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    try:
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status="Active",
            user_id=int(customer_id),
            reason="Resumed by customer via portal"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@portal_subscriptions_router.post("/{subscription_id}/close", response_model=SubscriptionDetailResponse)
def customer_close_subscription_endpoint(
    subscription_id: int,
    conn: sqlite3.Connection = Depends(get_db_session),
    current_user: Dict[str, Any] = Depends(require_customer),
):
    """Customer self-service action to cancel/close subscription early if permitted."""
    customer_id = current_user.get("id")
    sub = services.get_subscription_detail(conn, subscription_id, customer_id=int(customer_id))
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    try:
        return services.transition_subscription_status(
            conn,
            subscription_id=subscription_id,
            target_status="Closed",
            user_id=int(customer_id),
            reason="Cancelled by customer via portal"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ============================================================================
# Master Part 3 Router
# ============================================================================

router = APIRouter()
router.include_router(quotations_router)
router.include_router(subscriptions_router)
router.include_router(portal_subscriptions_router)
