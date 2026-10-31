# Brightloop Software - ZeroSkip Subscription Management Engine

A unified subscription management and recurring billing platform engineered for **Brightloop Software** to handle multi-tiered product catalogs, customizable pricing plans, automated subscription lifecycles, idempotent invoice generation, payment reconciliation, and real-time financial reporting with a guaranteed **< 2-second SLA**.

---

## 🚀 Quickstart & One-Click Launch

The repository includes an automated launcher script that verifies dependencies, resets and seeds the demo database, and starts the FastAPI application server:

```bash
# 1. Clone repository
git clone https://github.com/siddharthsai218/zeroskip.git
cd zeroskip

# 2. Make runner executable and launch
chmod +x run.sh
./run.sh
```

Once running, access the services:
- **Interactive Web Dashboard:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Specifications:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🔐 Interactive Web Dashboard & Demo Personas

The interactive web dashboard features live financial KPI cards, dynamic invoice action buttons, real-time billing triggers, and an **interactive authentication modal** supporting both manual JWT login and 1-click persona switching:

| Persona | Email | Password | Role & Permissions |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin@brightloop.io` | `BrightloopPass123!` | Full control: configure plans, trigger automated billing runs, view company-wide MRR/ARR |
| **Sales Staff** | `sales@brightloop.io` | `BrightloopPass123!` | Quotation creation, subscription lifecycle management, manual payment recording |
| **Customer (Alice)** | `alice@smallshop.com` | `BrightloopPass123!` | Customer Portal: self-service view of personal subscriptions and unpaid invoices |
| **Customer (Bob)** | `bob@megacorp.com` | `BrightloopPass123!` | Customer Portal: enterprise subscription history and invoice settlement |

> All dashboard API calls automatically authenticate against `/api/v1/auth/login` and attach verified Bearer JWT tokens.

---

## ⚡ High Performance & 2-Second SLA Benchmark

The problem statement requires all financial analytics and billing aggregations to execute in **under 2.0 seconds** over large datasets. ZeroSkip achieves this using raw SQLite WAL mode paired with composite indexes on `subscriptions`, `invoices`, and `payments`.

Run the automated 10,000 subscription stress test benchmark:

```bash
python scripts/stress_test.py
```

### Benchmark Results
- **Dataset Size:** 10,000 subscriptions + 10,000 invoices across 1,000 enterprise customers.
- **SLA Requirement:** `< 2.0000 s`
- **ZeroSkip Execution Time:** **`0.0051 s` (5.14 ms)**
- **Performance Factor:** **~388x faster than the required SLA.**

---

## 🧪 Comprehensive Test Suite (55/55 Passing)

All four isolated modules are thoroughly covered with synchronous pytest unit and integration tests using `starlette.testclient`:

```bash
pytest
```

```text
tests/test_part1_auth.py ...........................                     [ 49%]
tests/test_part2_catalog.py ...........                                  [ 69%]
tests/test_part3_subscriptions.py .......                                [ 81%]
tests/test_part4_billing.py ..........                                   [100%]

