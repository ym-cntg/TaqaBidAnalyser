-- App-owned overlay letting an analyst manually disqualify a vendor's
-- BOQ line from commercial evaluation, without ever writing back into
-- quotationline (that's Maximo-ingested, not ours to mutate). Add-only
-- relative to Maximo's own QL2 technical-acceptance status: this can
-- flag a line QL2 never caught, and an analyst can undo their own entry
-- (a later row with disqualified=false), but it can never re-qualify a
-- real QL2='TNA' rejection back to qualified -- comparison.py merges the
-- two with an OR, so Maximo's status always wins regardless of what's
-- written here. Applied as a display-time overlay by
-- backend/api/comparison.py.
--
-- Requires CREATE TABLE + INSERT grants beyond the app service
-- principal's current SELECT-only access -- see databricks/FINDINGS.md.
CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_line_disqualifications (
    disqualification_id STRING    NOT NULL COMMENT 'Python uuid4().hex.',
    rfqnum               STRING    NOT NULL,
    rfqlinenum           DOUBLE    NOT NULL COMMENT 'Matches the float(RFQLINENUM) key comparison.py already uses.',
    vendor               STRING    NOT NULL,
    disqualified         BOOLEAN   NOT NULL COMMENT 'true = disqualified, false = a later entry undoing an earlier manual disqualification.',
    reason               STRING             COMMENT 'Optional free-text reason.',
    disqualified_by      STRING    NOT NULL COMMENT 'Informational FK to bid_analyzer_users.user_id.',
    disqualified_at      TIMESTAMP NOT NULL COMMENT 'UTC. Append-only -- never updated/deleted; the latest row per (rfqnum, rfqlinenum, vendor) wins.'
)
USING DELTA
COMMENT 'App-owned overlay letting an analyst manually disqualify a BOQ line from commercial evaluation, independent of (and additive to) Maximo QL2 status.';
