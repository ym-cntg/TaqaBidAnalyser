-- App-owned storage for Excel-uploaded BOQs. NOT YET IN USE.
--
-- Uploaded BOQs currently live in a process-local store
-- (backend/uploads/store.py) because that needs no grant and therefore
-- actually works today, unlike every other bid_analyzer_* table. This
-- file is the design to switch to once CREATE TABLE + INSERT lands:
-- implement a DeltaUploadStore with the five UploadStore methods and
-- change the one line in get_store(). Nothing that reads uploads needs
-- to change.
--
-- Requires CREATE TABLE + INSERT/UPDATE/DELETE grants beyond the app
-- service principal's current USE CATALOG/USE SCHEMA/SELECT-only
-- access. See databricks/FINDINGS.md.
--
-- Three tables rather than one: a BOQ is a header, a set of lines, and
-- a price per (line, vendor, round). Flattening them would repeat every
-- line's description once per vendor per round.

CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_uploaded_boqs (
    project_id       STRING    NOT NULL COMMENT 'Python uuid4().hex. Used wherever an RFQNUM would be, including as the key for the correction/disqualification/partial-bid overlay tables.',
    name             STRING    NOT NULL COMMENT 'User-supplied project display name.',
    created_by       STRING    NOT NULL COMMENT 'Informational FK to bid_analyzer_users.user_id.',
    created_at       TIMESTAMP NOT NULL COMMENT 'UTC, generated in Python at insert time.',
    confirmed        BOOLEAN   NOT NULL COMMENT 'false while the analyst is still reviewing the extraction. The analysis tabs refuse to read an unconfirmed BOQ.',
    confirmed_at     TIMESTAMP          COMMENT 'UTC. Null until confirmed.'
)
USING DELTA
COMMENT 'Header row per Excel-uploaded BOQ project.';

CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_uploaded_lines (
    project_id       STRING    NOT NULL COMMENT 'FK to bid_analyzer_uploaded_boqs.project_id.',
    line_number      DOUBLE    NOT NULL COMMENT 'Stands in for Maximo RFQLINENUM. Assigned once in upload order and never recomputed, because every price is keyed to it.',
    item_no          STRING             COMMENT 'The vendor BOQ item number, e.g. "1.1.3". This is what cross-vendor line matching is based on.',
    description      STRING    NOT NULL COMMENT 'Line description, editable by the analyst before confirming.',
    unit             STRING             COMMENT 'Unit of measure.',
    quantity         DOUBLE             COMMENT 'BOQ quantity. Belongs to the BOQ, not to any one vendor.',
    section          STRING             COMMENT 'Nearest preceding section heading in the source sheet, for context.'
)
USING DELTA
COMMENT 'One row per BOQ line per uploaded project, shared across all vendors and rounds.';

CREATE TABLE IF NOT EXISTS ingestion_framework_test.bid_data_exploration.bid_analyzer_uploaded_prices (
    project_id       STRING    NOT NULL COMMENT 'FK to bid_analyzer_uploaded_boqs.project_id.',
    line_number      DOUBLE    NOT NULL COMMENT 'FK to bid_analyzer_uploaded_lines.line_number.',
    vendor           STRING    NOT NULL COMMENT 'Vendor code as entered by the analyst at upload time. Not validated against Maximo companies, since an uploaded bid need not be from a registered vendor.',
    round_label      STRING    NOT NULL COMMENT '"original", or the round as a float string such as "1.0". Must match the label vocabulary build_round_snapshots() produces, or the round selector breaks.',
    unit_cost        DOUBLE             COMMENT 'Null means the vendor did not quote this line, which is a real state and drives the unquoted flag.',
    line_cost        DOUBLE             COMMENT 'unit_cost * quantity, recomputed when the analyst edits either.'
)
USING DELTA
COMMENT 'One row per (line, vendor, round) in an uploaded project.';
