# 05: Application (Backend Module Reference)

`backend/main.py` mounts every router below under the `/api` prefix, in
this order:

```python
rfqs_router, users_router, projects_router, comparison_router,
beta_pricing_router, corrections_router, disqualifications_router,
partial_bids_router, rounds_router, negotiation_report_router,
negotiation_narrative_router
```

Plus two non-router routes defined directly on `app`: `GET /health`
(liveness) and `GET /api/rfq-count` (a lightweight, UI-independent
connectivity smoke test, a leftover from before `/` became the Projects
page).

## API endpoint reference

| Method | Path | Module | Purpose |
|---|---|---|---|
| GET | `/health` | `main.py` | Liveness check |
| GET | `/api/rfq-count` | `main.py` | Connectivity smoke test |
| GET | `/api/rfqs` | `rfqs.py` | Search/filter/paginate the RFQ browse list |
| POST | `/api/users/identify` | `users.py` | Resolve or create a user identity |
| GET | `/api/projects` | `projects.py` | List projects (optionally by user) |
| POST | `/api/projects` | `projects.py` | Create a project |
| GET | `/api/projects/{project_id}` | `projects.py` | Project detail |
| GET | `/api/rfqs/{rfqnum}/comparison` | `comparison.py` | The BOQ comparison engine; see [02](02-boq-comparison-engine.md) |
| POST | `/api/rfqs/{rfqnum}/corrections` | `corrections.py` | Manually correct/fill a price |
| POST | `/api/rfqs/{rfqnum}/disqualifications` | `disqualifications.py` | Manually disqualify a line |
| POST | `/api/rfqs/{rfqnum}/partial-bids` | `partial_bids.py` | Flag a vendor's bid as partial-scope |
| GET | `/api/rfqs/{rfqnum}/rounds` | `rounds.py` | Round-over-round trend + flags; see [03](03-round-negotiation-tracking.md) |
| GET | `/api/rfqs/{rfqnum}/negotiation-report` | `negotiation_report.py` | Ranked, deterministic negotiation-prep digest |
| GET | `/api/rfqs/{rfqnum}/negotiation-report.xlsx` | `negotiation_report.py` | Same, as an Excel download |
| POST | `/api/rfqs/{rfqnum}/negotiation-report/narrative` | `negotiation_narrative.py` | AI-generated executive summary + observations |
| POST | `/api/rfqs/{rfqnum}/comparison/beta` | `beta_pricing.py` | AI-estimated "Beta" unit price per line |

## Module-by-module

### `backend/db.py`

The one shared connection helper. `get_connection()` returns a
`databricks.sql` connection: an explicit `DATABRICKS_TOKEN` if set
(simplest for local dev), otherwise falls back to `databricks.sdk.core.Config()`'s
auto-detected credential chain (a configured CLI profile locally, or
auto-injected credentials as a deployed Databricks App). `CATALOG` and
`SCHEMA` constants and `escape_sql_literal()` (doubles embedded single
quotes) live here too, imported by every other module.

### `backend/boq_classification.py`

See [04-data-model.md](04-data-model.md)'s last section. In-process
cache, thread-safe via a plain `threading.Lock`, TTL 15 minutes.

### `backend/api/rfqs.py`

