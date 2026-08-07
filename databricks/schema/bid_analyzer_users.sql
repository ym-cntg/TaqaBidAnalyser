-- App-owned user registry. Not real authentication -- see
-- backend/api/users.py for the identity-resolution strategy (forwarded
-- Databricks Apps identity header if one exists, else a self-reported
-- display name cached client-side).
--
-- Requires CREATE TABLE + INSERT/UPDATE grants beyond the app service
-- principal's current USE CATALOG/USE SCHEMA/SELECT-only access -- not yet
-- granted as of the commit that added this file. See databricks/FINDINGS.md.
CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_users (
    user_id       STRING    NOT NULL COMMENT 'Python uuid4().hex, generated once per distinct identity (by email if forwarded-header identity is confirmed, else by self-reported display name).',
    display_name  STRING    NOT NULL COMMENT 'Shown in the UI. Equal to the forwarded email/username if platform identity was available, else self-reported.',
    email         STRING             COMMENT 'Populated only when a forwarded-identity header was present -- UNVERIFIED whether Databricks Apps actually sends one. NULL for self-reported users.',
    created_at    TIMESTAMP NOT NULL COMMENT 'UTC, generated in Python at insert time.'
)
USING DELTA
COMMENT 'App-owned user registry. Not real authentication -- see backend/api/users.py for the identity-resolution strategy.';
