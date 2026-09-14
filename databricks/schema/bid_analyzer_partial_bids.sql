-- App-owned flag letting an analyst mark a vendor's bid on a given RFQ
-- as a deliberate partial-scope submission (they only bid part of the
-- BOQ on purpose, not by oversight) -- never written back into
-- rfqvendor/quotationline. Applied as a display-time overlay by
-- backend/api/comparison.py: a partial bidder's unquoted lines stop
-- counting as a flag against them, their contract total is annotated
-- with how much of the BOQ it actually covers, and they're excluded
-- from winning the vendor-summary "Lowest" badge (an apples-to-oranges
-- comparison against a full-scope bidder's total) -- they can still win
-- individual lines/split-award on whatever they did bid.
--
-- Requires CREATE TABLE + INSERT grants beyond the app service
-- principal's current SELECT-only access -- see databricks/FINDINGS.md.
CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_partial_bids (
    partial_bid_id STRING    NOT NULL COMMENT 'Python uuid4().hex.',
    rfqnum         STRING    NOT NULL,
    vendor         STRING    NOT NULL,
    is_partial     BOOLEAN   NOT NULL COMMENT 'true = marked as a partial bid, false = a later entry undoing an earlier mark.',
    note           STRING             COMMENT 'Optional free-text note (e.g. which lots/sections they bid).',
    marked_by      STRING    NOT NULL COMMENT 'Informational FK to bid_analyzer_users.user_id.',
    marked_at      TIMESTAMP NOT NULL COMMENT 'UTC. Append-only -- never updated/deleted; the latest row per (rfqnum, vendor) wins.'
)
USING DELTA
COMMENT 'App-owned flag letting an analyst mark a vendor bid on an RFQ as a deliberate partial-scope submission, changing how it is compared against full-scope bidders.';
