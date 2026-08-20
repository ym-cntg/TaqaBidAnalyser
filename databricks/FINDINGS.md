# Maximo data findings

Running log of what the real Unity Catalog tables (`ingestion_framework_test.bid_data_exploration`)
actually contain, as notebooks get run and results come back. Updated as we
go — treat anything marked "pending" as not yet confirmed.

**Status: Run 2 complete for notebooks 01-04. Notebooks 07/08 (single-bid
end-to-end traces) also complete for 07 and Part 1 of 08** — see the new
section below for major corrections these surfaced (`BOQITEMNUM` is not how
real detailed BOQs are structured; documents are real and queryable).
Notebook 05 (`docinfo`/`doclinks`/documents) is still formally un-run as its
own notebook, but 07/08 already pulled real schema + data from the same
tables. Notebook 06 (cross-table) and `01_rfq.ipynb`'s Run 3 section are
still pending results. Notebook 08's Part 2 (`null`-flagged example) needs
a re-run — it was left with an empty widget, so it returned no data; use
`N-19899` (a good candidate, see below).

---

## Headline finding: D-111808 is real, and it changes the picture

The exact sample tender from `CLAUDE.md` — **D-111808**, "Construction
contract for the Replacement of Shobaisi, Samha and DRA Primary Substation in
Eastern Region" — exists in the real data with that near-verbatim
description (matches "3 primary substations in Eastern Region: SHBPRY, DRPRY,
SMHPRY"). That's a strong, welcome confirmation the sample data is grounded
in a real tender, not fabricated. But looking at the real rows for it
surfaces two things that don't match the demo's assumptions:

1. **`quotationline` holds only ONE lump-sum price line per vendor for this
   tender — no itemized BOQ breakdown at all.** 8 vendors quoted, each with
   exactly one row: `BOQITEMNUM = null`, `LINETYPE = MATERIAL`, `DESCRIPTION`
   = the full tender description (not a BOQ item description), `LINECOST` =
   their entire bid total. The ~218-line-per-lot itemized BOQ detail that the
   sample Excel files contain **does not exist as structured Maximo data for
   this RFQ** — if it exists anywhere on the Maximo side, it's only inside
   the bidder's actual attached document, which is exactly what notebook 05
   (deferred) needs to check.
2. **The real bidder pool and award don't match the two-bidder demo
   narrative.** `rfqvendor` shows 22 vendors invited; 8 actually submitted
   priced lines. One value lines up exactly: vendor `99473989` quoted
   **179,400,000.0000**, matching AL Geemi's "Original" round total
   (179.4M) in `CLAUDE.md` exactly — good sign that code = AL Geemi. But the
   row Maximo marks `ISAWARDED = 1` is vendor `001938` at **142,459,514.10**
   — a bidder/price that matches neither AL Geemi (179.4M) nor AGPOWER's
   estimated ~64.2M. **Now doubly confirmed**: `rfq.TOTALAWVALUE` for
   D-111808 is exactly `142,459,514.1000` — the header-level award total
   matches vendor `001938`'s line independently, via a completely different
   table/column. This is a real, corroborated award, not a data artifact.
   Full list of the 8 real quoted totals:

   | Vendor code | Total quoted | `ISAWARDED` |
   |---|---|---|
   | 001565 | 234,651,862.00 | 0 |
   | 001938 | 142,459,514.10 | **1 (awarded)** |
   | 99102876 | 208,545,844.64 | 0 |
   | 99107175 | 195,458,685.00 | 0 |
   | 99443592 | 221,525,111.00 | 0 |
   | 99456349 | 161,562,485.08 | 0 |
   | 99473989 | 179,400,000.00 | 0 — likely AL Geemi |
   | 9958404 | 149,332,885.00 | 0 |

   AGPOWER's ~64.2M (itself only an estimate, summed from lot files with "no
   combined total in their files" per `CLAUDE.md`) isn't close to any of
   these 8. Either AGPOWER's structured Maximo total was never captured this
   way (plausible — `CLAUDE.md` already flags PDF-submitted bids as the
   "biggest pain point" for manual data entry), or the demo's sample-data
   scenario diverges from what actually happened on this real tender. **This
   needs a straight answer from TAQA before treating the sample data's
   negotiation-round story as representative of real outcomes.**

---

## Notebooks 07/08 — single-bid end-to-end traces (major corrections here)

Traced one real `DETAILBOQAVAILABLE = 'Y'` tender (`N-19535`, chosen as the
richest candidate) end-to-end through every table, and did the same for
D-111808. Two of these results overturn earlier theories.

### D-111808's own `rfq` row, checked for the first time

`DETAILBOQAVAILABLE = null` — **not `Y` or `N`.** This directly answers the
open question from `01_rfq.ipynb`'s Run 3. D-111808 is a fully real, awarded,
124M-estimated / 142.46M-awarded construction tender — not an edge case —
and its flag was simply never set. **This is strong evidence `null` means
"never assessed", not "no BOQ"** — a genuinely important, high-value tender
falls into the 98.2%-null bucket alongside whatever else is in there.
Also: `TOTALCOST = 124,000,000.0000` (likely the internal budgeted/estimated
cost, distinct from `ESTIMATEDCOST` which is `null` here) vs. the real award
of 142.46M — the award came in ~15% over the internal cost figure.
`DISCOUNT_REVISION = 3` at the header level matches vendor `001938`'s
`DISCOUNT_REVISION`/`POSTBID_DISCOUNT_COUNTER` (both `3`) exactly — another
clean confirmation of the round mechanism. `PMETHOD = 'SAO'` — a
procurement-method code not seen before.

### `BOQITEMNUM` is NOT how real detailed BOQs are structured — correction to Run 2's softened theory

`N-19535` (400kV OHL works, ~307M AED, `DETAILBOQAVAILABLE = 'Y'`, 9 invited
vendors) has **2,480 real `quotationline` rows — and every single one has
`BOQITEMNUM = null`.** This is the richest, most detailed real BOQ we've
seen yet, and the column we originally thought was "the real hierarchical
item number" is entirely unpopulated on it. What actually carries the
structure instead:
- **`RFQLINENUM`** — plain sequential position (1, 2, 3…), same as always.
- **`DESCRIPTION`** carries real hierarchy and pricing-type information as
  free text — e.g. `"Section : 1 - LILO OF 400kV D/C OHL PVDF (PV2) - PVAJ
  (PV3) to HFRG"` for a section-header row, and item descriptions with
  `"(ERECTION PRICE / LOCAL)"` suffixed directly onto the text.
- **`ORDERUNIT = 'HEADER'`** on section-break rows (with `UNITCOST`/
  `LINECOST` both `null`) — a textual marker for a non-priced heading row
  mixed into the same flat line sequence as real priced rows.
- `LINETYPE` was uniformly `SERVICE` across the sample seen here — doesn't
  split CIF/Erection for this tender either; that distinction, if present,
  lives in the `DESCRIPTION` text itself (`"ERECTION PRICE"`) rather than a
  structured column.
- `ISAWARDED` at the line level: 539 of 2,480 lines marked awarded (21.7%)
  — real, granular, per-line award data on a genuinely large multi-vendor
  BOQ, consistent with the pattern already confirmed on `D19885308`.

**Correction:** `BOQITEMNUM` should not be treated as the general mechanism
for item-level structure — it appears to populate only for certain
smaller catalog/material/service RFQs (as seen in Run 2's `D19892718`/
`N-20711.1` examples), not for large detailed construction/works BOQs like
`N-19535`. The real, general parsing target for line-item structure is
**`RFQLINENUM` order + `DESCRIPTION` text patterns**, not `BOQITEMNUM`.

**Good news:** `DETAILBOQAVAILABLE = 'Y'` *did* correlate with a genuinely
rich, real, multi-vendor detailed BOQ here (2,480 lines, 9 vendors) — the
flag has real signal for "this is a detailed procurement", even though the
`BOQITEMNUM` column doesn't cooperate.

### `RFQLINENUM` confirmed as the real cross-vendor join key (replaces `BOQITEMNUM`)

Directly tested on `N-19535`'s 4 vendors who actually submitted (out of 9
invited — `003235`, `003300`, `99134662`, `99471778`): **620 distinct
`RFQLINENUM` values, each appearing exactly once per vendor** (620 × 4 =
2,480 rows, zero duplicate `(RFQLINENUM, VENDOR)` pairs), and **100% of
them have identical `DESCRIPTION`/`ORDERQTY`/`ORDERUNIT` across all 4
vendors — zero mismatches.** Only `UNITCOST`/`LINECOST` vary by vendor, as
expected for genuinely independent pricing against a shared template. E.g.
`RFQLINENUM = 6` ("30 Meter depth (ERECTION PRICE / LOCAL)") shows
`UNITCOST` of `null` (vendor `003235`, a real unquoted-item case), `11,000`,
`6,229`, and `38,000` for the other three — same item, four different
prices.

