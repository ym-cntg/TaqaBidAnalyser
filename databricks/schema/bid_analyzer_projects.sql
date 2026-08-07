-- App-owned, mutable project registry. Unlike the Maximo-ingested tables
-- in this schema, lowercase snake_case columns and an app-chosen name
-- mark this as NOT part of the ingestion pipeline.
--
-- Requires CREATE TABLE + INSERT/UPDATE grants beyond the app service
-- principal's current USE CATALOG/USE SCHEMA/SELECT-only access -- not yet
-- granted as of the commit that added this file. See databricks/FINDINGS.md.
CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_projects (
    project_id       STRING    NOT NULL COMMENT 'Python uuid4().hex.',
    user_id          STRING    NOT NULL COMMENT 'Informational FK to bid_analyzer_users.user_id -- validated at insert time by the API, not a DB constraint.',
    name             STRING    NOT NULL COMMENT 'User-supplied project display name.',
    rfqnum           STRING    NOT NULL COMMENT 'Informational FK to rfq.RFQNUM -- validated at insert time by the API, not a DB constraint.',
    created_at       TIMESTAMP NOT NULL COMMENT 'UTC, generated in Python at insert time, not a SQL DEFAULT (unverified whether column defaults work on this warehouse).'
)
USING DELTA
COMMENT 'App-owned, mutable project registry. Unlike the Maximo-ingested tables in this schema, lowercase snake_case columns and an app-chosen name mark this as NOT part of the ingestion pipeline.';
