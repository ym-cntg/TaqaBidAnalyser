# TAQA Bid Analyzer — Maximo Integration Build-Out

This branch (`maximo-integrated-buildout`) starts rebuilding the bid-analyzer
application against TAQA's **real** Maximo procurement data (Databricks
Unity Catalog), now that `maximo-data-analysis` has established what the
real schema actually looks like — see `databricks/FINDINGS.md` for the full
write-up (confirmed real tender D-111808, the `RFQLINENUM` cross-vendor join
key, why `BOQITEMNUM` doesn't work, how documents are reachable, etc.).

## Where this branch starts

Deliberately narrow first step: a **bare-bones, one-page app** whose only
job is to prove a deployed Databricks App can actually reach and query the
real Unity Catalog tables. Nothing else yet — no comparison UI, no
extraction, no reporting. Get the deployment path working first, build
features on top of it once it's confirmed, rather than building against
assumptions about how Databricks Apps hosting/auth actually behaves.

- `backend/main.py` — FastAPI app, one real endpoint (`/api/rfq-count`)
  that connects to the SQL warehouse and returns a row count from `rfq`.
- `frontend/` — one Next.js page that calls it and displays either the
  count or a clear error message.
- `start.sh` / `app.yaml` — Databricks Apps deployment plumbing. **Not yet
  verified against a real deployment** — see the comments in both files.
  This first deploy attempt is expected to need small fixes to exact env
  var names / manifest schema; that's the point of testing it now rather
  than guessing further ahead.

## Running locally

```
cp .env.example .env   # fill in DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
uv sync
uv run uvicorn backend.main:app --reload --port 8000   # terminal 1
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
