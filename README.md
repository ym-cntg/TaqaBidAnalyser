# TAQA Bid Analyzer — Maximo Integration Build-Out

This branch (`maximo-integrated-buildout`) starts rebuilding the bid-analyzer
application against TAQA's **real** Maximo procurement data (Databricks
Unity Catalog), now that `maximo-data-analysis` has established what the
real schema actually looks like — see `databricks/FINDINGS.md` for the full
write-up (confirmed real tender D-111808, the `RFQLINENUM` cross-vendor join
key, why `BOQITEMNUM` doesn't work, how documents are reachable, etc.).

## Progress

**Deployment proven**: a Databricks App on this branch successfully
connects to the SQL warehouse and queries Unity Catalog end-to-end
(`start.sh`/`app.yaml`, FastAPI on an internal port, Next.js on the
exposed port proxying `/api/*` to it).

**RFQ Browse/Search built**, now at `/rfqs`: a searchable/filterable table
of real RFQs, classified as Detailed BOQ / Shallow / Lump-sum / No pricing
data by actual `quotationline` structure (not the unreliable
`DETAILBOQAVAILABLE` flag — see `databricks/FINDINGS.md`'s "App
implementation" section for the exact query and expected numbers). The
list only ever loads RFQs with **more than 10 BOQ line items per vendor**
— lump-sum/shallow/no-pricing RFQs have no real BOQ to compare, so they're
excluded outright, not just filterable.

**Projects landing page built**, now at `/`: create a named "project"
mapped to exactly one RFQ (many projects can point at the same RFQ). Project
data lives in a new Unity Catalog Delta table
(`databricks/schema/bid_analyzer_projects.sql`) — **not yet writable**;
the app's service principal currently only has read (`USE CATALOG`/`USE
SCHEMA`/`SELECT`) access, so `POST /api/projects`/`POST
/api/users/identify` 503 with a clean permission error until a new admin
grant lands. "Who's using the app" is resolved without building real
auth: a forwarded Databricks Apps identity header is tried first
(**unverified whether this platform sends one**), falling back to a
self-reported name cached in the browser (`bid_analyzer_users.sql`). See
the "App implementation" section of `databricks/FINDINGS.md` for details.
Sections are being built one at a time — the actual BOQ line-item
comparison a project opens into isn't started yet.

- `backend/main.py` — app factory, mounts `rfqs`/`users`/`projects`
  routers; keeps `/api/rfq-count` as a lightweight connectivity smoke test.
- `backend/db.py` — the SQL warehouse connection helper + shared
  `escape_sql_literal()`.
- `backend/boq_classification.py` — the BOQ-category cache + thresholds,
  shared source of truth for any section that needs it.
- `backend/api/users.py` — identity resolution (`POST
  /api/users/identify`) against `bid_analyzer_users`.
- `backend/api/projects.py` — the Projects registry (`GET`/`POST
  /api/projects`, `GET /api/projects/{id}`) against `bid_analyzer_projects`.
- `databricks/schema/` — this app's own (not Maximo-ingested) table DDL;
  see its `README.md` for the convention.
- `frontend/` — Next.js + Tailwind v4 + shadcn/base-ui (ported from
  `full-feature-buildout` for visual consistency — none of that branch's
  comparison *logic* is reusable against real data, only its UI shell).
  Routes: `/` (Projects), `/rfqs` (RFQ Browse/Search), `/projects/[id]`
  (project detail stub).
- `start.sh` / `app.yaml` — Databricks Apps deployment plumbing, confirmed
  working against a real deployment.

## Running locally

```
cp .env.example .env   # fill in DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
uv sync
uv run uvicorn backend.main:app --reload --port 8001   # terminal 1 -- must match frontend/next.config.ts's rewrite target
cd frontend && npm install && npm run dev               # terminal 2
```

## Data source

Unity Catalog: **`ingestion_framework_test.bid_data_exploration`** — see
`databricks/FINDINGS.md` for everything confirmed about it so far, and
`databricks/notebooks/` for the exploration notebooks that got us here.

## What's kept from `maximo-data-analysis`

- `CLAUDE.md` — full project background.
- `project_details/` — original business-case materials.
- `databricks/` — all exploration notebooks and `FINDINGS.md`, kept as the
  reference for what the real schema actually contains.
