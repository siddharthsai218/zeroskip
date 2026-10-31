# AGENTS.md

Brightloop subscription management: Python 3.13, FastAPI, raw `sqlite3` (no ORM), bcrypt + PyJWT.
Always read the progress.md whenever the work is being started or when you start to do. Make sure that there will be no conflicts when work is being pulled. Before starting, identify your part in [Work division] Also for each work or a part of the work done, make sure to commit in git. (#work-division--three-parts-strictly-non-overlapping) below — work only your part.

## Current state

Only the shared core exists:

- `src/config.py` — paths/env config
- `src/common/db.py` — full schema + indexes, connection helpers
- `src/common/security.py` — password hashing/validation, JWT create/decode

`README.md` specifies the target four-part design, but these do **not** exist yet:

- `src/main.py` and the FastAPI app
- `src/part1_auth/`, `src/part2_catalog/`, `src/part3_subscriptions/`, `src/part4_billing/`
- `tests/`

Create the expected package/file layout when implementing a part; do not invent a parallel structure.

## Commands

Run from the repository root (imports are absolute, e.g. `from src.common.db import init_db`).

```bash
pip install -r requirements.txt
python -c "from src.common.db import init_db; init_db()"   # create/upgrade local schema
pytest                                                     # once tests exist
pytest tests/test_part1_auth.py -q                         # single part
uvicorn src.main:app --reload                              # after src/main.py exists
```

- There is no package install, `pyproject.toml`, lint/typecheck config, or CI. Do not assume `npm`, `make`, or formatter commands exist.
- No `.env` loading is configured. Export `DB_PATH` / `JWT_SECRET` in the shell; `os.getenv` reads the process env.
- Default DB is `<repo>/zeroskip.db` (gitignored). For tests/smoke checks, pass a temp path instead of touching it.
- `init_db()` is idempotent (`CREATE ... IF NOT EXISTS`) but cannot alter existing tables. There is no migration framework: delete the local DB or add explicit migration SQL when changing columns.

## Implementation constraints

- Strict ownership: edit only your assigned `src/partX_*` package. Treat `src/config.py` and `src/common/*` as shared/read-only unless the change is truly cross-cutting.
- Routers mount under `/api/v1` (e.g. `/api/v1/auth`, `/api/v1/subscriptions`). Part 1 must expose `get_current_user`, `require_admin`, `require_staff`, `require_customer` for the other parts.
- No cross-domain writes: Part 3 owns `subscriptions`/`subscription_lines`; Part 4 owns `invoices`/`payments`/`billing_runs`; Part 4 may only update subscription `next_billing_date`.
- Use `src.common.db.get_db()` (commits on success, rolls back on exception) and `sqlite3.Row` access. Do not open ad-hoc SQLite connections.
- Status/role values are exact display strings from `db.py`: `Draft`, `Quotation`, `Confirmed`, `Active`, `Paused`, `Closed`; `ADMIN`, `STAFF`, `CUSTOMER`; payment methods such as `Bank Transfer`.
- Keep imports one-way: routers/services import shared core and their own schemas only. No circular part-to-part imports.

## Schema gotchas

- `src/common/db.py` is the executable schema source of truth, even where README differs. Actual table names are `tax_rules` and `discount_rules` (README says `taxes`/`discounts`), and `subscription_lines` has `tax_rate` but no `discount_id`/`tax_id` columns. Reconcile README when you touch this area.
- All indexes live in `init_db()`; add new indexes there, matching the existing `CREATE INDEX IF NOT EXISTS` pattern.
- `DB_PATH` is captured as a default argument when `src.common.db` is imported. Monkeypatching `src.config.DB_PATH` later does not affect `init_db()`/`get_db()`; pass `db_path` explicitly in tests, or set `DB_PATH` before importing.
- No `pytest-asyncio` in `requirements.txt`; prefer sync tests with `fastapi.testclient.TestClient` unless you add it.