**This means `RFQLINENUM` (scoped to `RFQNUM`) is the reliable line-item
join key for comparing vendors on the same tender — not `BOQITEMNUM`,**
consistent with ADDC's standardized BOQ template (same line-numbered
template to every bidder, prices filled in against fixed line numbers).
Confirmed on one real example so far (a strong test — 620 real lines, not
trivial) — worth a second spot-check on another detailed BOQ before treating
this as a hard rule for pipeline logic, but this is exactly what a
comparison tool needs and didn't have before this notebook.

### Lots and rounds inside the BOQ itself

**Rounds leave a real trace at the line-item level — but only as a
before/after snapshot, not a history.** On `N-19535`'s real data:
`LINECOST` (original quote) vs. `LINECOSTWDIS` (post-discount price) differ
on 1,146 of 2,480 lines (46%), with `DISCOUNT_PERCENT` varying **per line**
(0%, 4.29%, 13.86%, 14.72%, even 100% on some lines) — not one blanket
vendor-wide discount. `DISCOUNT_APPLIED_AFTERBIDS` is set on 1,843/2,480
lines (74%). **But `quotationline` has no round-number column and no
change-timestamp** — only `ENTERDATE` (a single initial-entry stamp, no
`CHANGEDATE`). So this table only ever shows original-vs-final state; if
there were multiple negotiation rounds, the intermediate ones are
overwritten, not preserved. The header-level `DISCOUNT_REVISION` counter
(`rfq`/`rfqvendor`) remains the only record of *how many* rounds happened —
`quotationline` just shows the net effect of however many there were.
`DISCOUNT_UNITCOST` was 100% null in this sample — appears unused, at least
here. `QUOTESTARTDATE`/`QUOTEENDDATE` were also 100% null.

**Correction (2026-08-14): the round-by-round history above DOES exist —
just not in `quotationline`.** The user identified two tables never
queried in this codebase: `DISCOUNTHISTORY` and `DISCOUNTHISTORYLINE`.
`DISCOUNTHISTORYLINE` has `RFQNUM`/`VENDOR`/`REVISION`/`RFQLINENUM`/
`LINECOSTWDIS` — a per-line price snapshot at each negotiation revision,
joinable back to `quotationline` via the already-confirmed `RFQLINENUM`
cross-vendor key. `DISCOUNTHISTORY` (header/event level) adds `STAGE`,
`ENTERDATE`, `DISCOUNT_SUBMISSION_DATE`, `DISCOUNT_APPLY_DATE` per
`(RFQNUM, VENDOR, REVISION)`. See the "App implementation: round-over-round
tracking" section near the end of this file for the query design and what
remains unverified (this codebase's first use of both tables — no live
data seen yet).

**Lots have no structural home anywhere — confirmed, not just assumed.**
- No column named anything like `LOT` in any of the 4 line-item/header
  schemas (checked directly across all `DESCRIBE` output pulled so far).
- **D-111808 itself has zero lot-suffixed `RFQNUM` variants** — re-checked
  the `RFQNUM LIKE 'D-111808%'` results already pulled in `02_rfqvendor` and
  `03_quotationline`: only the exact `D-111808` appears, no `-L1`/`-L2`/etc.
  Combined with the one-lump-sum-line-per-vendor finding, this strongly
  suggests **ADDC's real 3-substation lot split (SHBPRY/DRPRY/SMHPRY) was
  never captured in Maximo's structured tables for this tender at all** — if
  it exists anywhere, it's only inside the bidder's attached document.
- The word "lot" does appear as free text, but means something unrelated:
  on `N-19535`, `"Lot = 13 KM"` (204 hits) is a batch-pricing unit — price
  per 13km segment of cable — not a tender-lot division. Separately, Run
  2's `N-17334` example had `BOQITEMNUM` values literally `"LOT 01"`/
  `"LOT 02"`/`"LOT 03"` — a real but apparently one-off, ad-hoc usage, not a
  consistent mechanism reused elsewhere.

### Documents are real, richly populated, and queryable — via `vw_rfqvendor_documents`

Schema (discovered live, notebook 05 itself still not formally run):
`docinfo` (36 columns) and `doclinks` (39 columns) are complex, but
**`vw_rfqvendor_documents`** is a clean, pre-joined, lowercase-named view:
`rfqnum`, `vendor`, `bidstatus`, `rfqvendorid`, `ownertable`, `docinfoid`,
`document`, `urlname`.

Filtering it by `rfqnum = 'N-19535'` returned **386 real rows** — actual
named documents per vendor: bid bonds (`"TENDER BOND N-19535-AED 400K"`),
tender docs, manpower histograms, technical submission folders
(`"FOLDER NO. 4.3 VENDOR DOCUMENTS"`), narrative program assumptions, etc.
**`urlname` is a Windows UNC file path** on an internal file server, e.g.:
```
\\advapfsn02\LinkedDocs\DoclinkProd\doclinks\EBID\TECHBID\FolderNo.4.3VendorDocuments.pdf
```
**This resolves the long-standing open question**: document *metadata* is
real, rich, and fully queryable via Unity Catalog/SQL right now. Actual
document *content* is not — it lives on an on-prem Windows file share
(`advapfsn02`), which Databricks SQL has no path to. Retrieving real file
content would need a separate integration (VPN/network path access, or
whatever this file server has been migrated to, if anything) — a genuinely
different and larger piece of work than anything SQL-only can solve.

**D-111808's own documents were not actually checked** in this run (the
query was left commented out) — fixed and ready to run next time
(`08_trace_bid_without_boq.ipynb`, Part 1).

### Part 2 of `08` (the `null`-flagged example) didn't actually run

The widget (`null_rfqnum`) was left empty, so every Part 2 query returned 0
rows — this wasn't a real test yet. From the candidates query that *did*
run, though, one signal jumped out already: **`N-19899`** (a `null`-flagged
fire-alarm-system blanket agreement, 38,740 lines, 5 vendors) has **7,748
distinct `BOQITEMNUM` values** — populated, unlike `N-19535`'s `Y`-flagged
example which had zero. That's an early hint that `BOQITEMNUM` population
and `DETAILBOQAVAILABLE` may be close to *independent* signals, not
correlated in either direction. Flagged as the candidate for next run
(notebook and its widget are ready — just needs `N-19899` pasted in).

---

## `rfq` — tender / RFQ header

**Row count:** 30,338

**Schema (relevant columns):**

| Column | Type | Notes |
|---|---|---|
| `RFQNUM` | varchar(20) | Tender/RFQ number — business key. Format varies across the table's history (`G1663`, `G-D2157`, `A11096521`, `D-111808` all seen) — no single consistent pattern. |
| `DESCRIPTION` | varchar(254) | Free-text tender description |
| `STATUS` | varchar(50) | Lifecycle status — see distribution below |
| `STAGE` | varchar(16) | **Confirmed 100% null across all 30,338 rows.** Not populated anywhere in this table — treat as a dead/unused column, at least at this snapshot. |
| `TENDERSTATUS` | varchar(50) | A publish-cycle status, distinct from `STATUS` — see distribution below |
| `ORGID` / `SITEID` | varchar(8) | Organization/site — confirmed spans 7 orgs, see distribution below |
| `ENTERDATE` | timestamp | Confirmed live/current — rows go up to 2026-07-22, current statuses (`INPRG`, `SENT`, `APPRV`) alongside 20+ years of closed history |
| `PMETHOD` | varchar(20) | Procurement method (`SELECTIVE` seen) |
| `TOTALAWVALUE` / `TOTALCOST` / `ESTIMATEDCOST` | decimal(18,4) | Money fields at the RFQ level — **null on every recent row checked**, so award totals live elsewhere (`rfqvendor`/`quotationline`), not here |
| `DETAILBOQAVAILABLE` | varchar(1) | Confirmed real but **rare** — see distribution below |
| `DISCOUNT_REVISION` | decimal(38,10) | Confirmed real, behaves like a round counter — see distribution below |
| `POSTBID_DISCOUNT_CLOSEDATE` / `EXT_POSTBID_DISCOUNT_CLOSEDATE` | timestamp | Supports the round/negotiation theory above |
| `BIDBOND`, `PERFBOND`, `BIDBONDVALUE`, `RETENTIONAPPLIED`, `RETENTIONPERCENT`, `ADVANCEPAYMENT*` | various | Commercial terms — richer than anything the sample-data model captures today |
| `TDCOMMENTS`/`TDENDORSEDATE`/`TDRESULT`, `BUDGENH*`, `BLA*` | various | An extensive multi-stage approval/endorsement workflow (technical committee, budget/finance, board-level) with no equivalent in the current app at all |