======================== 55 passed in 24.30s ========================
```

---

## 🎬 3-Minute Video Presentation Guide

For hackathon submissions and evaluations, refer to [`DEMO_GUIDE.md`](DEMO_GUIDE.md) for a time-coded walkthrough covering:
1. **0:00 - 0:45:** Problem context, 4-part architecture, and conflict-free Git strategy.
2. **0:45 - 1:30:** Live Interactive Dashboard walkthrough (Admin vs. Customer views, Quote-to-Subscription lifecycle).
3. **1:30 - 2:15:** Automated billing run, strict idempotency enforcement, and payment settlement.
4. **2:15 - 3:00:** 10,000-subscription stress benchmark (< 6ms response) and conclusion.

---

## 🏛 Architecture & Work Breakdown (4 Independent Parts)

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
- **Namespace:** `/api/v1/auth`, `/api/v1/users`, `/api/v1/portal/profile`  
- **Core Responsibility:** Identity verification, strict password policies, role-based authorization, and staff governance.
- **Key Features:**
  - Strict password validation: > 8 chars (min 9), 1 uppercase, 1 lowercase, 1 special character.
  - Secure bcrypt hashing & PyJWT token generation/refresh.
  - Role-Based Access Control (`Admin`, `Staff`, `Customer`).
  - Dependency inversion guards: `get_current_user`, `require_admin`, `require_staff`, `require_customer`.
- **Owned Tables:** `users`, `password_resets`.

---

### Part 2: Product Catalog, Plans, Variants, Taxes & Pricing Rules
- **Namespace:** `/api/v1/catalog`, `/api/v1/plans`, `/api/v1/templates`, `/api/v1/taxes`, `/api/v1/discounts`  
- **Core Responsibility:** Product definitions, dynamic variants, billing plan policies, quotation templates, and discount/tax calculation engines.
- **Key Features:**
  - Product variants supporting attribute adjustments (e.g., Brand = "Odoo" adds +$560 to base price).
  - Billing intervals: `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY`.
  - Plan lifecycle rules: `auto_close`, `allow_early_close`, `allow_pause`, `allow_renew`.
  - Pre-configured Quotation Templates for 1-click quote drafting.
  - Percentage and fixed discount rules with expiration and threshold validation.
- **Owned Tables:** `products`, `product_variants`, `plans`, `quotation_templates`, `quotation_template_lines`, `taxes`, `discounts`.

---

### Part 3: Subscriptions Lifecycle & Quotation Management
- **Namespace:** `/api/v1/quotations`, `/api/v1/subscriptions`, `/api/v1/portal/subscriptions`  
- **Core Responsibility:** Quote building, subscription state machine, term management, and customer self-service subscription views.
- **Key Features:**
  - Unique subscription sequence generation (`SUB-2026-00001`).
  - Strict State Machine: `Draft` ➔ `Quotation` ➔ `Confirmed` ➔ `Active` ➔ `Closed`.
  - Mid-lifecycle state actions: Pause, Resume, Renew, Early Close, Auto-Close on expiration.
  - Access segregation: Staff views all subscriptions; Customers access only their owned records.
- **Owned Tables:** `subscriptions`, `subscription_lines`.

---

### Part 4: Recurring Billing Engine, Invoicing, Payments & Financial Reporting
- **Namespace:** `/api/v1/billing`, `/api/v1/invoices`, `/api/v1/payments`, `/api/v1/reports`, `/api/v1/portal/invoices`  
- **Core Responsibility:** Idempotent recurring billing runs, invoice lifecycles, payment recording, overdue tracking, and high-performance financial reporting.
- **Key Features:**
  - **Idempotency Guarantee:** "Nothing billed twice or skipped" via strict period verification and `billing_runs` tracking.
  - Automatic advancement of `next_billing_date` based on subscription plan cycle.
  - Full invoice lifecycle: `Draft` ➔ `Confirmed` ➔ `Paid` (or `Cancelled`), with HTML print formatting.
  - Multi-method payment capture (`Credit Card`, `Bank Transfer`, `Stripe`, `Cash`, `Check`) with automated settlement.
  - Sub-2s executive analytics: Active subscriptions, MRR, ARR, Collected vs Overdue balances.
- **Owned Tables:** `invoices`, `invoice_lines`, `payments`, `billing_runs`.

---

## 📂 Repository Directory Structure

```text
zeroskip/
├── README.md                     # Comprehensive system guide & architecture specs
├── DEMO_GUIDE.md                 # 3-minute video presentation & script
├── progress.md                   # Real-time task tracker and completion records
├── requirements.txt              # Production and test dependencies
├── run.sh                        # Automated application bootstrap & demo launcher
├── zeroskip.db                   # SQLite WAL database (auto-generated)
│
├── scripts/
│   ├── seed_demo.py              # Realistic Brightloop demo data seeder
│   └── stress_test.py            # 10,000 subscription / sub-2s SLA benchmark
│
├── src/
│   ├── config.py                 # Application configuration & environment settings
│   ├── main.py                   # Central FastAPI app mounting routers from Parts 1-4
│   ├── dashboard_html.py         # Tailwind CSS / AlpineJS interactive web dashboard
│   │
│   ├── common/                   # Shared infrastructure (Read-only for all parts)
│   │   ├── db.py                 # SQLite WAL connection, migrations, indexes
│   │   └── security.py           # Bcrypt & JWT verification primitives
│   │
│   ├── part1_auth/               # PART 1: Identity & RBAC
│   │   ├── router.py             # /auth, /users endpoints
│   │   ├── services.py           # User management, password validation, reset tokens
│   │   ├── schemas.py            # Pydantic schemas for auth & profiles
│   │   └── dependencies.py       # Reusable JWT & role guards
│   │
│   ├── part2_catalog/            # PART 2: Catalog, Plans & Rules
│   │   ├── router.py             # /catalog, /plans, /templates, /taxes, /discounts
│   │   ├── services.py           # Pricing calculator, discount evaluation
│   │   └── schemas.py            # Pydantic schemas for products & pricing
│   │
│   ├── part3_subscriptions/      # PART 3: Lifecycle & Quotations
│   │   ├── router.py             # /quotations, /subscriptions, /portal endpoints
│   │   ├── services.py           # Lifecycle state machine, quote conversion
│   │   └── schemas.py            # Pydantic schemas for subscriptions
│   │
│   └── part4_billing/            # PART 4: Billing Engine, Invoicing & Reports
│       ├── router.py             # /billing, /invoices, /payments, /reports
│       ├── services.py           # Billing engine, payment reconciliation, analytics
│       └── schemas.py            # Pydantic schemas for invoices & payments
│
└── tests/
    ├── conftest.py               # Shared test database fixture
    ├── test_part1_auth.py        # Part 1 tests (27 passing)
    ├── test_part2_catalog.py     # Part 2 tests (11 passing)
    ├── test_part3_subscriptions.py # Part 3 tests (7 passing)
    └── test_part4_billing.py     # Part 4 tests (10 passing)
```

---

## 🗄 High-Performance Database Indexing Plan

All database tables are initialized in `src/common/db.py` with composite indexes guaranteeing `< 2-second` query response times under high-volume operations:

```sql
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

## 🛡 Conflict Prevention Rules for Teams

1. **Strict Router Isolation:** Each developer only edits their assigned package directory (`src/partX_*`).
2. **Read-Only Shared Core:** Changes to `src/common/db.py` or `src/config.py` require mutual review.
3. **No Cross-Domain Direct DB Writes:** 
   - Part 3 writes only to `subscriptions` and `subscription_lines`.
   - Part 4 writes only to `invoices`, `payments`, and `billing_runs`.
4. **Decoupled Tests:** Each part has its own test file in `tests/test_partX_*.py` that runs independently in CI/CD.
5. **Zero Circular Imports:** Routers and services import only from `src.common` or schemas within their own module.
