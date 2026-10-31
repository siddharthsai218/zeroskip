# Brightloop Software - Subscription Management System

A unified subscription management and recurring billing platform engineered for Brightloop Software to handle products, pricing plans, automated subscription lifecycles, idempotent invoice generation, payment reconciliation, and real-time financial reporting.

---

## Architecture & Work Breakdown (4 Independent Parts)

To allow four developers (or teams) to build this system in parallel without merge conflicts, code collisions, or dependency deadlocks, the project is divided into **four decoupled parts**. Each part has strict ownership of its domain models, API routes, business logic, and test suites.

```
                          ┌────────────────────────────────────────┐
                          │         Shared Core Foundation         │
                          │   (Config, DB Connection, SQLite WAL)  │
                          └───────────────────┬────────────────────┘
                                              │
         ┌───────────────────────┬────────────┴──────────┬──────────────────────┐
         ▼                       ▼                       ▼                      ▼
  ┌───────────────┐       ┌───────────────┐       ┌───────────────┐      ┌───────────────┐
  │    PART 1     │       │    PART 2     │       │    PART 3     │      │    PART 4     │
  │ Auth, Users & │       │ Catalog, Plans│       │ Subscriptions │      │ Recurring     │
  │ RBAC Security │       │ & Pricing     │       │ & Quotations  │      │ Invoicing &   │
  │               │       │ Rules         │       │ Lifecycle     │      │ Financials    │
  └───────┬───────┘       └───────┬───────┘       └───────┬───────┘      └───────┬───────┘
          │                       │                       │                      │
          └───────────────────────┴───────────┬───────────┴──────────────────────┘
                                              ▼
                                 Unified API Gateway / App
```

---

### Part 1: Authentication, Access Control & User Identity
**Owner:** Developer 1  
**Namespace:** `/api/v1/auth`, `/api/v1/users`, `/api/v1/portal/profile`  
**Core Responsibility:** Identity verification, strict password policies, role-based authorization, and staff governance.

#### Key Functional Requirements
- **Account Registration & Password Policy:**
  - Single account per email (unique constraint).
  - Strict password validation: strictly > 8 characters (min 9), containing at least one uppercase letter, one lowercase letter, and one special character.
- **Authentication & Sessions:**
  - Secure password hashing using bcrypt.
  - JWT token generation and verification with configurable expiration.
  - Password reset workflow: secure token generation, expiration tracking, and reset confirmation.
- **Role-Based Access Control (RBAC):**
  - **Admin:** Unrestricted access; only Admins can create staff accounts and configure global settings.
  - **Staff:** Limited internal access for day-to-day operations (customer viewing, quote generation, payment entry).
  - **Customer:** Restricted strictly to self-service portal (own profile, subscriptions, and invoices).
- **Dependency Inversion / Shared Guards:**
  - Export reusable authentication dependencies: `get_current_user`, `require_admin`, `require_staff`, `require_customer`.

#### Owned Data Models & Tables
- `users` (`id`, `email`, `password_hash`, `full_name`, `role`, `is_active`, `created_at`)
- `password_resets` (`id`, `user_id`, `token`, `expires_at`, `used`, `created_at`)

#### Interface Contract Provided to Other Parts
- Provides auth middleware and security primitives to Parts 2, 3, and 4.
- Resolves authenticated user identity (`user_id`, `role`) for all downstream operations.

---

### Part 2: Product Catalog, Plans, Variants, Taxes & Pricing Rules
**Owner:** Developer 2  
**Namespace:** `/api/v1/catalog`, `/api/v1/plans`, `/api/v1/templates`, `/api/v1/taxes`, `/api/v1/discounts`  
**Core Responsibility:** Product definitions, dynamic variants, billing plan policies, quotation templates, and discount/tax calculation engines.

#### Key Functional Requirements
- **Product & Variant Catalog:**
  - Products with name, type (Software, Add-on, Service), sales price, cost price, notes, and active status.
  - Product variants supporting attribute adjustments (e.g., Brand = "Odoo" adds 560 to base price).
- **Subscription Plans:**
  - Billing intervals: `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`.
  - Plan constraints: pricing, minimum quantity, validity date ranges (`start_date`, `end_date`).
  - Lifecycle policy flags: `auto_close` (close automatically on end), `allow_early_close`, `allow_pause`, `allow_renew`.
- **Quotation Templates:**
  - Reusable templates with pre-configured plan, product lines, and validity duration in days.