**Distributions (Run 2 results):**

- **`STATUS`**: `CLOSE` 21,677 · `CANCEL` 7,414 · `AWDAPV` 542 · `INPRG` 189 ·
  `SENT` 157 · `COMEVAL` 128 · `COMP` 116 · `TECHEVAL` 72 · `APPRV` 38 ·
  `BLREVIEW` 4 · `AMEND` 1
- **`TENDERSTATUS`**: `null` 20,827 · `PUBLISHED` 8,975 · `REPUBLISHED` 527 ·
  `RECALLED` 9 — so ~2/3 of rows predate whatever process started populating
  this field; likely only relevant for more recent tenders.
- **`ORGID`/`SITEID`**: `ADDCORG`/`ADDC` 10,077 · `TRANSORG`/`TRANS` 6,735 ·
  `AADCORG`/`AADC` 6,251 · `ADWEAORG`/`ADWEA` 4,987 · `AMPCORG`/`AMPC` 1,809 ·
  `ADSSCORG`/`ADSSC` 392 · `BPCORG`/`BPC` 86 · one stray row with
  `ORGID=ADWEAORG` but `SITEID=ADDC` (data-quality noise, 1 row). **7 real
  orgs beyond just ADDC** — confirms real filtering is required for any
  ADDC-only analysis.
- **`DETAILBOQAVAILABLE`**: `null` 29,785 · `Y` 412 · `N` 141. Confirmed real
  and populated, but **rare** — only ~1.8% of all RFQs have this flag set at
  all. Whatever process sets it is selective (probably only construction/BOQ
  tenders), not universal.
- **`DISCOUNT_REVISION`**: `null` 27,833, then monotonically decreasing counts
  as the number increases — `1`→1,305, `2`→662, `3`→294, `4`→146, `5`→57,
  `6`→26, `7`→6, `8`→3, `9`→2, `10`→1, `11`→2, `12`→1. This shape (fewer
  tenders reach each successive round) is exactly what a real negotiation-
  round counter should look like — **strong support that this is the round
  mechanism**, at least for the "post-bid discount" style of negotiation.

**Key structural findings:**

1. **D-111808 confirmed real** — see headline finding above.
2. **No lot column anywhere.** D-111808's 3 lots (SHBPRY/DRPRY/SMHPRY) have
   no home in `rfq`, and (per the headline finding) `quotationline` doesn't
   show line-level detail for this RFQ either — so lots may simply not be
   modeled in Maximo's structured tables at all for this tender; they may
   only exist inside the bidder's document. Still open.
3. **`DISCOUNT_REVISION` looks like the real round counter** — the
   distribution shape is convincing. Still needs reconciling with the rare
   `-R1`/`-R2` `RFQNUM` suffix pattern found in `rfqvendor` (see below) —
   these appear to be two different, occasionally-overlapping mechanisms,
   not one.
4. **`DETAILBOQAVAILABLE`** is real but rare (553 of 30,338 rows). **Now
   checked directly: D-111808's own value is `null`**, not `Y` or `N` (see
   "Notebooks 07/08" section above) — despite being a fully real, awarded
   124M+ construction tender. That's strong evidence `null` means "never
   assessed", not "no BOQ" — treating it as a clean `data_gap` proxy is not
   safe. It does still correlate with real richness where it IS set to `Y`
   (confirmed on `N-19535`, 2,480 real lines) — just don't trust the null
   bucket to mean absence.
5. **`STAGE` is dead weight** — 100% null, don't rely on it for anything.

---

## `rfqvendor` — one row per bidder submission

**Row count:** 412,896 (~13.6 invited-vendor rows per RFQ on average — this
is invitees, not just actual submitters)

**Schema (relevant columns):**

| Column | Type | Notes |
|---|---|---|
| `RFQNUM` | varchar(20) | FK back to `rfq.RFQNUM` |
| `VENDOR` | varchar(44) | **A vendor code (`001052`), not a company name.** No vendor/company master table exists among our current 7 tables/views — need to find one to resolve codes to names like "AGPOWER". |
| `CONTACT`, `PHONE`, `FAXPHONE`, `EMAIL` | various | A real contact person at the vendor, plus their details — confirmed populated with real names on D-111808's rows |
| `RFQVENDORID` | decimal(38,10) | This table's PK (one row per invited vendor per RFQ) |
| `BIDSTATUS` / `BIDSTATUSDATE` | varchar(25) / timestamp | Vendor's bid status — see distribution below |
| `SCORE` | decimal(16,2) | A per-vendor evaluation score — **null on every row checked so far**, including recent ones; may only populate post-technical-evaluation |
| `TOTALAWARDCOST`, `TOTALDISCOUNT`, `TOTBIDCOSTWDIS`, `TOTBIDCOSTWODIS`, `TOTALAWARDCOSTWITHTAX`, `BASETOTALAWARDCOST`, `TOTAWDWODISCOUNT` | **binary** | ⚠️ Typed `binary`, every sample row shows the *identical* value (`CGTqea+foUw=`) across all 7 columns — looks encrypted/masked. Still unresolved; not re-tested directly in Run 2. |
| `TOTALAWARDCOSTWDIS`, `TOTALAWARDCOSTWITHTAXWDIS` | decimal(16,2) | **Confirmed populated on recent (2026) rows** — real, readable values (e.g. 790.00, 2,292.00, 9,634.08), mostly 0.00 where nothing's been awarded yet. This is the real, usable path to award totals — use these, not the binary columns. |
| `POSTBID_DISCOUNT_COUNTER`, `POSTBID_DISCOUNT_SENT`, `DISCOUNT_REVISION`, `DISCOUNT_SUBMISSION_DATE`, `DISCOUNT_APPLY_DATE`, `DISCOUNTSTATUS`, `DISCOUNT_APPLIED_AFTERBIDS/AFTERPI/BEFOREBIDS` | various | A rich post-bid-discount mechanism at the vendor level — **confirmed to track tightly with `rfq.DISCOUNT_REVISION`** (see below) |

**Distributions (Run 2 results):**

- **`RFQNUM` round-suffix** (`regexp_extract(RFQNUM, '-(R[0-9]+)$')`): no
  suffix 412,386 · `R1` 499 · `R2` 11. **The suffix pattern is rare** (~0.12%
  of rows) — this weakens the "rounds are separate RFQ records" theory as
  the *primary* mechanism. It looks more like an occasional formal re-tender
  path, while `DISCOUNT_REVISION` (present on ~12% of rows once you exclude
  nulls at the `rfqvendor` level too) is the everyday post-bid-negotiation
  loop.
- **`BIDSTATUS`**: `null` 221,159 · `SUBMITTED` 61,766 · `NOT SIGNED` 49,862 ·
  `REGRETTED` 31,467 · `COLLECTED` 28,750 · `NOT COLLECTED` 14,094 ·
  `NOT QUOTED` 3,629 · `PI SUBMITTED` 2,023 · `WITHDRAWN` 146. Real
  lifecycle: most invited vendors never actually submit (collected/not
  collected/not signed dominate over submitted).
- **`DISCOUNT_REVISION` × `POSTBID_DISCOUNT_COUNTER`**: overwhelmingly
  `null`/`null` (400,386 of 412,896 — most vendor rows never enter a
  discount round at all), and where populated, the two columns move
  together in lockstep (e.g. `1`/`1` → 3,834 rows, `2`/`2` → 1,892, `3`/`3` →
  878) with only small drift between them. **Confirms these two columns are
  the real, working round-tracking mechanism** at the vendor level, not
  independent counters.

**Key structural findings:**

1. **Vendor names aren't in this dataset at all** — `VENDOR` is a bare code.
   Resolving to real company names needs another table we haven't been given
   access to yet (a Maximo `COMPANIES`/vendor-master table almost certainly
   exists in the source system). One code is now tentatively identified by
   price match: `99473989` ≈ AL Geemi (see headline finding).
2. **`DISCOUNT_REVISION`/`POSTBID_DISCOUNT_COUNTER` is the real round
   mechanism**, confirmed by both the `rfq`-level distribution shape and the
   vendor-level lockstep pairing. The `-R1`/`-R2` `RFQNUM` suffix is real but
   rare — likely a separate, occasional "formal re-tender" path rather than
   the everyday negotiation loop. **Both exist; they are not the same
   thing.**
3. **The `WDIS` decimal columns are the usable award-total path** — confirmed
   populated on real recent rows. The parallel `binary`-typed columns still
   look masked/encrypted and remain unresolved, but they no longer block
   anything since a working alternative exists.
