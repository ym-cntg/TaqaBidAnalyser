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

**Row count:** 412,896 (~13.6 invited-vendor rows per RFQ on average — this
is invitees, not just actual submitters)

**Schema (relevant columns):**

| Column | Type | Notes |
|---|---|---|
| `RFQNUM` | varchar(20) | FK back to `rfq.RFQNUM` |
| `VENDOR` | varchar(44) | **A vendor code (`001052`), not a company name.** No vendor/company master table exists among our current 7 tables/views — need to find one to resolve codes to names like "AGPOWER". |
| `CONTACT`, `PHONE`, `FAXPHONE`, `EMAIL` | various | A real contact person at the vendor, plus their details |
| `RFQVENDORID` | decimal(38,10) | This table's PK (one row per invited vendor per RFQ) |
| `BIDSTATUS` / `BIDSTATUSDATE` | varchar(25) / timestamp | Vendor's bid status — distribution pending |
| `SCORE` | decimal(16,2) | A per-vendor evaluation score |
| `TOTALAWARDCOST`, `TOTALDISCOUNT`, `TOTBIDCOSTWDIS`, `TOTBIDCOSTWODIS`, `TOTALAWARDCOSTWITHTAX`, `BASETOTALAWARDCOST`, `TOTAWDWODISCOUNT` | **binary** | ⚠️ Typed `binary`, not decimal, and every sample row shows the *identical* value (`CGTqea+foUw=`) across all 7 columns — looks encrypted/masked, not just unpopulated. Potential blocker for reading award/discount totals directly. |
| `TOTALAWARDCOSTWDIS`, `TOTALAWARDCOSTWITHTAXWDIS` | decimal(16,2) | Proper decimal equivalents exist alongside the binary ones — null in the (2003-era) sample, pending check on recent rows |
| `POSTBID_DISCOUNT_COUNTER`, `POSTBID_DISCOUNT_SENT`, `DISCOUNT_REVISION`, `DISCOUNT_SUBMISSION_DATE`, `DISCOUNT_APPLY_DATE`, `DISCOUNTSTATUS`, `DISCOUNT_APPLIED_AFTERBIDS/AFTERPI/BEFOREBIDS` | various | A rich post-bid-discount mechanism at the vendor level — same `DISCOUNT_REVISION` column as `rfq`, reinforcing (but not yet confirming) the negotiation-round theory |

**Key structural findings:**

1. **Vendor names aren't in this dataset at all** — `VENDOR` is a bare code.
   Resolving to real company names needs another table we haven't been given
   access to yet (a Maximo `COMPANIES`/vendor-master table almost certainly
   exists in the source system).
2. **Sample `RFQNUM` values carry a `-R1` suffix** (`D1752-R1`) — this raises
   a real possibility that **negotiation rounds are separate RFQ records**
   (a new RFQNUM per round) rather than the `DISCOUNT_REVISION` counter
   theorized from `rfq` alone. These might be two different concepts: a
   formal re-tender (new RFQNUM) vs. a lighter post-bid discount loop
   (`DISCOUNT_REVISION`/`POSTBID_DISCOUNT_COUNTER`) within one RFQ. **Needs
   clarifying with TAQA — this materially affects how "round" should be
   modeled if this data ever backs the app.**
3. **Several money columns are `binary`-typed and appear masked/encrypted**
   in the sample — if this holds on real recent tenders, reading actual
   award/discount amounts may require a different path (a decrypted view,
   an API, or the `WDIS` decimal columns instead).

## `quotationline` — priced BOQ line items

**Schema (relevant columns):**