- **Tax & Discount Rules:**
  - Admin-configured tax rules (fixed rate, percentage).
  - Admin-configured discount rules: fixed amount or percentage, minimum purchase/quantity thresholds, usage limits, date ranges, and scope (product-specific vs. whole subscription).
- **Pricing Engine Service:**
  - Self-contained calculator: `compute_line_pricing(product_id, variant_id, plan_id, quantity, discount_id, tax_id)`.

#### Owned Data Models & Tables
- `products`, `product_variants`
- `plans`
- `quotation_templates`, `quotation_template_lines`
- `taxes`, `discounts`

#### Interface Contract Provided to Other Parts
- Part 3 uses Part 2's catalog, plans, and pricing calculator to instantiate subscriptions and quotes.
- Part 4 uses Part 2's tax and discount engines to apply accurate recurring rate adjustments.

---

### Part 3: Subscriptions Lifecycle & Quotation Management
**Owner:** Developer 3  
**Namespace:** `/api/v1/quotations`, `/api/v1/subscriptions`, `/api/v1/portal/subscriptions`  
**Core Responsibility:** Quote building, subscription state machine, term management, and customer self-service subscription views.

#### Key Functional Requirements
- **Quotation Management:**
  - Create quotes from scratch or pre-fill from Part 2 templates.
  - Unique subscription/quote number generation (e.g., `SUB-2026-00001`).
  - Quote validity tracking with expiration dates.
- **Subscription Lifecycle State Machine:**
  - Valid transitions: `Draft` ➔ `Quotation` ➔ `Confirmed` ➔ `Active` ➔ `Closed`.
  - State actions:
    - **Pause / Resume:** Allowed only if the underlying plan permits `allow_pause`.
    - **Early Close:** Allowed only if the plan permits `allow_early_close`.
    - **Renewal:** Extends active subscription duration according to plan policy.
    - **Auto-Close:** Automatic transition to `Closed` upon expiry if `auto_close` is enabled.
- **Subscription Line Items:**
  - Product, selected variant, quantity, unit price, applied tax rate, applied discount, and net total.
- **Access Segregation:**
  - Staff/Admin: View and manage all subscriptions across all customers.
  - Customer Portal: Customers view only subscriptions tied to their own `customer_id`.

#### Owned Data Models & Tables
- `subscriptions` (`id`, `subscription_number`, `customer_id`, `plan_id`, `status`, `start_date`, `expiry_date`, `next_billing_date`, `payment_terms`, `auto_close`, `created_at`)
- `subscription_lines` (`id`, `subscription_id`, `product_id`, `variant_id`, `quantity`, `unit_price`, `discount_id`, `tax_id`, `amount`)

#### Interface Contract Provided to Other Parts
- Provides subscription status and `next_billing_date` query endpoints for Part 4's billing engine (`get_due_subscriptions(billing_date)`).
- Consumes user identities from Part 1 and catalog entities from Part 2.

---

### Part 4: Recurring Billing Engine, Invoicing, Payments & Financial Reporting
**Owner:** Developer 4  
**Namespace:** `/api/v1/billing`, `/api/v1/invoices`, `/api/v1/payments`, `/api/v1/reports`, `/api/v1/portal/invoices`  
**Core Responsibility:** Idempotent recurring billing runs, invoice lifecycles, payment recording, overdue tracking, and high-performance financial reporting.

#### Key Functional Requirements
- **Automated Recurring Billing Engine:**
  - Batch job / endpoint processing all active subscriptions where `next_billing_date <= current_date`.
  - Idempotent execution: prevents duplicate invoicing for the same cycle (`billing_runs` log).
  - Automatically advances `next_billing_date` by the plan interval (`DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`).
- **Invoice Management:**
  - Invoices generated automatically with snapshot of customer details, lines, applied discounts, and taxes.
  - Lifecycle: `Draft` ➔ `Confirmed` ➔ `Paid` (or `Cancelled`).
  - Invoice actions: Confirm, cancel, send (email simulation), and print/HTML rendering.
- **Payments & Reconciliation:**
  - Record payments with method (`Credit Card`, `Bank Transfer`, `Stripe`, `Cash`, `Check`), amount, payment date, reference ID, and notes.
  - Real-time invoice status update: auto-transitions invoice to `Paid` once payments meet or exceed total.
  - Overdue tracking: identifies confirmed invoices past their due date.
