-- App-owned overlay of manually-corrected BOQ prices. Never written back
-- into quotationline (that's Maximo-ingested, not ours to mutate) --
-- applied as a display-time overlay by backend/api/comparison.py.
--
-- Requires CREATE TABLE + INSERT grants beyond the app service
-- principal's current SELECT-only access -- see databricks/FINDINGS.md.
CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_price_corrections (
    correction_id STRING    NOT NULL COMMENT 'Python uuid4().hex.',
    rfqnum        STRING    NOT NULL,
    rfqlinenum    DOUBLE    NOT NULL COMMENT 'Matches the float(RFQLINENUM) key comparison.py already uses.',
    vendor        STRING    NOT NULL,
    unit_cost     DOUBLE    NOT NULL COMMENT 'The corrected unit rate -- line_cost is derived at read time (qty x this), not stored, so there is one source of truth.',
    note          STRING             COMMENT 'Optional free-text reason.',
    corrected_by  STRING    NOT NULL COMMENT 'Informational FK to bid_analyzer_users.user_id.',
    corrected_at  TIMESTAMP NOT NULL COMMENT 'UTC. Append-only -- never updated/deleted; the latest row per (rfqnum, rfqlinenum, vendor) wins.'
)
USING DELTA
COMMENT 'App-owned overlay of manually-corrected BOQ prices. Never written back into quotationline -- applied as a display-time overlay by backend/api/comparison.py.';
