# Databricks exploration notebooks

## Running this

This repo is connected to the Databricks workspace via **Databricks
Repos** (git-backed). To run the exploration notebook:

1. In the Databricks workspace, open this repo under **Repos** and make
   sure you're on the `maximo-data-analysis` branch (pull if needed).
2. Open `databricks/explore_bid_data.py` — Databricks renders it as a
   notebook automatically (the `# Databricks notebook source` header and
   `# COMMAND ----------` cell markers are Databricks' native notebook
   format, not a custom convention).
3. Attach it to a cluster and run all cells.

No credentials are needed in this repo for this — the notebook uses the
`spark` session Databricks provides natively inside the workspace, and
reads directly from Unity Catalog (`ingestion_framework_test.bid_data_exploration`)
using whatever access the attached cluster/your identity already has.

## Why notebooks, not a local script

The alternative would be a local Python script using
`databricks-sql-connector` with a workspace host + personal access token
stored in `.env`. That's more setup (and a credential to manage) for no
benefit here — the whole point of Databricks Repos is that code lives in
git but *runs* in the workspace with its own auth. If a local/CI query
path is ever needed later (e.g. to feed the bid-analyzer backend from
outside Databricks), that's a deliberate follow-up, not a default.

## Files

- `explore_bid_data.py` — schema/row-count/sample exploration of all 7
  tables in `ingestion_framework_test.bid_data_exploration`, with
  "Observations" cells to fill in per table as findings come in.