| Column | Type | Notes |
|---|---|---|
| `RFQNUM`, `VENDOR` | varchar | Together, this is how a line joins back to `rfqvendor` — see correction below |
| `RFQLINENUM` | decimal(38,10) | A plain sequential line counter (1, 2, 3… up to 557+ seen) — **not** the hierarchical BOQ number |
| `QUOTATIONLINEID` | decimal(38,10) | This table's PK |
| `BOQITEMNUM` | varchar(15) | **Likely the real hierarchical item number** (the `1.2.3`-style numbering the sample data uses) — null in our sample rows (those happened to be simple catalog/material RFQs), pending a populated example |
| `ORDERQTY` / `ORDERUNIT` | decimal / varchar | Quantity and unit |
| `UNITCOST` / `LINECOST` | decimal(18,4) | Rate and line total — confirmed `LINECOST = ORDERQTY × UNITCOST` in the sample |
| `LINETYPE` | varchar(15) | Values seen: `MATERIAL`, `SERVICE`, `ITEM` — **leading theory: this is how CIF (supply) vs. Erection (install) is split**, as two rows sharing a `BOQITEMNUM` rather than two columns on one row. Unconfirmed. |
| `ISAWARDED` | decimal(38,10) | **Confirmed real and granular**: for tender `D19885308`, 3 vendors quoted the same items and only one vendor's specific lines show `ISAWARDED=1` — award decisions are tracked per line, per vendor, not just one winner per RFQ |
| `AWARDCOST` | decimal(14,4) | Populated the same as `LINECOST` regardless of `ISAWARDED` in the sample — looks like a default/suggested cost, not a live award-only value |
| `DISCOUNT_PERCENT`, `DISCOUNT_UNITCOST`, `DISCOUNT_APPLIED_AFTERBIDS`, `LINECOSTWDIS` | various | Discount/negotiation mechanics exist at the **line-item level** too — directly relevant to round-over-round price movement |
| `TAX1CODE`…`TAX5` | various | Up to 5 tax code/amount pairs per line |
| `QL1`-`QL5`, `QL_EXTRA1` | various | Custom extension fields — one showed values `QUOTED`/`TNA` (possibly a technical-acceptance status?), needs confirming which field this actually is |

**Key structural findings:**

1. **No separate CIF/Erection columns.** Only one `UNITCOST`/`LINECOST` pair
   per row. If `LINETYPE` (`MATERIAL` vs `SERVICE`) turns out to split CIF vs.
   Erection as two rows per `BOQITEMNUM`, that's a clean mapping — pending
   the follow-up query in `03_quotationline.ipynb`.
2. **Correction to the previous entry in this file:** I previously wrote that
   `quotationline.RFQVENDOR_ID` was "confirmed" to exist, based on a query in
   `06_cross_table_relationships.ipynb` being left uncommented after you
   edited it. That was a bad inference on my part — cell outputs are
   stripped when Databricks commits back to git, so I had no way to actually
   confirm that query succeeded rather than errored, and I shouldn't have
   implied otherwise. **The real schema of `quotationline` has no
   `RFQVENDORID`/`RFQVENDOR_ID` column at all.** The join back to
   `rfqvendor` is the **composite key `(RFQNUM, VENDOR)`**, which both
   tables have.
3. Sample data includes RFQs with 500+ sequential `RFQLINENUM`s — consistent
   with real large BOQs (~218 rows/lot in the sample data).
4. A third org, `TRANS`/`TRANSORG`, appears — reinforces that this dataset
   spans the whole legacy group, not just ADDC.

**Follow-ups added to `02_rfqvendor.ipynb` and `03_quotationline.ipynb`**
(need results): round-suffix distribution on `RFQNUM`, `BIDSTATUS`
distribution, `DISCOUNT_REVISION`/`POSTBID_DISCOUNT_COUNTER` distribution,
whether the `WDIS` decimal award columns populate on recent rows, a
populated `BOQITEMNUM` example, `LINETYPE` distribution and whether it pairs
up per `BOQITEMNUM`, which RFQs have 100+ lines (real BOQs), and a direct
search for `D-111808`.

## `altquotationline` — alternate/optional lines

**Schema:** near-identical to `quotationline` (same `RFQNUM`/`RFQLINENUM`/
`VENDOR`/`ITEMNUM`/`UNITCOST`/`LINECOST`/`LINETYPE`/`BOQITEMNUM`/`ISAWARDED`/
tax/discount columns), plus:

| Column | Type | Notes |
|---|---|---|
| `ALTQUOTATIONLINEID` | decimal(38,10) | This table's PK |
| `ALTQUOTLINEUID` | decimal(38,10) | **Likely FK back to a specific base `quotationline.QUOTATIONLINEID`** — i.e. "this is an alternate offered *for* that line". Unconfirmed, join query added. |
| `MANUFACTURERNAME` | varchar(254) | Full manufacturer name (vs. the short `MANUFACTURER` code both tables share) |
| `SERVICE` | decimal(38,10) | A separate boolean-ish column, distinct from `LINETYPE='SERVICE'` — meaning unclear, low priority |
| `QL2` | varchar(30) | **Likely the real technical-acceptance status field** — values seen: `QUOTED`, `TNA` (Technically Not Acceptable?). Same field/values also appeared in `quotationline`'s sample. |

**Key structural findings:**

1. The sample batch is routine MRO/stock-replenishment procurement (coffee,
   cardamom, tea, bearings, light fittings, hand tools) under `TRANSORG`
   (the transmission-company org seen earlier) — not a construction BOQ.
   Consistent with `quotationline`'s sample: **still no confirmed example of
   a populated `BOQITEMNUM` in either table.**
2. Alternates appear to be a general-purpose mechanism (any RFQ line can
   have a bidder-proposed substitute), not something specific to
   construction/BOQ tenders.
3. `QL2`'s `QUOTED`/`TNA` values are the closest thing to a per-line
   technical-acceptance signal seen so far — worth confirming the full
   distinct value set (only 2 values seen in a small sample).

## `docinfo` / `doclinks` / `vw_rfqvendor_documents` — attached documents

**Deliberately deferred** — notebook 5 was run, but we're intentionally not
digging into it yet and coming back to it later. Still important: this is
the table that determines whether actual bid documents (Excel/PDF) are
retrievable at all, or whether this is metadata-only. Pick up here next.

## Cross-table relationships

_Pending — the join key question this section originally flagged is now_
_resolved (see the correction under `quotationline` above): `(RFQNUM, VENDOR)`,_
_not a single FK id. `06_cross_table_relationships.ipynb`'s queries need_
_updating to match once `docinfo` findings are in too._

---

## Open questions for TAQA (carried over / refined from the original feature-list Excel)

- Confirm whether `DETAILBOQAVAILABLE` is really the data-gap signal, and
  what a reviewer is supposed to do when it's `N`.
- Confirm whether `DISCOUNT_REVISION`/`POSTBID_DISCOUNT_COUNTER` is the
  negotiation-round counter, **or** whether a round is actually a distinct
  RFQ record (the `-R1`-suffix pattern seen on some `RFQNUM`s in
  `rfqvendor`) — these may be two different things (formal re-tender vs.
  post-bid discount loop).
- Confirm how lots are modeled — `rfq` has no lot column, and
  `quotationline`'s `BOQITEMNUM` is null on the sample rows we've seen so
  far (all non-BOQ catalog RFQs).
- Confirm whether `LINETYPE` (`MATERIAL`/`SERVICE`) is really the CIF/
  Erection split.
- Confirm the current/active `ORGID` value(s) to filter to ADDC-relevant
  records only (this table appears to span the whole ADWEA group, plus at
  least one more entity, `TRANS`).
- Find/get access to a vendor/company master table — `rfqvendor.VENDOR` is
  a bare code with no name attached anywhere in our current 7 tables.
- Confirm whether the `binary`-typed award/discount-cost columns in
  `rfqvendor` are genuinely encrypted, and if so, what the supported way to
  read real values is (the `WDIS` decimal columns, a view, an API, etc).
- **`BOQITEMNUM` has been null in every sample row seen so far, across both
  `quotationline` and `altquotationline`** (both samples happened to be
  catalog/MRO-type RFQs, not construction BOQs) — still need one real
  populated example before the item-numbering theory can be called
  confirmed rather than just plausible.