4. **D-111808 confirmed**: 22 invited vendors, real contact names, all dated
   April 2023, mixed `BIDSTATUS` (`SUBMITTED`, `COLLECTED`, `REGRETTED`,
   `NOT SIGNED`) — only 8 of the 22 actually made it into `quotationline`
   with a priced line (see headline finding).

---

## `quotationline` — priced BOQ line items

**Row count:** 1,660,753

**Schema (relevant columns):**

| Column | Type | Notes |
|---|---|---|
| `RFQNUM`, `VENDOR` | varchar | Together, this is how a line joins back to `rfqvendor` — confirmed composite key, no single FK column exists |
| `RFQLINENUM` | decimal(38,10) | A plain sequential line counter (1, 2, 3… up to 500+ seen) — **not** the hierarchical BOQ number |
| `QUOTATIONLINEID` | decimal(38,10) | This table's PK |
| `BOQITEMNUM` | varchar(15) | **Populated — but not a clean universal hierarchical code.** See correction below. |
| `ORDERQTY` / `ORDERUNIT` | decimal / varchar | Quantity and unit |
| `UNITCOST` / `LINECOST` | decimal(18,4) | Rate and line total — confirmed `LINECOST = ORDERQTY × UNITCOST` in the sample |
| `LINETYPE` | varchar(15) | **5 distinct values found**, not just MATERIAL/SERVICE — see distribution below. CIF/Erection-split theory not confirmed — see correction below. |
| `ISAWARDED` | decimal(38,10) | **Confirmed real and granular** — tracked per line, per vendor. Also confirmed directly on D-111808 (see headline finding: vendor `001938`'s single line is the one marked awarded). |
| `AWARDCOST` | decimal(14,4) | Populated the same as `LINECOST` regardless of `ISAWARDED` in the sample — looks like a default/suggested cost, not a live award-only value |
| `DISCOUNT_PERCENT`, `DISCOUNT_UNITCOST`, `DISCOUNT_APPLIED_AFTERBIDS`, `LINECOSTWDIS` | various | Discount/negotiation mechanics exist at the **line-item level** too |
| `TAX1CODE`…`TAX5` | various | Up to 5 tax code/amount pairs per line |
| `QL1`-`QL5`, `QL_EXTRA1` | various | Custom extension fields — `QL2` confirmed as a technical-acceptance-style status field (see `altquotationline` distribution — same field, same values, on both tables) |

**Distributions / findings (Run 2 results):**

- **`LINETYPE`**: `SERVICE` 1,032,113 · `ITEM` 351,248 · `MATERIAL` 277,304 ·
  `STDSERVICE` 78 · `TOOL` 10. **5 categories, not a clean binary** —
  `MATERIAL`/`SERVICE` alone don't cover most rows (`ITEM` is actually the
  second-largest category).
- **`BOQITEMNUM` populated example found** (tender `D19892718`, a fuse
  supply RFQ): values like `3001013.80`, `3000213.50`, `3001013.125`,
  `3001813.160` — a code-like string, not `1.2.3`-style hierarchy. A
  *different* tender (`N-20711.1`, a services contract) shows plain small
  integers (`1`, `5`, `6`, `8`...`14`) as `BOQITEMNUM` instead. **Format is
  tender-specific, not a single universal ADDC numbering scheme** — softer
  finding than previously assumed.
- **`BOQITEMNUM` grouping test** (`GROUP BY RFQNUM, VENDOR, BOQITEMNUM` +
  `COLLECT_SET(LINETYPE)`): groups are often much larger than 2 — e.g. 117,
  49, 13, 12, 11, 9, 8 rows sharing one `BOQITEMNUM` — and in most of those
  groups **`COLLECT_SET(LINETYPE)` returns a single value** (`List(SERVICE)`
  or `List(MATERIAL)`), not two. **This disproves the "2 rows per
  `BOQITEMNUM`, MATERIAL+SERVICE = CIF+Erection" theory as a general rule.**
  Real examples show `BOQITEMNUM` values like `"PART 1"`, `"HEADER"`,
  `"LOT 01"`, `"STAGE IB"` — these read as **coarse section/lot labels
  shared by many distinct line items**, not a unique per-item identifier.
  One tender (`N-17334`) does show `List(SERVICE, MATERIAL)` together under
  one `BOQITEMNUM` — so the CIF/Erection-via-LINETYPE pairing can happen,
  but it's not the dominant pattern.
- **Real BOQ scale confirmed**: RFQs with 100+ lines exist up to **52,398
  lines** (`N-20585`, 9 vendors) and **42,336** (`N-18709`, 9 vendors) — real
  detailed procurements are far larger than the sample data's ~218-row lots.
