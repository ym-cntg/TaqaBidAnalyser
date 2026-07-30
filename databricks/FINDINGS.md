# Maximo data findings

Running log of what the real Unity Catalog tables (`ingestion_framework_test.bid_data_exploration`)
actually contain, as notebooks get run and results come back. Updated as we
go — treat anything marked "pending" as not yet confirmed.

---

## `rfq` — tender / RFQ header

**Row count:** 30,338

**Schema (relevant columns):**

| Column | Type | Notes |
|---|---|---|
| `RFQNUM` | varchar(20) | Tender/RFQ number — business key. Format varies across the table's history (`G1663`, `G-D2157`, `A11096521` all seen) — no single consistent pattern. |
| `DESCRIPTION` | varchar(254) | Free-text tender description |
| `STATUS` | varchar(50) | Lifecycle status (`CLOSE`, `CANCEL` seen in sample) |
| `STAGE` | varchar(16) | A second lifecycle field — distinct from `STATUS`, meaning unclear yet |
| `TENDERSTATUS` | varchar(50) | A *third* status-like field |
| `ORGID` / `SITEID` | varchar(8) | Organization/site — sample shows both `ADWEAORG`/`ADWEA` and `ADDCORG`/`ADDC`. **This table spans the whole legacy ADWEA group, not just ADDC/TAQA.** Any real query needs to filter on this. |
| `ENTERDATE` | timestamp | Sample rows range 2002–2018 — this table has ~20+ years of history |
| `PMETHOD` | varchar(20) | Procurement method (`SELECTIVE` seen) |
| `TOTALAWVALUE` / `TOTALCOST` / `ESTIMATEDCOST` | decimal(18,4) | Money fields at the RFQ level |
| `DETAILBOQAVAILABLE` | varchar(1) | **Leading candidate for the sample data's `data_gap` flag** (ELMEC-style: no real per-item BOQ) — pending distribution check |
| `DISCOUNT_REVISION` | decimal(38,10) | **Leading candidate for "which negotiation round"** — pending distribution check |
| `POSTBID_DISCOUNT_CLOSEDATE` / `EXT_POSTBID_DISCOUNT_CLOSEDATE` | timestamp | Supports the round/negotiation theory above |
| `BIDBOND`, `PERFBOND`, `BIDBONDVALUE`, `RETENTIONAPPLIED`, `RETENTIONPERCENT`, `ADVANCEPAYMENT*` | various | Commercial terms — richer than anything the sample-data model captures today |
| `TDCOMMENTS`/`TDENDORSEDATE`/`TDRESULT`, `BUDGENH*`, `BLA*` | various | An extensive multi-stage approval/endorsement workflow (technical committee, budget/finance, board-level) with no equivalent in the current app at all |

**Key structural findings:**

1. **No lot column anywhere.** D-111808's 3 lots (SHBPRY, DRPRY, SMHPRY) have
   no home in `rfq`. Either lots are separate RFQ records each, or the lot
   concept lives in `quotationline` instead. **Open — check `quotationline`
   schema for a lot indicator, and check whether 3 RFQNUMs with a shared
   prefix/description exist for a known real tender.**
2. **No explicit round column** in the header — `DISCOUNT_REVISION` is the
   best candidate for "which negotiation round" a quote belongs to, but that
   needs to be confirmed on `rfqvendor`/`quotationline` too, since a revision
   counter at the RFQ level might not track *per-vendor* rounds.
3. **This table is NOT ADDC/power-only.** It's the shared Maximo instance
   across the whole ADWEA group's history. Real analysis needs an `ORGID`
   filter (`ADDC` at minimum) and probably a recent-date filter — the raw
   `LIMIT 20` sample was 19 rows from 2002-2004 and one from 2018, nothing
   resembling current tender activity.
4. **`DETAILBOQAVAILABLE`** plausibly maps to the sample data's `data_gap`
   concept (bidders with no real priced BOQ, like ELMEC) — pending
   distribution check.

**Follow-up queries added to `01_rfq.ipynb`** (need results):
- Search for a real D-111808-equivalent (`DESCRIPTION LIKE '%substation%'`)
- Recent RFQs only (`ENTERDATE >= '2024-01-01'`)
- `ORGID`/`SITEID` distribution
- `STATUS`/`STAGE`/`TENDERSTATUS` distinct values
- `DETAILBOQAVAILABLE` distribution
- `DISCOUNT_REVISION` distribution

---

## `rfqvendor` — one row per bidder submission

_Pending — notebook not yet run/shared._

## `quotationline` — priced BOQ line items

_Pending — notebook not yet run/shared. This is the highest-priority table_
_once schema comes in: it should show whether CIF/Erection map cleanly, how_
_lots are distinguished (if `rfq` truly has none), and whether item numbering_
_matches the ADDC-standard template the sample data assumes._

## `altquotationline` — alternate/optional lines

_Pending — notebook not yet run/shared._

## `docinfo` / `doclinks` / `vw_rfqvendor_documents` — attached documents

_Pending — notebook not yet run/shared._

## Cross-table relationships

_Pending — needs `rfqvendor`/`quotationline` schemas confirmed first. One_
_data point already in hand: `quotationline.RFQVENDOR_ID` exists as a real_
_column (confirmed by running the query in `06_cross_table_relationships.ipynb`_
_rather than just guessing it) — the FK from `quotationline` back to_
_`rfqvendor` is `RFQVENDOR_ID`._

---

## Open questions for TAQA (carried over / refined from the original feature-list Excel)

- Confirm whether `DETAILBOQAVAILABLE` is really the data-gap signal, and
  what a reviewer is supposed to do when it's `N`.
- Confirm whether `DISCOUNT_REVISION` is the negotiation-round counter, and
  whether it's per-RFQ or per-vendor.
- Confirm how lots are modeled — separate RFQs, or something in
  `quotationline` — since `rfq` itself has no lot column.
- Confirm the current/active `ORGID` value(s) to filter to ADDC-relevant
  records only (this table appears to span the whole ADWEA group).
