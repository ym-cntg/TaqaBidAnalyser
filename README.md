# TAQA Bid Analyzer — Maximo Data Analysis

This branch (`maximo-data-analysis`) is a clean-room exploration of TAQA's
**real** Maximo procurement data, now landed in Databricks Unity Catalog, as
a prerequisite to extending the bid-analyzer application (see `CLAUDE.md`
for the full project background — business case, manual process, sample
tender data) to work against real data instead of the hand-curated sample
set in `data/power` and `data/water`.

## Why this branch is bare-bones

The full application (FastAPI backend, Next.js frontend, all the
sample-data extraction/comparison/reporting logic) lives on
`full-feature-buildout`. It's deliberately **not** carried over here: this
branch's job is to understand the shape of the real Maximo tables first,
not to build features against an assumption of what they contain. Once the
real schema is understood, the relevant pieces get built (or ported) with
that knowledge — rather than guessing now and reworking later, the same
lesson learned from the water-tender sample data turning out to have a
different BOQ schema than power's (see `full-feature-buildout`'s
`PROGRESS.md`, 2026-07-20 entry).

## What's here

- `CLAUDE.md` — full project background (kept from the main line of work).
- `project_details/` — original business-case materials (kept).
- `databricks/` — notebook-style exploration scripts for the Unity Catalog
  tables TAQA has landed. See `databricks/README.md`.

## Data source

Unity Catalog: **`ingestion_framework_test.bid_data_exploration`**

| Table | Likely maps to |
|---|---|
| `rfq` | Tender / Request for Quotation header |
| `rfqvendor` | One row per bidder submission against an RFQ |
| `quotationline` | Bidder's priced BOQ line items |
| `altquotationline` | Alternate/optional quotation lines |
| `docinfo` | Attached-document metadata |
| `doclinks` | Links between documents and RFQ/vendor records |
| `vw_rfqvendor_documents` | View joining vendor submissions to their documents |

These mappings are inferred from table/column names and TAQA's manual
process (`project_details/power_transcript.md`) — not yet confirmed against
real rows. That confirmation is exactly what the exploration notebook is
for.
