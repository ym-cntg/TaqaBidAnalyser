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

**BOQ line-item comparison built**, on the project detail page: side-by-
side bidder pricing per BOQ line (lowest price per line highlighted),
plus automated commercial flags (unquoted items, arithmetic errors, price
outliers, bidders who didn't submit at all). A **round selector** at the
top lets the analyst view the same grid at any later negotiation
revision, not just the original quote — a line not yet revised at a
given round carries forward its last known value (the same forward-fill
reconstruction the round-tracking dashboard uses, factored out into
`backend/api/round_snapshots.py` so both features share one
implementation). Arithmetic-error checks and manual price corrections
stay original-round only, since `DISCOUNTHISTORYLINE` only carries a
post-discount line total, not an independently-reported unit rate. **No
lot rollup** — just contract totals — since lots aren't modeled anywhere
in the real schema. Vendor names are resolvable via a `companies` table
(`companies.company = rfqvendor.VENDOR`) — unverified fully-qualified
location, first real use of this table. Pure read, so it works
independent of the Projects write-grant status. The outlier check
compares each line against a vendor's *own* typical pricing pattern
(a median/MAD-based z-score, threshold 3) rather than the raw peer
median — an earlier flat version flagged a consistently pricier or
cheaper vendor on nearly every line, which was just their overall price
level, not a real anomaly. A line can never show more than one outlier
— if two vendors both deviate on the same line, only the stronger
signal is flagged. See
`databricks/FINDINGS.md`'s "App implementation" section for flag
thresholds and the known-value spot check.

**Round-over-round tracking built**, a second tab on the project detail
page: a line chart + totals table of each vendor's contract total across
negotiation revisions, plus anomaly flags (a price that rises between
rounds; a discount far steeper than peers gave on the same line). Real
round history turned out to exist after all — `DISCOUNTHISTORY`/
`DISCOUNTHISTORYLINE`, never queried before this — layered over
`quotationline`'s original quote via a forward-fill reconstruction that's
correct whether Maximo stores each revision as a full snapshot or a
delta (unverified which; see `databricks/FINDINGS.md`). Chart palette is
the dataviz skill's validated reference categorical set, adopted as this
app's `--chart-1..5` tokens (the previously-ported ones were never
actually validated — this is the first real chart in the app).

**Price corrections built**: any cell in the comparison table (quoted,
zero-priced, or unquoted) can be manually corrected or filled in inline.
A `0` price is now flagged distinctly from `unquoted` (`zero_price`) and
excluded from the lowest-price/outlier logic — a real BOQ line's genuine
`AED 0` bid is almost always a data problem, not a legitimate free item.
Corrections are stored as an append-only overlay
(`bid_analyzer_price_corrections`) and applied at display time — **never**
written back into the Maximo-ingested `quotationline` table. A corrected
cell is trusted (its own flags are suppressed) but still fully
participates in `is_lowest`/`contract_total`. See `databricks/FINDINGS.md`.

**Negotiation-prep export built**, a third tab: closes CLAUDE.md's manual-
process step 6 ("prepare negotiation notes per bidder") by consolidating
the BOQ comparison and round-movement flags into one ranked, exportable
view — vendors sorted by contract total, % above lowest, flag-count
badges, and a capped/deduped top-issues list per vendor, plus an Excel
download. Deliberately **not LLM-generated** (a discussed, deliberate
scope cut — `full-feature-buildout`'s equivalent used Azure OpenAI for a
narrative recommendation; this version presents ranked facts only, no
"primary award," so the analyst draws their own conclusions). See
`databricks/FINDINGS.md`'s "App implementation" section for the digest
design and the one inherited limitation (top-issues detection is capped
the same way the comparison view already is, on very large BOQs).

