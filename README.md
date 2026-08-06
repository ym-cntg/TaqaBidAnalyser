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

**Section 1 built — RFQ Browse/Search** (the app's landing page): a
searchable/filterable table of real RFQs, classified as Detailed BOQ /
Shallow / Lump-sum / No pricing data by actual `quotationline` structure
(not the unreliable `DETAILBOQAVAILABLE` flag — see
`databricks/FINDINGS.md`'s "App implementation" section for the exact
query and expected numbers). The list only ever loads RFQs with **more
than 10 BOQ line items per vendor** — lump-sum/shallow/no-pricing RFQs
have no real BOQ to compare, so they're excluded outright, not just
filterable. Sections are being built one at a time — later sections (RFQ
detail with vendor/line-item comparison, award analysis, document
metadata) aren't started yet.

- `backend/main.py` — app factory, mounts `backend/api/rfqs.py`'s router;
  keeps `/api/rfq-count` as a lightweight connectivity smoke test.
- `backend/db.py` — the SQL warehouse connection helper.
- `backend/boq_classification.py` — the BOQ-category cache + thresholds,
  shared source of truth for any future section that needs it.
- `frontend/` — Next.js + Tailwind v4 + shadcn/base-ui (ported from
  `full-feature-buildout` for visual consistency — none of that branch's
  comparison *logic* is reusable against real data, only its UI shell).
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
