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

## Notebook 09 — client walkthrough: real numbers across the whole dataset

First run against the full 30,338-row `rfq` universe, not just hand-picked
examples. See `databricks/notebooks/09_client_walkthrough_boq_analysis.ipynb`.

### Headline: only 10.8% of RFQs have a genuinely detailed, line-by-line BOQ

Classified by real structure (average `quotationline` rows per vendor),
not the unreliable `DETAILBOQAVAILABLE` flag:

| Category | RFQ count | % of all RFQs | Total recorded award value |
|---|---|---|---|
| Lump-sum (1 line/vendor) | 10,903 | 35.9% | **AED 62,808M** |
| Shallow (2-9 lines/vendor) | 9,893 | 32.6% | AED 28,163M |
| No priced lines at all | 6,253 | 20.6% | AED 48M |
| Detailed BOQ (10+ lines/vendor) | 3,289 | 10.8% | AED 47,298M |

**Counter-intuitive and important**: lump-sum tenders carry the *most*
recorded value of any category — more than genuinely detailed BOQs. The
biggest deals in this dataset are frequently bid as a single number, not
itemized. Concrete example: **G-5809, "Strategic Water Storage / Recovery
Project in Liwa"** — 8 vendors, each bidding a single lump-sum line between
**AED 1.61B and AED 2.45B**, won by the lowest bid (AED 1,611,242,556 to
vendor `9918338`). A real, billion-AED mega-project with zero line-item
detail in Maximo's structured data.

(Caveat carried over from earlier: `total_award_value` only sums rows where
`TOTALAWVALUE` is populated at the header level — most rows have it `null`
— so treat this as directional, not exhaustive.)

### `DETAILBOQAVAILABLE` reconfirmed dead as a signal — now with the full cross-tab

|  | `N` | `Y` | `null` |
|---|---|---|---|
| Detailed BOQ (10+ lines/vendor) | 17 | **106** | 3,166 |
| Shallow (2-9 lines/vendor) | 31 | 134 | 9,728 |
| Lump-sum (1 line/vendor) | 74 | 111 | 10,718 |
| No priced lines at all | 19 | **61** | 6,173 |

Of the 3,289 RFQs that are *genuinely* detailed, only 106 (3.2%) are
flagged `Y`. Of the 6,253 RFQs with **zero** priced lines at all, 61 are
flagged `Y` anyway. The flag and real structure are essentially
uncorrelated — do not use it as a proxy for BOQ detail in any pipeline
logic.

### Round tracking — a new anomaly on top of the confirmed mechanism

Real example this run: `N-20585` (valve repair/replacement, 52,398 lines,
9 vendors). `DISCOUNT_REVISION` distribution reconfirmed identical to
earlier findings (1,305 → 662 → 294 → ... → 1 across rounds 1-12) —
consistent, no surprises there.

The line-level before/after chart surfaced something new, though: most
lines behave as expected (`LINECOSTWDIS` slightly below `LINECOST`, e.g. a
consistent ~1.54% discount across many of vendor `001145`'s early lines),
but a few lines for vendor `002012` show `LINECOSTWDIS` **higher** than
`LINECOST` (376,000 → 6,718,076), and vendor `003108`'s largest lines drop
straight to **0**. Neither looks like an ordinary discount. **Open
question for TAQA**: does `LINECOSTWDIS` ever legitimately increase or
zero out for reasons other than a price discount (re-quote, disqualification,
a data-entry correction), or is this a data-quality issue?

### Fixed a bug in the 4c WDIS-confirmation test — the real result is still pending

The first run of this test reported a **0% match rate (0/15)** between
`rfq.TOTALAWVALUE` and `rfqvendor.TOTALAWARDCOSTWDIS` — but that result is
an artifact of a flawed query, not evidence against the hypothesis. The
query compared the header value against **every invited vendor's** WDIS
figure (e.g. `N-19957` alone contributed 6 rows, one per invited vendor,
all compared against the same header total) rather than filtering to the
vendor actually marked `ISAWARDED = 1`. Only the winner should ever match —
comparing all bidders guarantees near-total mismatch by construction. This
is exactly the D-111808 test that *did* match earlier, because that
comparison was manually restricted to the awarded vendor (`001938`).

**Fixed** (`WHERE rv.ISAWARDED = 1` added) — needs a re-run to get the real
match rate across a broader sample than just D-111808.

### 4a (vendor names) and 4d (altquotationline) — reconfirmed, no new findings

- Live `information_schema.columns` search found the same non-answers as
  expected: `rfq.BUYERCOMPANY` and `rfq.REPNAME` are new candidates not
  checked before — worth a quick follow-up to see what values populate
  them (likely TAQA-side names, not bidder names, but cheap to confirm).
- `altquotationline` row count (42,668) vs. `quotationline` (1,660,753)
  reconfirmed exactly matching prior findings — no change.

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

## Open questions for TAQA (updated after notebook 09)

- **New**: does `LINECOSTWDIS` ever legitimately increase relative to
  `LINECOST`, or drop straight to `0`, for reasons other than a price
  discount? Seen on real lines in `N-20585` — looks like disqualification
  or a re-quote rather than a normal discount, but that's a guess.
- **New**: is `rfqvendor.TOTALAWARDCOSTWDIS` (filtered to the awarded
  vendor) really the confirmed final price at scale, not just on
  D-111808? The broader test is written (`09`, section 4c) but needs a
  re-run after fixing a query bug (see notebook 09 section above) — no
  real answer yet.
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
- **New**: `quotationline` shows real per-line discount data
  (`LINECOST`/`LINECOSTWDIS`/`DISCOUNT_PERCENT`) but no round-number or
  change-timestamp column — only original-vs-final state is visible, no
  round-by-round history. Confirm with TAQA whether that intermediate
  history exists anywhere in Maximo (even if not in these 7
  tables/views) — it matters for whether a rebuilt comparison tool can ever
  show true round-over-round movement per line, or only net effect.
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