**AI negotiation narrative built**, an "AI summary" card on the
negotiation-report tab: an on-demand, LLM-generated executive summary +
per-vendor observations layered on top of the deterministic report above
— additive, not a replacement, and never auto-generated (a user has to
click "Generate AI summary"). Built after the user closed out an AI
Impact Assessment for this project and **explicitly chose Databricks
Model Serving / AI Gateway** over a direct external API call, so vendor
pricing data never leaves TAQA's governed workspace. No award
recommendation field — advisory observations only, always under a
persistent "AI-generated — advisory only, not a decision" banner — and a
deterministic safety net strips (and logs as a caveat) any observation
referencing a vendor that isn't actually in this RFQ's real data, so a
hallucination can't slip through silently. `DATABRICKS_LLM_ENDPOINT` is
set in `app.yaml` to `databricks-claude-haiku-4-5` — a Databricks-hosted
foundation model endpoint, **confirmed working end-to-end on a real
deploy** (the app's own service principal does have query access). That
first live run also surfaced a real bug — a 9-vendor RFQ's response got
truncated before finishing valid JSON at the original 1200-token budget
— fixed by raising the budget and capping each vendor's write-up length
in the prompt so output size stays bounded regardless of vendor count.
See `databricks/FINDINGS.md`'s "App
implementation" section for the verified SDK call shape and the full
guardrails list.

**Beta AI-estimated pricing built**, a "Beta" column on the BOQ
Comparison table: an on-demand, per-line AI-estimated fair unit price,
requested via a "Generate Beta prices" button. **A deliberately
higher-risk AI feature than the narrative above** — flagged to the user
before building, since it asks the model to invent a price from its own
general knowledge (vendor quotes are given only as context, never as a
formula), the opposite of the narrative feature's "never invent a number
not in the data" rule. Built this way only after the user was told that
tradeoff and explicitly chose it. Every estimate carries a self-reported
confidence level and a one-line rationale, is capped and batched
(`BETA_LINES_CAP`/`BETA_BATCH_SIZE` in `backend/api/beta_pricing.py`) to
avoid repeating the narrative feature's real truncation bug at BOQ scale,
and is never persisted or computed automatically. The frontend renders it
in its own column, always italicized and confidence-styled, never using
the green/red "cheapest/priciest" coloring real vendor prices get, so it
can't be mistaken for a real quote. **Has not yet been through the AI
Impact Assessment / CoE review the narrative feature went through** —
a real open item, not a formality, given the different risk category.
See `databricks/FINDINGS.md`'s "App implementation" section for the full
design discussion and the three explicit choices the user made before
this was built.

- `backend/main.py` — app factory, mounts `rfqs`/`users`/`projects`/
  `comparison`/`beta_pricing`/`corrections`/`rounds`/`negotiation_report`/
  `negotiation_narrative` routers; keeps `/api/rfq-count` as a
  lightweight connectivity smoke test.
- `backend/api/llm_client.py` — shared Databricks Model Serving endpoint
  config, used by both `negotiation_narrative.py` and `beta_pricing.py`.
- `backend/db.py` — the SQL warehouse connection helper + shared
  `escape_sql_literal()`.
- `backend/boq_classification.py` — the BOQ-category cache + thresholds,
  shared source of truth for any section that needs it.
- `backend/api/users.py` — identity resolution (`POST
  /api/users/identify`) against `bid_analyzer_users`.
- `backend/api/projects.py` — the Projects registry (`GET`/`POST
  /api/projects`, `GET /api/projects/{id}`) against `bid_analyzer_projects`.
- `backend/api/comparison.py` — `GET /api/rfqs/{rfqnum}/comparison`
  (+ `?round=`), the BOQ line-item comparison + commercial flags +
  corrections overlay.
- `backend/api/beta_pricing.py` — `POST /api/rfqs/{rfqnum}/comparison/beta`,
  the AI-estimated "Beta" price layer on top of the comparison above.
- `backend/api/round_snapshots.py` — the shared forward-fill
  reconstruction (`build_round_snapshots()`) both `comparison.py`'s round
  selector and `rounds.py`'s trend chart are built on.
- `backend/api/corrections.py` — `POST /api/rfqs/{rfqnum}/corrections`
  against `bid_analyzer_price_corrections`.
- `backend/api/rounds.py` — `GET /api/rfqs/{rfqnum}/rounds`, the
  round-over-round trend + movement flags.
- `backend/api/negotiation_report.py` — `GET
  /api/rfqs/{rfqnum}/negotiation-report` (+ `.xlsx`), the ranked
  per-vendor digest combining comparison + round flags.
- `backend/api/negotiation_narrative.py` — `POST
  /api/rfqs/{rfqnum}/negotiation-report/narrative`, the AI-generated
  summary layer (Databricks Model Serving) on top of the digest above.
- `databricks/schema/` — this app's own (not Maximo-ingested) table DDL;
  see its `README.md` for the convention.
- `frontend/` — Next.js + Tailwind v4 + shadcn/base-ui (ported from
  `full-feature-buildout` for visual consistency — none of that branch's
  comparison *logic* is reusable against real data, only its UI shell).
  Routes: `/` (Projects), `/rfqs` (RFQ Browse/Search), `/projects/[id]`
  (project detail: BOQ comparison + round tracking + negotiation report
  tabs).
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