- **Finance Lead Analytics Dashboard (< 2s latency guarantee):**
  - Active subscription count, Monthly Recurring Revenue (MRR), Annual Recurring Revenue (ARR).
  - Total collected revenue vs. outstanding/overdue balances.
  - Filterable by date range, customer, and payment status.
  - Indexed SQL queries optimized to run sub-2-second queries on large datasets.
- **Customer Portal Invoices:**
  - Customers view and download their own invoices.

#### Owned Data Models & Tables
- `invoices`, `invoice_lines`
- `payments`
- `billing_runs`

#### Interface Contract Provided to Other Parts
- Reads subscriptions from Part 3 without modifying subscription lines or plans.
- Updates subscription `next_billing_date` upon successful billing run.
- Emits invoice and payment status for portal and staff auditing.

---

## Directory Structure & Conflict-Free Code Boundaries

```
zeroskip/
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── config.py                 # Common configuration & environment variables
│   ├── main.py                   # Central FastAPI app mounting routers from Parts 1-4
│   │
│   ├── common/                   # Shared infrastructure (Read-only for all parts)
│   │   ├── __init__.py
│   │   ├── db.py                 # SQLite WAL connection, migrations, indexes
│   │   └── security.py           # Bcrypt & JWT verification primitives
│   │
│   ├── part1_auth/               # PART 1: Owned by Developer 1
│   │   ├── __init__.py
│   │   ├── router.py             # /auth, /users routes
│   │   ├── services.py           # User creation, password validation, reset logic
│   │   ├── schemas.py            # Pydantic schemas for auth & user profiles
│   │   └── dependencies.py       # Current user & RBAC permission checks
│   │
│   ├── part2_catalog/            # PART 2: Owned by Developer 2
│   │   ├── __init__.py
│   │   ├── router.py             # /catalog, /plans, /templates, /taxes, /discounts routes
│   │   ├── services.py           # Catalog CRUD, pricing engine, discount evaluation
│   │   └── schemas.py            # Pydantic schemas for products, plans, rules
│   │
│   ├── part3_subscriptions/      # PART 3: Owned by Developer 3
│   │   ├── __init__.py
│   │   ├── router.py             # /quotations, /subscriptions, /portal/subscriptions routes
│   │   ├── services.py           # State machine, pause/close/renew, template loader
│   │   └── schemas.py            # Pydantic schemas for quotes & subscriptions
│   │
│   └── part4_billing/            # PART 4: Owned by Developer 4
│       ├── __init__.py
│       ├── router.py             # /billing, /invoices, /payments, /reports routes
│       ├── services.py           # Billing engine, payment reconciliation, MRR/ARR analytics
│       └── schemas.py            # Pydantic schemas for invoices, payments, reports
│
└── tests/
    ├── conftest.py               # Shared test database fixture
    ├── test_part1_auth.py        # Part 1 isolated tests
    ├── test_part2_catalog.py     # Part 2 isolated tests
    ├── test_part3_subscriptions.py # Part 3 isolated tests
    └── test_part4_billing.py     # Part 4 isolated tests
```

---

## Shared Database Schema & Database Indexing Plan

To prevent schema conflicts, all database tables are declared in a single initialization script (`src/common/db.py`) with strict index definitions ensuring `< 2-second` query response times:

```sql
-- High-Performance Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);
CREATE INDEX IF NOT EXISTS idx_plans_code ON plans(code);
CREATE INDEX IF NOT EXISTS idx_subs_customer ON subscriptions(customer_id);
CREATE INDEX IF NOT EXISTS idx_subs_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subs_next_billing ON subscriptions(next_billing_date);
CREATE INDEX IF NOT EXISTS idx_invoices_sub ON invoices(subscription_id);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_due ON invoices(due_date);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_discounts_dates ON discounts(start_date, end_date);
```

---

## Conflict Prevention Rules for Teams

1. **Strict Router Isolation:** Each developer only edits their assigned package directory (`src/partX_*`).
2. **Read-Only Shared Core:** Changes to `src/common/db.py` or `src/config.py` require mutual review.
3. **No Cross-Domain Direct DB Writes:** 
   - Part 3 writes only to `subscriptions` and `subscription_lines`.
   - Part 4 writes only to `invoices`, `payments`, and `billing_runs`.
4. **Decoupled Tests:** Each part has its own test file in `tests/test_partX_*.py` that can pass independently in CI/CD.
5. **Zero Circular Imports:** Routers and services import only from `src.common` or schemas within their own module.
