# 10 — Development Guide

## Local setup

**Prerequisites**: Python 3.11.11+ (managed via `uv`), Node.js/npm,
access to a Databricks workspace with the `ingestion_framework_test.bid_data_exploration`
schema.

```bash
# Backend
uv sync
uv pip install httpx2 -q   # needed for TestClient-based scratch tests; see 09-troubleshooting.md
cp .env.example .env       # fill in DATABRICKS_HTTP_PATH at minimum

# Frontend
cd frontend && npm install
```

## Running locally

Two processes, same as production (`start.sh`), but run separately for
hot-reload:

```bash
# Terminal 1 — backend
uv run uvicorn backend.main:app --reload --port 8001

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open `http://localhost:3000` — **not** `http://127.0.0.1:3000` (see
[09-troubleshooting.md](09-troubleshooting.md)). `next.config.ts`
rewrites `/api/*` to `http://127.0.0.1:8001/api/*` automatically; no
separate proxy setup is needed.

## Testing approach

There is **no committed test suite** in this repository. Verification
during development follows a consistent, deliberate pattern instead:

1. **Backend logic**: an ad-hoc script using `fastapi.testclient.TestClient`
   against the real `backend.main.app`, with `backend.api.<module>.get_connection`
   patched (via `unittest.mock.patch`) to a hand-written `FakeConn`/
   `FakeCursor` that pattern-matches on substrings of the SQL text and
   returns fixture rows. This exercises the real endpoint logic
   end-to-end (routing, validation, dataclass serialization) without a
   real warehouse connection.
2. **Frontend**: `npx tsc --noEmit` for typechecking, plus a mock FastAPI
   backend (a small standalone script exposing just the endpoints a
   given page needs, with in-memory fixture data) run on port 8001
   alongside the real `npm run dev` frontend, driven by a Playwright
   script for a visual walkthrough/screenshot.

**When adding a new backend feature, write a `FakeCursor` test that
covers**: the baseline (nothing set yet), the new write path working
end-to-end and changing the read-side output correctly, an undo path if
one exists, and the two standard validation failures (unknown
`user_id` → 404, unknown target entity → 400). Re-run every prior
feature's fixture-based test afterward to confirm no regression — there
is no CI to catch this automatically.

**Critical `FakeCursor` gotcha**: order your `execute()` method's
`if`/`elif` branches so `CREATE TABLE`/`INSERT INTO` checks for your new
table come **before** any generic `WHERE rfqnum = '...'` mismatch guard.
DDL/INSERT statements don't contain that WHERE-clause shape, so a
mismatch guard checked first will silently swallow them — meaning your
fixture data never actually gets appended, and every assertion after the
write will subtly fail against stale data.

## Adding a new app-owned overlay table

Follow the exact pattern established by `bid_analyzer_line_disqualifications`
and `bid_analyzer_partial_bids`:

1. **Schema file**: `databricks/schema/bid_analyzer_<name>.sql`. A single
   `CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_<name>`
   statement, `USING DELTA`, with a `COMMENT` on the table and every
   column explaining its purpose and any FK relationship (informational
   only — never a real constraint). Note at the top of the file exactly
   which grant it needs beyond the app's current `SELECT`-only access.
2. **Backend module**: `backend/api/<name>.py`. Read the schema file's
   text once at module scope
   (`Path(__file__).resolve().parent.parent.parent / "databricks" / "schema" / "bid_analyzer_<name>.sql"`).
   In the write endpoint: validate `user_id` exists in
   `bid_analyzer_users`, validate the target entity is real (a genuine
   `quotationline`/`rfqvendor` row — whatever prevents a typo'd key from
   creating an orphan row), then `cursor.execute(_CREATE_TABLE_SQL)`
   followed by the `INSERT`. Wrap the whole block in
   `try/except HTTPException: raise / except Exception as exc: raise
   HTTPException(503, ...)`.
3. **Overlay fetch in `comparison.py`** (if the new table affects the
   BOQ comparison view): a fail-open `_fetch_<name>(rfqnum)` function
   (bare `try/except Exception: return {}`), called unconditionally
   inside `build_comparison()` if the concept doesn't change between
   negotiation rounds (like disqualification/partial-bid status), or
   gated on `is_original` if it does (like price corrections).
4. **Mount the router** in `backend/main.py`, alongside the existing
   `app.include_router(...)` calls.
5. **Frontend type + fetch wrapper** in `lib/api.ts`, following the
   existing `SetDisqualificationParams`/`DisqualificationSummary`/
   `setDisqualification` shape.
6. **Document it** in `databricks/FINDINGS.md` — a new subsection
   matching the style of the existing disqualification/partial-bid
   sections: what it does, the exact enforcement rule if there is one,
   what was verified, and known limitations.

## Code style conventions to match

- **Dataclasses for request/response shapes**, converted with
  `dataclasses.asdict()` — not Pydantic `BaseModel`, even though FastAPI
  supports both.
- **No comments explaining *what* code does** — only *why*, when the
  reasoning isn't obvious from reading the code itself (a workaround, a
  non-obvious invariant, a real bug this shape was chosen to avoid).
  Every module docstring in this codebase follows this same discipline.
- **`f"...{escape_sql_literal(x)}..."` for every interpolated string
  value in SQL** — never skip this, even for a value that "shouldn't"
  contain a quote.
- **A `build_x()` plain function separate from its `@router` decorator**,
  whenever another module might plausibly want to call it in-process
  (see [05-application.md](05-application.md)'s "shared conventions").
- **Fail-open only for genuinely optional overlay data** — never for the
  core data a view depends on to mean anything (see
  [06-business-logic.md](06-business-logic.md)'s fail-open section for
  the exact line between the two).

## Working with `databricks/FINDINGS.md`

This file is the project's running data-exploration and design-decision
log — not just a historical record. Before building anything that
touches a Maximo table, check whether it's already been profiled here
(row counts, real column behavior, known-unreliable columns like
`DETAILBOQAVAILABLE`/`BOQITEMNUM`). When you learn something new about a
table's real behavior, or make a deliberate scope/design decision, add a
new subsection rather than editing an old one out — corrections to
earlier findings are written as explicit "correction to Run N" notes, so
the history of what was believed and why it changed stays visible.