`GET /api/rfqs`: the browse/search list. Filters by org (default
`ADDCORG`), free-text search (`ILIKE` on `RFQNUM`/`DESCRIPTION`, with
manual `%`/`_`/`\` escaping since this is hand-written SQL), and BOQ
category. Only RFQs above `MIN_BOQ_LINE_ITEMS` are ever returned;
lump-sum/shallow/no-pricing-data RFQs have no real BOQ to compare and are
dropped entirely, not exposed as a togglable filter.

### `backend/api/users.py`

`POST /api/users/identify`; see
[06-business-logic.md](06-business-logic.md) for the identity model in
full. Tries a forwarded platform header first
(`X-Forwarded-Email`/`X-Forwarded-Preferred-Username`/`X-Forwarded-User`,
unverified whether Databricks Apps actually sends any of these), falls
back to a self-reported `display_name`. `email IS NULL` is the
discriminator that keeps self-reported users from ever colliding with a
real forwarded-identity user of the same display name.

### `backend/api/projects.py`

The "Projects" registry: each project maps to exactly one RFQ and one
user (many projects can point at the same RFQ). `POST /api/projects`
validates the target RFQ is actually in-scope (has a real BOQ, per
`boq_classification`) before creating anything. Every read endpoint here
defensively runs `CREATE TABLE IF NOT EXISTS` too (not just the write
path); without it, the very first list load on a fresh deployment would
503 instead of showing a clean empty state, since the table wouldn't
exist yet.

### `backend/api/comparison.py`

The core engine. Full chapter: [02-boq-comparison-engine.md](02-boq-comparison-engine.md).

### `backend/api/corrections.py`, `disqualifications.py`, `partial_bids.py`

Three structurally near-identical write endpoints, all following the
same shape: validate `user_id` exists (`bid_analyzer_users`), validate
the target (line+vendor, or just vendor for partial bids) is real
(`quotationline` or `rfqvendor`), then `CREATE TABLE IF NOT EXISTS` +
`INSERT` an append-only row. See
[06-business-logic.md](06-business-logic.md) for the pattern this
follows and why it's replicated three times rather than shared.

### `backend/api/round_snapshots.py`, `rounds.py`

Full chapter: [03-round-negotiation-tracking.md](03-round-negotiation-tracking.md).

### `backend/api/negotiation_report.py`

Deterministic negotiation-prep digest, **deliberately not LLM-generated**.
Calls `build_comparison()` and `build_round_trend()` **in-process**
(direct Python function calls, not HTTP round trips to the app's own
API), ranks vendors by `contract_total` ascending, and for each vendor
picks up to `TOP_ISSUES_PER_VENDOR = 8` issues via a category-first
dedup-then-backfill algorithm (`_pick_top_issues`), so a lone arithmetic
error isn't crowded out by five outliers of the same category. Also
exposes an Excel download (`openpyxl`, two sheets: Summary and Issues)
via `GET .../negotiation-report.xlsx`.

### `backend/api/llm_client.py`

One function, `get_llm_endpoint_name()`: reads `DATABRICKS_LLM_ENDPOINT`
from the environment, raising a clean, actionable 503 if unset. Shared
by both AI features so there's exactly one place that knows the env var
name and the "not configured" message.

### `backend/api/negotiation_narrative.py`

AI-generated executive summary + per-vendor observations, layered on the
deterministic report above. Uses Databricks Model Serving
(`WorkspaceClient().serving_endpoints.query()`), an explicit choice
after an AI Impact Assessment review, so vendor pricing data stays inside
TAQA's governed workspace rather than going to a third-party API. Always
a fresh call, no caching, never auto-triggered. See
[06-business-logic.md](06-business-logic.md) for the guardrails
(deterministic safety net, prompt-injection posture, error taxonomy).

### `backend/api/beta_pricing.py`

A materially higher-risk AI feature than the narrative: the model is
asked to **invent** a fair unit price from its own general construction/
material/service cost knowledge, using real vendor quotes only as
context, not as a formula. Batched (`BETA_BATCH_SIZE = 20` lines per
Model Serving call, capped at `BETA_LINES_CAP = 60` lines total) to keep
every response small regardless of BOQ size, a direct lesson from a
real truncation bug hit by the narrative feature at higher line counts.
See [06-business-logic.md](06-business-logic.md) and
[09-troubleshooting.md](09-troubleshooting.md).

## Shared conventions across every module

- **Dataclasses, not Pydantic models, for response shapes**, converted
  to dicts via `dataclasses.asdict()` right before returning. Request
  bodies *are* declared as dataclasses too and FastAPI handles the
  validation.
- **`_iso(dt)` helper**, duplicated per-module rather than shared, to
  safely stringify a possibly-`None` Databricks timestamp.
- **Every write endpoint's schema file is read once at import time**
  (`Path(...).read_text()` at module scope), then `cursor.execute()`'d
  inline before the real `INSERT`, not re-read from disk on every
  request.
- **A `build_x(...)` plain function + a thin `@router` wrapper**, for
  every endpoint another module might want to reuse in-process
  (`build_comparison`, `build_round_trend`, `build_round_snapshots`,
  `build_negotiation_report`, `build_beta_pricing`). This is what lets
  `negotiation_report.py` pull from both `comparison.py` and `rounds.py`
  without an HTTP round trip.
