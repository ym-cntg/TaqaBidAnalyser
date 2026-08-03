# Databricks exploration notebooks

## Running these

This repo is connected to the Databricks workspace via **Databricks
Repos** (git-backed). To run the exploration notebooks:

1. In the Databricks workspace, open this repo under **Repos** and make
   sure you're on the `maximo-data-analysis` branch (pull if needed).
2. Open any notebook under `databricks/notebooks/` — they're real `.ipynb`
   files, Databricks renders them with the standard notebook UI directly.
3. Attach to a cluster and run all cells, in order (01 → 06) — `06` builds
   on column names you'll only know after running `02` and `03`.

No credentials are needed in this repo for this — each notebook's `%sql`
cells run against the `spark` session Databricks provides natively inside
the workspace, reading directly from Unity Catalog
(`ingestion_framework_test.bid_data_exploration`) using whatever access the
attached cluster/your identity already has.

## Why notebooks, not a local script

The alternative would be a local Python script using
`databricks-sql-connector` with a workspace host + personal access token
stored in `.env`. That's more setup (and a credential to manage) for no
benefit here — the whole point of Databricks Repos is that code lives in
git but *runs* in the workspace with its own auth. If a local/CI query
path is ever needed later (e.g. to feed the bid-analyzer backend from
outside Databricks), that's a deliberate follow-up, not a default.

## Files — one targeted notebook per table/concern, not one giant script

| Notebook | Covers |
|---|---|
| `01_rfq.ipynb` | `rfq` — tender/RFQ header |
| `02_rfqvendor.ipynb` | `rfqvendor` — one row per bidder submission |
| `03_quotationline.ipynb` | `quotationline` — priced BOQ line items (the core data) |
| `04_altquotationline.ipynb` | `altquotationline` — alternate/optional lines |
| `05_documents.ipynb` | `docinfo`, `doclinks`, `vw_rfqvendor_documents` — attached documents |
| `06_cross_table_relationships.ipynb` | Joins across tables + a summary checklist to fill in once 01-05 are done |
| `07_trace_bid_with_boq.ipynb` | Traces one real `DETAILBOQAVAILABLE = 'Y'` tender end-to-end across every table |
| `08_trace_bid_without_boq.ipynb` | Traces D-111808 (established "no itemized BOQ" example) and a `null`-flagged tender end-to-end, for comparison against `07` |
| `09_client_walkthrough_boq_analysis.ipynb` | Client-facing walkthrough: what % of RFQs have a real detailed BOQ (with charts), how rounds are tracked, lump-sum examples, and the 4 open questions for TAQA |

Notebooks 01-05 follow the same shape: what the table is expected to
represent, `DESCRIBE TABLE`, a row count, a 20-row sample, and an
"Observations" cell to fill in once you've actually looked at it — that
write-up is the real deliverable, not the raw query output. 06 is
cross-table joins instead. 07/08 are single-bid end-to-end traces (see
below) — they use a Databricks widget (`dbutils.widgets.text(...)`) so you
can paste in a real `RFQNUM` from a candidates query and re-run the rest of
the notebook against it. 09 is different in kind from the rest: it's
Python-first (not `%sql` cells) with `spark.sql(...)` + `plotly` charts,
meant to be run once and presented directly to TAQA rather than iterated
on query-by-query.
