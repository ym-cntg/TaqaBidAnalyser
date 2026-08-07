# App-owned schema

DDL for tables the app itself owns and writes to (as opposed to
`ingestion_framework_test.bid_data_exploration`'s Maximo-ingested tables,
which are read-only from this app's perspective).

No migration framework exists here -- one `.sql` file per table, checked in
as the reviewable source of truth. The backend runs each file's `CREATE
TABLE IF NOT EXISTS` statement lazily, on the write path that needs it, so
schema changes to an *existing* table need a manual `ALTER TABLE` run once
against the warehouse (not handled by this mechanism).

Both tables here need `CREATE TABLE`/`INSERT`/`UPDATE` grants for the app's
service principal, beyond the `USE CATALOG`/`USE SCHEMA`/`SELECT`-only
access it has today -- see `databricks/FINDINGS.md` for status.