- **D-111808 in this table**: only **8 rows total, one per vendor, no BOQ
  detail** — see headline finding. This is the single most important
  correction from Run 2: **for this specific tender, the itemized per-line
  BOQ pricing does not exist in Maximo's structured data.** If it exists at
  all on the Maximo side, it must be inside the attached bid document
  (notebook 05's territory).

**Key structural findings:**

1. **No separate CIF/Erection columns**, and — contrary to the earlier
   theory — **no consistent 2-rows-per-`BOQITEMNUM` CIF/Erection split
   either.** `LINETYPE` splitting is real in some tenders but not the
   general rule.
2. **`BOQITEMNUM` is often a coarse grouping/section label, not a unique
   item number** — this is a correction to the "hierarchical item number"
   theory from Run 1. It may still carry hierarchy in *some* tenders (worth
   checking `N-17334`'s `LOT 01`/`02`/`03` pattern further), but it isn't
   safe to assume line-item granularity from this column alone. **Further
   correction (notebook 07, see "Notebooks 07/08" section above): on
   `N-19535` — a large, real, `DETAILBOQAVAILABLE='Y'` BOQ with 2,480 lines
   — `BOQITEMNUM` is null on every single row.** The real structural
   mechanism for a big detailed works/construction BOQ is `RFQLINENUM`
   sequence + free-text `DESCRIPTION` (including `ORDERUNIT='HEADER'`
   marker rows for section breaks, and CIF/Erection-type annotations
   embedded directly in the description text) — not `BOQITEMNUM` at all.
   `BOQITEMNUM` seems to populate mainly for smaller catalog/material/
   service RFQs instead.
3. Join back to `rfqvendor` is the composite key `(RFQNUM, VENDOR)`, **not**
   a single `RFQVENDORID`/`RFQVENDOR_ID` FK column — confirmed, no such
   column exists in this table (correcting an earlier bad inference from
   Run 1, see prior note below).
4. **`ISAWARDED` genuinely tracks award status per vendor per line** —
   directly confirmed on D-111808's real data (vendor `001938`'s one line is
   the awarded one, at 142.46M — see headline finding for why that's
   surprising).
5. A third org, `TRANS`/`TRANSORG`, appears — reinforces that this dataset
   spans the whole legacy group, not just ADDC.

_Note kept from Run 1: I previously wrote that `quotationline.RFQVENDOR_ID`_
_was "confirmed" to exist, based only on an uncommented query in_
_`06_cross_table_relationships.ipynb` — that was a bad inference (outputs_
_are stripped on git commit, so I had no way to know if that query had_
_actually succeeded). Run 2's real `DESCRIBE` output confirms no such column_
_exists; the join is `(RFQNUM, VENDOR)`._

---

## `altquotationline` — alternate/optional lines

**Row count:** 42,668 (vs. `quotationline`'s 1,660,753 — alternates are rare,
~2.6% of base line volume)

**Schema:** near-identical to `quotationline` (same `RFQNUM`/`RFQLINENUM`/
`VENDOR`/`ITEMNUM`/`UNITCOST`/`LINECOST`/`LINETYPE`/`BOQITEMNUM`/`ISAWARDED`/
tax/discount columns), plus:

| Column | Type | Notes |
|---|---|---|
| `ALTQUOTATIONLINEID` | decimal(38,10) | This table's PK |
| `ALTQUOTLINEUID` | decimal(38,10) | **Theory disproved (see below)** — not a working FK to `quotationline.QUOTATIONLINEID` |
| `MANUFACTURERNAME` | varchar(254) | Full manufacturer name (vs. the short `MANUFACTURER` code both tables share) |
| `SERVICE` | decimal(38,10) | A separate boolean-ish column, distinct from `LINETYPE='SERVICE'` — meaning unclear, low priority, not investigated further |
| `QL2` | varchar(30) | **Confirmed: a real technical-acceptance status field** — full value set below |

**Distributions / findings (Run 2 results):**

- **`ALTQUOTLINEUID` → `quotationline.QUOTATIONLINEID` join test**: returned
  **zero rows.** The join key theory from Run 1 is **disproved** — this
  column does not link to `quotationline`'s PK, at least not directly by
  equality. What it actually references is now an open question again (a
  different ID namespace? a different table entirely, not among our 7?).
- **`QL2` full value set**: `QUOTED` 41,027 · `TNA` 1,387 · `NOQUOTE` 182 ·
  `Cancel` 51 · `CNA` 21. Confirmed as a real technical-acceptance-style
  status field with 5 values (not just the 2 seen in the Run 1 sample).
- **`BOQITEMNUM` example** (tender `N-16578`): many rows share
  `BOQITEMNUM = "PART 1"` with completely different `DESCRIPTION`s (network
  equipment part numbers like `WS-C2960X-48FPD-L`, `C9500-16X-A`) —
  reinforces the `quotationline` correction: `BOQITEMNUM` here is a coarse
  section label, not a unique item code.
- **D-111808 has zero rows in this table** — no alternates were offered for
  this tender.

**Key structural findings:**

1. The sample batch is routine MRO/stock-replenishment procurement (coffee,
   cardamom, tea, bearings, light fittings, hand tools, network switches)
   under `TRANSORG` mostly — not construction BOQs. Still no confirmed
   example of `BOQITEMNUM` behaving as a unique per-item identifier in
   either table — it consistently reads as a section/lot/part grouping
   label.
2. Alternates are a general-purpose, relatively rare mechanism (2.6% of base
   line volume) — not something specific to construction/BOQ tenders.
3. `ALTQUOTLINEUID`'s real purpose is still unknown — the FK-to-base-line
   theory didn't survive testing. Low priority to chase further unless
   alternates become relevant to a real workflow.

---

## `docinfo` / `doclinks` / `vw_rfqvendor_documents` — attached documents

**No longer a black box** — notebook 05 itself is still formally un-run, but
notebooks 07/08 pulled real schema and data from these tables directly (see
"Notebooks 07/08" section above for full detail). Summary:

- `docinfo` (36 cols) and `doclinks` (39 cols) have complex schemas — not
  yet fully explored.
- **`vw_rfqvendor_documents` is a clean, ready-to-use, pre-joined view**:
  `rfqnum`, `vendor`, `bidstatus`, `rfqvendorid`, `ownertable`, `docinfoid`,
  `document`, `urlname` (note: lowercase column names, unlike every other
  table). Filtering by `rfqnum` works and returns real rows — 386 for
  `N-19535` alone (bid bonds, tender docs, technical submissions, etc).
- **Document metadata is real and fully queryable via SQL right now.**
  Document *content* is not — `urlname` is a Windows UNC path
  (`\\advapfsn02\LinkedDocs\DoclinkProd\doclinks\...`) on an on-prem file
  share Databricks SQL can't reach. Retrieving actual file bytes would need
  a separate integration, not more SQL.
- D-111808's own documents specifically haven't been checked yet — query is
  ready in `08_trace_bid_without_boq.ipynb` (Part 1), just needs a re-run.

---

## Cross-table relationships (`06_cross_table_relationships.ipynb`)

**Not productively advanced in Run 2.** Both queries in this notebook are
still stale:
- The "vendors per RFQ" query is still commented out (never run).
- The "quotation lines per vendor submission" query still references a
  placeholder column (`rfqvendor_id`) that doesn't exist in `quotationline`
  — it errored with `AnalysisException` when run, as expected now that we
  know the real join is `(RFQNUM, VENDOR)`.

This notebook needs a rewrite using the columns now confirmed real:
`rfqvendor.RFQVENDORID` as the PK, and `(RFQNUM, VENDOR)` as the join back
from `quotationline`/`altquotationline`. Not done yet — flagging as the
clear next step once notebook 05 unblocks or in parallel with it.

---

## Open questions for TAQA (updated after notebooks 07/08)

- **The vendor-price discrepancy on D-111808** (headline finding): the real
  Maximo-recorded award (vendor `001938`, 142.46M, now doubly confirmed via
  `rfq.TOTALAWVALUE` matching exactly) doesn't match either named bidder's
  numbers in the sample data. Need to understand whether the sample data
  represents a different scenario/round than what's in Maximo, or whether
  AGPOWER's real structured total was simply never captured this way.
- Where is the itemized BOQ line-item detail for a real construction tender
  like D-111808, if not in `quotationline`? Given `N-19535` (a genuinely
  detailed real BOQ) structures itself via `RFQLINENUM` + free-text
  `DESCRIPTION` rather than `BOQITEMNUM`, D-111808's single lump-sum line
  may just mean this particular tender's pricing was never broken into line
  items in Maximo at all (lump-sum bidding), not that the detail exists
  elsewhere and we're missing it. Worth a direct question to TAQA rather
  than more digging.
- ~~Confirm how lots are modeled~~ **Largely answered**: no lot column or
  indicator exists anywhere (`rfq`, `quotationline`, `altquotationline`),
  and D-111808 has zero lot-suffixed `RFQNUM` variants — lots appear to
  simply not be captured in Maximo's structured tables at all for this
  tender. Remaining question for TAQA: is this true generally, or does some
  other tender actually split lots as separate RFQNUMs (worth one more
  spot-check on a known multi-lot tender before generalizing)?
- ~~`quotationline` shows real per-line discount data but no round-number
  or change-timestamp column — confirm whether intermediate round history
  exists anywhere in Maximo~~ **Answered**: `DISCOUNTHISTORY`/
  `DISCOUNTHISTORYLINE` hold exactly this (see the "round-by-round
  history" correction above and the "App implementation: round-over-round
  tracking" section below). Remaining question for TAQA: whether each
  `REVISION`'s `DISCOUNTHISTORYLINE` rows are a full snapshot of every
  line the vendor has priced, or only the lines that changed at that
  revision — the app's reconstruction is written to produce correct
  totals either way (forward-fill), but confirming the real shape would
  remove the need for that hedge.
- Reconcile the two round mechanisms: `DISCOUNT_REVISION`/
  `POSTBID_DISCOUNT_COUNTER` (common, ~12% of vendor rows, lockstep-paired)
  vs. the `-R1`/`-R2` `RFQNUM` suffix (rare, ~0.12% of rows) — are these
  really two different real-world processes (post-bid discount loop vs.
  formal re-tender), or does one supersede the other in practice?
- ~~Is `BOQITEMNUM`'s coarse-grouping behavior intentional/standard?~~
  **Largely answered**: it doesn't populate at all for large detailed
  works BOQs (`N-19535`, 2,480 lines, all null) — real structure lives in
  `RFQLINENUM` + `DESCRIPTION` text instead, and `RFQLINENUM` is now
  confirmed as a working cross-vendor join key on that same example (100%
  match on `DESCRIPTION`/`ORDERQTY`/`ORDERUNIT` across all 4 submitting
  vendors, 620 lines). Remaining question: is there *any* tender type where
  `BOQITEMNUM` carries genuine unique per-item meaning, or is it
  effectively vestigial across the board?
- Find/get access to a vendor/company master table — `rfqvendor.VENDOR` is
  a bare code; `99473989` is now tentatively AL Geemi by price match, but
  this needs a real lookup table to confirm and scale.
- Confirm whether the `binary`-typed award/discount-cost columns in
  `rfqvendor` are genuinely encrypted — lower priority now that the `WDIS`
  decimal columns are confirmed as a working alternative path to real
  award totals.
- What does `ALTQUOTLINEUID` actually reference, now that the
  `quotationline.QUOTATIONLINEID` join theory is disproved?
- Confirm the current/active `ORGID` value(s) to filter to ADDC-relevant
  records only — 7 orgs confirmed present (`ADDC`, `TRANS`, `AADC`, `ADWEA`,
  `AMPC`, `ADSSC`, `BPC`).
- **New**: is there any supported way to reach the actual document files
  behind `vw_rfqvendor_documents.urlname` (the `advapfsn02` UNC file
  share), or has that content been migrated somewhere network-reachable
  from Databricks/the app? This determines whether real bid documents can
  ever be pulled programmatically, or only manually.
- ~~Can bid documents be retrieved via `docinfo`/`doclinks`, or is this
  metadata-only?~~ **Answered**: metadata only, from SQL. Real content
  needs separate file-share access (see above).

---

## App implementation: BOQ classification query (`backend/boq_classification.py`)

The `maximo-integrated-buildout` app's RFQ Browse page classifies every RFQ
by real `quotationline` detail rather than trusting `DETAILBOQAVAILABLE`
(confirmed unreliable above). This is the exact query, checked in here as
ground truth per its own verification plan:

```sql
WITH boq_stats AS (
    SELECT RFQNUM, COUNT(*) / COUNT(DISTINCT VENDOR) AS avg_lines_per_vendor
    FROM ingestion_framework_test.bid_data_exploration.quotationline
    GROUP BY RFQNUM
),
invited AS (
    SELECT RFQNUM, COUNT(DISTINCT VENDOR) AS invited_vendor_count
    FROM ingestion_framework_test.bid_data_exploration.rfqvendor
    GROUP BY RFQNUM
)
SELECT r.RFQNUM, r.ORGID,
       COALESCE(inv.invited_vendor_count, 0) AS vendor_count,
       bs.avg_lines_per_vendor
FROM ingestion_framework_test.bid_data_exploration.rfq r
LEFT JOIN boq_stats bs ON bs.RFQNUM = r.RFQNUM
LEFT JOIN invited inv ON inv.RFQNUM = r.RFQNUM
```

Thresholds: no `boq_stats` row → `no_pricing_data`; `avg_lines_per_vendor <= 1`
→ `lump_sum`; `<= 9` → `shallow`; else → `detailed_boq`.

**Expected result across all 30,338 RFQs** (from the notebook 09 client
walkthrough, first real run): Lump-sum 10,903 (35.9%, AED 62.8B recorded
value — the highest-value bucket), Shallow 9,893 (32.6%, AED 28.2B),
Detailed BOQ 3,289 (10.8%, AED 47.3B), No pricing data 6,253 (20.6%, AED
48M). Sums to 30,338.

**Known-value spot check**: `search=D-111808` on the app's `/api/rfqs`
endpoint should return exactly one row — `boq_category = "lump_sum"`,
`vendor_count = 22` (invited, from `rfqvendor` — not the 8 who actually
priced), `total_award_value = 142459514.10`.

If the app's live numbers diverge meaningfully from the percentages above,
check the threshold boundaries first (`<=1`/`<=9`) before assuming the
underlying data changed.

### App implementation: Projects (`backend/api/projects.py`, `backend/api/users.py`)

A "Projects" landing page (now `/`) lets someone create a named project
mapped to exactly one RFQ. This needed the app's **first-ever writes** to
Unity Catalog, via two new app-owned Delta tables
(`databricks/schema/bid_analyzer_projects.sql`,
`bid_analyzer_users.sql`) in the same `bid_data_exploration` schema as the
read-only Maximo tables.

**Blocked pending a new admin grant**: the app's service principal
currently has only `USE CATALOG`/`USE SCHEMA`/`SELECT` — no `CREATE
TABLE`/`INSERT`/`UPDATE`. Until that's granted, `POST
/api/users/identify` and `POST /api/projects` both 503 with the real
Databricks permission error (not a crash) — this is the expected,
directly-testable pre-grant state. The `CREATE TABLE IF NOT EXISTS`
DDL runs lazily on those write paths (not on every `GET`), so once the
grant lands, it self-heals with zero code changes and no restart.

**Untested against the real warehouse** (no local write credentials in
this session):
- Whether either table's `CREATE TABLE IF NOT EXISTS` DDL succeeds as
  written — this is the first DDL ever run from this codebase.
- Whether the manually-built `TIMESTAMP 'yyyy-MM-dd HH:mm:ss.ffffff'`
  literal used in both `INSERT`s is accepted by this warehouse via
  `databricks-sql-connector`.
- **Whether Databricks Apps forwards a signed-in user's identity via any
  request header** (`X-Forwarded-Email`/`X-Forwarded-Preferred-Username`/
  `X-Forwarded-User`, checked in that order by `backend/api/users.py`) —
  never confirmed anywhere in this codebase. If none of these fire, every
  user falls back to a self-reported display name cached in
  `localStorage`, which still works fully, just less seamlessly. Worth
  checking directly after deploy (a temporary log line on the first
  request would settle it).

Once the grant lands, the known-value spot check for this feature is:
create a project against `N-19535` (real, `detailed_boq`, 9 invited
vendors, description "400kV OHL Works for Haffar, ICAD4 & ICAD5 (SASN
Retirement)") and confirm `POST /api/projects` returns that description/
status/org/category/vendor_count enrichment correctly, then confirm `GET
/api/projects?user_id=...` and `GET /api/projects/{id}` both reflect it.

### App implementation: BOQ line-item comparison (`backend/api/comparison.py`)

**New fact from the user, resolving a long-open gap**: vendor names ARE
resolvable — `SELECT name FROM companies WHERE company = rfqvendor.vendor`.
This directly answers the `rfqvendor` section's "vendor names aren't in
this dataset at all" finding above. Assumed fully-qualified as
`ingestion_framework_test.bid_data_exploration.companies` (same schema as
everything else) — **UNVERIFIED**, first real use of this table in this
codebase. If `GET /api/rfqs/{rfqnum}/comparison` 503s with something
`TABLE_OR_VIEW_NOT_FOUND`-shaped, check this table's real location first.

**"Round 1" scope, deliberately minimal**: this comparison uses
`quotationline.UNITCOST`/`LINECOST` only — the original quote. As already
documented above, `quotationline` has no round-number or change-timestamp
column, only an original-vs-final snapshot (`LINECOST` vs
`LINECOSTWDIS`), so there is no queryable per-round history to compare
against. This is a deliberate, data-driven scope cut, not a placeholder.

**No lot rollup**: confirmed above that no lot column/structure exists
anywhere in the real schema, so this feature computes **contract totals
only** (`SUM(LINECOST)` per vendor across all their lines) — no lot-level
subtotal, since lots aren't modeled in Maximo's structured tables.

**Query approach** (three reads, no writes — independent of the Projects
write-grant status):
1. `rfqvendor` LEFT JOIN `companies` (`companies.company = rfqvendor.VENDOR`)
   → the invited-vendor roster + resolved names.
2. `quotationline` filtered to `RFQNUM` and `ORDERUNIT <> 'HEADER'` (or
   null) — excludes non-priced section-break rows, keeping only real BOQ
   line items.
3. Shaping (canonical line list, per-vendor pricing grid, flag
   computation) happens in Python, not SQL — consistent with this
   codebase's existing preference for verifiable logic over unverified
   warehouse-specific SQL (e.g. no `MEDIAN()` aggregate relied on).

**Flag definitions** (first-pass thresholds, tune later against real data —
this is the most likely thing to need iteration):
- **Unquoted**: a vendor has no `quotationline` row for a given
  `RFQLINENUM`, or has one with a null `UNITCOST`.
- **Arithmetic error**: `abs(LINECOST - ORDERQTY * UNITCOST) > 0.01`.
- **Outlier**: only computed when ≥3 vendors quoted a line (fewer isn't a
  meaningful sample) — `abs(UNITCOST - median_of_quotes) / median > 0.5`.
- **Did not submit** (distinct from "unquoted"): an invited vendor
  (present in `rfqvendor`) with zero `quotationline` rows for the whole
  RFQ at all — listed separately from the comparison table's vendor
  columns, not rendered as an all-empty column.

**Size safety**: real BOQs go up to 52k lines (documented above). Returned
`lines` are capped at 500 (`LINES_CAP` in `comparison.py`) with
`truncated`/`total_line_count` in the response — a flat `LIMIT`, not real
pagination. Vendor contract totals and flag counts are always computed
over the *full* line set, never just the returned/truncated page.

**Known-value spot check** once deployed: `GET
/api/rfqs/N-19535/comparison` should return 9 invited vendors in
`rfqvendor` (per the "Notebooks 07/08" section above), a subset of those
as columns (only ones with ≥1 `quotationline` row — recall 4 of 9 actually
submitted per that section), and 2,480 total lines (`total_line_count`,
truncated to the first 500 returned).

### Flagship demo example: N-19281 (high fill rate) — and a real duplicate-row finding

Went looking for a real RFQ where most/all vendors priced most/all lines
— a clean demo of the comparison feature with few unquoted cells. Query:
group `quotationline` (excluding `ORDERUNIT = 'HEADER'`) by `RFQNUM`,
compute `fill_rate = total_priced_rows / (total_lines * num_vendors)`;
1.0 means every submitting vendor priced every line.

**New finding, real and unexpected**: several RFQs (`A-1233`, `A1450`,
`A1474`, `N1658`, `G-01-0070.1`, `A1591`) came back with `fill_rate > 1.0`
— only possible if a vendor has **multiple `quotationline` rows for the
same `RFQLINENUM`**. This means the "zero duplicate `(RFQLINENUM,
VENDOR)` pairs" claim in the `RFQLINENUM` section above was only ever
confirmed on the one example tested (`N-19535`) — **not a general rule**.
`backend/api/comparison.py` doesn't handle this case: its `by_vendor =
{r.VENDOR: r for r in line_rows}` dict construction silently keeps
whichever duplicate row comes last and drops the rest, no warning. Do not
use any of the RFQs above for a demo until that's fixed — the table would
render looking clean while quietly showing incomplete data.

**Chosen example: `N-19281`** — 368 real BOQ lines, 9 submitting vendors,
exact `fill_rate = 1.0` (3,312 = 368 × 9, no duplicate-row anomaly).
Comfortably under `comparison.py`'s `LINES_CAP = 500`, so it renders
complete, no truncation. Runner-up: `N-14516.1` (293 lines, 10 vendors,
exact fill) if more bidder columns is preferred over more lines.

Every genuinely large detailed BOQ found with exact `fill_rate = 1.0`
(`N-19899`, `N-20585`, `N-18530`, etc. — thousands of lines each) is well
past the 500-line cap and would show truncated. The smallest *exact-fill*
RFQs found (9–11 real lines, e.g. `N-20221.1`, `M4817`, `D19890405`) are
real but too thin to read as a substantial procurement in a demo — they
just barely clear the `MIN_BOQ_LINE_ITEMS` threshold. `N-19281` sits in
the useful middle ground between those two extremes.

Note: the first fill-rate query used to find these candidates only
checked whether a `quotationline` row *existed* for a `(RFQLINENUM,
VENDOR)` pair, not whether `UNITCOST` was actually populated on it — so
it overstated fill rate wherever a row exists with a null price. Fixed by
also requiring `UNITCOST IS NOT NULL` before counting a line as quoted,
matching `comparison.py`'s real `unquoted` definition exactly.

### AED 0 is not "no data" — the zero-price flag

A `quotationline` row can have a non-null `UNITCOST`/`LINECOST` of
exactly `0`. For a real BOQ line this is almost always a data-entry
problem, not a legitimate free item — but it used to be treated as a
completely normal quote, meaning it could win `is_lowest` (a bad zero
beating a real bid) and skew the outlier median.

`backend/api/comparison.py` now flags this separately (`zero_price`,
distinct from `unquoted` — it has a value, just a bad one) and excludes
zero-priced cells from both the `is_lowest` candidate pool and the
outlier median's input list. A `zero_price_count` is tracked per vendor
alongside the existing three flag counts.

### Price corrections — `backend/api/corrections.py`, `bid_analyzer_price_corrections`

The app's first user-facing *editing* feature: any price cell in the
comparison (quoted, zero-priced, or unquoted) can be manually corrected
or filled in from the UI. Corrections are **never** written back into
`quotationline` — that table is Maximo-ingested, not ours to mutate.
Instead they're stored in a new app-owned overlay table
(`databricks/schema/bid_analyzer_price_corrections.sql`, same pattern as
`bid_analyzer_projects`/`bid_analyzer_users`) and applied at display time
by `comparison.py`. Append-only — correcting again just adds a new row;
the latest per `(rfqnum, rfqlinenum, vendor)` wins.

A corrected cell is trusted: `arithmetic_error`/`outlier`/`zero_price`
are all suppressed for it (a human already reviewed it), but it still
fully participates in `is_lowest` and `contract_total` — that's the
point of correcting bad data, not just annotating it.

Needs the same `CREATE TABLE`/`INSERT` grant as the Projects tables. The
comparison endpoint's corrections lookup is deliberately fail-open: if
the corrections table doesn't exist yet (nobody has corrected anything,
or the grant isn't applied), the read-only comparison view still returns
normally with zero corrections applied, rather than breaking a working
feature because of an unrelated write-path gap.

### Browse-list scope: only RFQs with a real BOQ (`MIN_BOQ_LINE_ITEMS = 10`)

Product decision: the RFQ Browse page only ever loads RFQs with
`avg_lines_per_vendor > 10` (strictly, so a value of exactly `10` is
excluded) — lump-sum/shallow/no-pricing-data RFQs have no real line-item
BOQ to compare, so they're dropped from the list entirely rather than left
as a togglable filter. This is a hard floor applied on every request in
`backend/api/rfqs.py`, not just the `boq_category` filter.

**This changes the known-value spot check above**: D-111808 is `lump_sum`
(one line per vendor), so it no longer appears in `/api/rfqs` at all under
this floor — `search=D-111808` should now return zero rows. That's
expected, not a bug. The floor is slightly stricter than the `detailed_boq`
category boundary (`> 10` vs. `> 9`), so the in-scope count should be a bit
below the 3,289 `detailed_boq` figure above — exact number not yet
confirmed against the live warehouse.

### App implementation: round-over-round tracking (`backend/api/rounds.py`)

**New tables from the user, resolving the "no round-by-round history"
gap documented above**: `DISCOUNTHISTORY` and `DISCOUNTHISTORYLINE` —
first use of either in this codebase, fully-qualified location assumed
to match the rest of the schema (`ingestion_framework_test.bid_data_exploration`),
**UNVERIFIED**. Given schema:

- `DISCOUNTHISTORYLINE`: `RFQNUM`, `VENDOR`, `REVISION` (decimal — the
  round number), `RFQLINENUM`, `LINECOSTWDIS` (decimal — the discounted
  line cost at that revision), `DISCOUNT_PERCENT`, `RECORDTYPE`,
  `DESCRIPTION`, `ORGID`/`SITEID`, `ROWSTAMP`.
- `DISCOUNTHISTORY`: `RFQNUM`, `VENDOR`, `REVISION`, `STAGE`,
  `ENTERDATE`, `DISCOUNT_SUBMISSION_DATE`, `DISCOUNT_APPLY_DATE`,
  `DESCRIPTION`, `ORGID`/`SITEID`, `ROWSTAMP` — header/event level, one
  row per `(RFQNUM, VENDOR, REVISION)`.

**The one real design risk, handled by construction rather than
assumption**: whether each `REVISION`'s `DISCOUNTHISTORYLINE` rows are a
full snapshot of every line the vendor has ever priced, or only the lines
that changed at that revision, is unknown (no live data seen). The
backend forward-fills: seed a running per-vendor per-line map from
`quotationline.LINECOST` (the `"original"` round), then overlay each
increasing `REVISION`'s rows onto it and snapshot the *full* resulting
map at that revision. This produces correct per-round contract totals
whether revisions are deltas or full snapshots — verified in the
scratchpad test suite with both fixture shapes producing identical
totals. `RECORDTYPE`/`STAGE` aren't used yet — meaning unclear, not
investigated.

**Flags** ported from `full-feature-buildout`'s `backend/analysis/rounds.py`
(the "local version" round-tracking dashboard this was modeled on),
adapted from hierarchical `item_no`/lot to `RFQLINENUM` (no lots, per
above): a **critical** flag for any round-over-round price *increase*
per line (negotiation rounds should never raise a price), and a
**warning** flag for a discount far steeper than the peer-median ratio
other vendors showed on the same line between the same two rounds
(`PEER_DEVIATION_THRESHOLD = 4.0`, needs ≥3 peer vendors to judge) —
same threshold values as the original build, carried over as a
first-pass baseline pending real data, same spirit as the comparison
feature's arithmetic/outlier thresholds.

**Known-value spot check** once deployed: `GET /api/rfqs/N-19535/rounds`
should return `rounds_present` starting with `"original"` followed by
whatever real `REVISION` values exist for this RFQ in
`DISCOUNTHISTORYLINE` (none confirmed yet — first thing to check), and
each vendor's `"original"` point should match their `contract_total` in
`GET /api/rfqs/N-19535/comparison` exactly (both derive from the same
`quotationline.LINECOST` sum).

### App implementation: negotiation-prep export (`backend/api/negotiation_report.py`)

Closes CLAUDE.md's manual-process step 6 ("prepare negotiation notes per
bidder") by consolidating the comparison and round-tracking flags already
computed elsewhere — no new analysis, no new tables, no new queries of
its own. Calls `build_comparison()`/`build_round_trend()` directly
in-process (both `comparison.py` and `rounds.py` were refactored to
expose their logic as plain callables, not just route handlers, for
exactly this reuse).

**Deliberately not LLM-generated** — `full-feature-buildout`'s equivalent
(`backend/reporting/llm_report.py`) used Azure OpenAI for an executive
summary, an award recommendation, and prose negotiation points. This
version presents ranked facts only (contract total ascending, % above
lowest, flag counts, a capped/deduped top-issues list per vendor,
mirroring that build's `digest.py` pattern minus the LLM call) — no
"primary award", no generated reasoning. A deliberate, discussed scope
cut, not a placeholder for "add the LLM later without telling anyone" —
if a narrative layer gets built, it should be visibly additive to this,
not a silent replacement.

**Known limitation, inherited, not new**: `_collect_boq_issues` scans
`comparison["lines"]`, which is itself capped at `comparison.py`'s
`LINES_CAP = 500` — on a BOQ larger than that, issues on lines past the
cap won't appear in anyone's `top_issues` (though the flag *counts* are
unaffected, those come from `comparison.py`'s vendor summary which is
always computed over the full line set).

**Export**: an `.xlsx` via `openpyxl` (already used elsewhere in this
project per `CLAUDE.md`'s tooling notes, but was only present in
`uv.lock` as a stale transitive entry, not actually declared in
`pyproject.toml`, until this feature — now a real, intentional
dependency). Two sheets: `Summary` (one row per vendor, ranked) and
`Issues` (every vendor's top issues, flattened) — no per-lot sheets like
the original build's export, since lots don't exist in real data.

**Known-value spot check** once deployed: `GET
/api/rfqs/N-19535/negotiation-report` should rank the same vendors
`GET /api/rfqs/N-19535/comparison` returns, by the same `contract_total`
values, and `has_round_data` should match whether `GET
/api/rfqs/N-19535/rounds` actually returns more than one `rounds_present`
entry.

### App implementation: AI negotiation narrative (`backend/api/negotiation_narrative.py`)

The LLM layer the previous section explicitly deferred ("if a narrative
layer gets built, it should be visibly additive to this, not a silent
replacement") — built after the user closed out an AI Impact Assessment
for this project and **explicitly chose Databricks Model Serving / AI
Gateway** over a direct external LLM API call, so vendor pricing data
never leaves TAQA's governed Databricks workspace. `POST
/api/rfqs/{rfqnum}/negotiation-report/narrative` layers an AI-written
executive summary + per-vendor observations on top of the deterministic
report above — additive, not a replacement: the ranked-facts view stays
primary, this is an optional, user-triggered extra (no auto-generation on
page load, no caching).

**SDK call shape — verified by introspecting the installed
`databricks-sdk` directly (`inspect.signature()`), not assumed from
documentation**:
```python
WorkspaceClient().serving_endpoints.query(
    name: str, *, messages: list[ChatMessage] = None,
    max_tokens: int = None, temperature: float = None,
) -> QueryEndpointResponse
# ChatMessage(content: str, role: ChatMessageRole.SYSTEM/USER/ASSISTANT)
# response.choices[0].message.content  -- the model's text
```
`WorkspaceClient()` takes no args — same auto-detected auth `db.py`'s
`Config()`-based connection already relies on, no new credential
plumbing.

**Config**: a new `DATABRICKS_LLM_ENDPOINT` env var (mirrors how `db.py`
reads `DATABRICKS_HTTP_PATH`), set in `app.yaml` alongside
`DATABRICKS_HTTP_PATH` for the deployed app.

**Endpoint confirmed real and working (2026-08-20)** — the user ran a
direct notebook test against this workspace
(`adb-3103344838598474.14.azuredatabricks.net`) using the OpenAI-compatible
client (`OpenAI(api_key=<notebook token>,
base_url=f"{host}/serving-endpoints")`, `model="databricks-claude-haiku-4-5"`)
and got a real completion back. `app.yaml` now sets
`DATABRICKS_LLM_ENDPOINT=databricks-claude-haiku-4-5` — a Databricks-hosted
pay-per-token foundation model endpoint (Claude Haiku 4.5 served through
Databricks' own governed proxy, not a customer-deployed model), so there's
no separate serving capacity to provision or manage. An alternative
endpoint on the same workspace is available if a larger open-weights
model is ever preferred: `databricks-gpt-oss-120b`
(`https://adb-3103344838598474.14.azuredatabricks.net/serving-endpoints/databricks-gpt-oss-120b/invocations`).

This closes the "does a usable endpoint exist" half of the original open
question. **Still unconfirmed**: whether the *app's own service
principal* (not the notebook's interactive user identity used in the
test above) has "Can Query" permission on this endpoint — foundation
model endpoints are workspace-shared, but per-principal query grants are
typically still enforced the same as for a custom-deployed endpoint. The
notebook test used the calling *user's* auto-injected token
(`dbutils...apiToken()`), which is a different identity than whatever the
deployed app authenticates as (`WorkspaceClient()`'s auto-detected
Databricks Apps credentials, per `backend/db.py`'s existing pattern) — so
this still needs a real deploy to confirm the service principal itself
isn't blocked. If it 502s with `api_error` after deploy, this grant is
the first thing to check.

**Guardrails actually implemented** (mapping directly to the AIA
governance conversation that prompted this feature):
- **Structured-JSON-only output**, never free text rendered directly —
  the system prompt requires exactly `{executive_summary, observations:
  [{vendor, note, talking_points}], caveats}`. A response that doesn't
  parse to this shape is a hard `parse_error` (502), never best-effort
  rendered.
- **No `primary_award`/recommendation field** — deliberately absent
  (unlike `full-feature-buildout`'s equivalent, which had one). Advisory
  observations only; the model never produces an award decision, and the
  UI's "ok" state carries a persistent "AI-generated — advisory only, not
  a decision" banner.
- **Deterministic safety net, applied after the model responds**
  (`_apply_safety_net`, mirrors `full-feature-buildout`'s
  `_enforce_data_gap_safety_net` pattern) — code the model's output can
  never override, not an instruction it might not follow. Strips any
  `observations` entry referencing a vendor that isn't actually one of
  this RFQ's real submitting vendors, and logs the correction as a
  `caveats` entry rather than silently dropping it. Verified with a
  scratchpad test injecting a hallucinated vendor code into a canned
  model response — confirmed stripped, confirmed logged.
- **Prompt-injection guardrail**: only system-computed data enters the
  prompt (vendor codes/resolved names, computed totals/ranks/flag
  counts, the digest's own synthesized issue strings). The one free-text
  user input anywhere in this app — the price-correction `note` field
  (`backend/api/corrections.py`) — is deliberately never included in any
  prompt.
- **No autonomous actions** — this endpoint only ever returns a report
  for a human to read; it never triggers a write, email, or decision on
  its own.
- **No caching, always a fresh call** — a deliberate "single high-value,
  user-triggered action," not an auto-refreshing or auto-loaded feature.
- **Rate-limiting/content-safety filtering is explicitly out of scope for
  application code** — that belongs at the Databricks AI Gateway
  admin-config level on whichever endpoint gets chosen, worth raising
  with whoever manages the workspace once `DATABRICKS_LLM_ENDPOINT` is
  set for real.

**Error taxonomy**, discriminated by HTTP status code alone (never by
string-matching the message — the exact bug class the misleading-503
fix earlier in this project's history was about avoiding a repeat of):
`not_configured` (missing env var) → 503; `api_error` (the Model Serving
call itself failed, most likely a missing "Can Query" grant) and
`parse_error` (response didn't match the expected JSON shape) → both 502.
The frontend only needs to tell "not configured" apart from "something
went wrong when it tried" — it doesn't need to visually distinguish
`api_error` from `parse_error` from each other.

**Verified in the scratchpad** (`TestClient` + a fake `WorkspaceClient`,
same pattern as every other backend feature in this project — no live
Databricks connection): missing `DATABRICKS_LLM_ENDPOINT` → clean 503
`not_configured`; well-formed response including a hallucinated vendor →
200 with that observation stripped and a caveat added; non-JSON model
content → 502 `parse_error`; the SDK `query()` call raising (simulating a
permissions error) → 502 `api_error` surfacing the real underlying
exception text, not a generic message. Frontend build/typecheck passed
clean; a mock-backend Playwright walkthrough confirmed both the idle
"Generate AI summary" state and the loaded state (executive summary,
per-vendor observation cards, caveats list, advisory banner) render
correctly.

**Known-value spot check** once deployed: `POST
/api/rfqs/N-19535/negotiation-report/narrative` should reference only
vendors that also appear in `GET /api/rfqs/N-19535/negotiation-report`'s
`vendors` list — if the response ever includes a `caveats` entry about a
stripped vendor, that's the safety net catching a real hallucination, not
a bug.

**Dev-environment note, unrelated to this feature but worth recording**:
while visually verifying this card, `next dev` (Turbopack) served pages
but never actually hydrated React when the app was accessed via
`http://127.0.0.1:3000` — the browser's WebSocket to `/_next/webpack-hmr`
was rejected by Next's `allowedDevOrigins` check (which allows
`localhost` but not the `127.0.0.1` literal by default), and something
about that failure silently prevented client-side hydration from
completing at all (no console error, no page error — just an inert page
stuck on every component's initial "Loading…" state). Using
`http://localhost:3000` instead of `127.0.0.1` fixed it immediately. Not
an app bug — just a trap worth avoiding in any future local verification
session against `next dev`.
