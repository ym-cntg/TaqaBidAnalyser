# Bug & Data-Quality Tracker

Structured record of every extraction-correctness issue found on this
project, separate from `PROGRESS.md` (which is the chronological narrative
log of all changes — features, fixes, docs). This file exists to answer
"what's broken, what's fixed, what's just real messy data" at a glance.

Two kinds of entries:
- **BUG-xxx**: something our code got wrong. Fixable, and fixed.
- **DATA-xxx**: something the *source data itself* is wrong/unusual about
  (bidder typo, OCR misread of a scanned document). Not code-fixable —
  the right response is detection/flagging, not a silent patch.

---

## Summary

| ID | Title | Severity | Status |
|---|---|---|---|
| [BUG-001](#bug-001) | Subtotal/recap rows parsed as fake line items (PDF/OCR paths) | Critical | Fixed |
| [BUG-002](#bug-002) | Multi-lot boundary misattribution for combined PDFs | Critical | Fixed |
| [BUG-003](#bug-003) | Missing contract-total fallback when no summary file exists | High | Fixed |
| [BUG-004](#bug-004) | Lot-summary document misparsed as detail BOQ (ELMEC) | High | Fixed (excluded) |
| [BUG-005](#bug-005) | Inflated effective column count from stray formula artifacts | Medium | Fixed |
| [DATA-001](#data-001) | OCR digit misread, 100x inflation (DANWAY) | Critical | Flagged — correctable via reviewer edit |
| [DATA-002](#data-002) | Bidder's own cross-lot pricing inconsistency (Site) | Medium | Flagged — correctable via reviewer edit |

---

## BUG-001

**Title**: Subtotal/recap rows parsed as fake line items
**Severity**: Critical — inflated contract totals up to ~3x
**Component**: `backend/extraction/pdf_parser.py`, `backend/extraction/ocr_parser.py`
**Found**: 2026-07-06, spot-checking Compare table against `CLAUDE.md` figures
**Status**: Fixed, commit `4b249c5`

**Root cause**: Row-skip logic only checked the `description` field for
total/subtotal keywords, never the `item_no` field — but recap rows like
`"Item-1 Sub Total - Installation of New 33/11kV Primary station"` carry
that text in `item_no`. The Excel parser already guarded against this
pattern; the PDF/OCR paths didn't, so these rows got summed *in addition to*
the real line items they recapped.

**Fix**: Added the same item_no-based total/subtotal/recap detection
(`"sub total"`, `"grand total"`, `"total"`, and the `"item N"` recap
pattern) to both PDF/OCR row parsers.

**Impact measured**: AGPOWER original-round total: AED 579.5M → AED 195.5M.

---

## BUG-002

**Title**: Multi-lot boundary misattribution for combined PDFs
**Severity**: Critical — items bled across lots, wildly uneven lot totals
**Component**: `backend/extraction/router.py`
**Found**: 2026-07-06
**Status**: Fixed, commit `4b249c5`

**Root cause**: Bidders whose only PDF is a single document covering all 3
lots (AL Geemi, Spaceage) relied on `_detect_lot_boundaries()` — an
item-number-reset heuristic — to split it. That heuristic silently misfires
when OCR doesn't cleanly reproduce bare top-level item numbers ("1", "2",
"3"...), causing items to bleed across lot boundaries.

**Fix**: `router.py` now prefers a bidder's known-reliable per-lot Excel
files whenever no PDF filename identifies a specific lot (rather than
trusting the guessed split from a combined document).

**Impact measured**: AL Geemi: AED 460.9M (uneven lots 123.8M/254.6M/82.4M)
→ AED 179.4M (evenly split ~58-61M/lot), matching `CLAUDE.md` almost exactly.

---

## BUG-003

**Title**: Missing contract-total fallback when no summary file exists
**Severity**: High — `total_contract_price: None` despite correct lot data
**Component**: `backend/extraction/excel_parser.py`
**Found**: 2026-07-06
**Status**: Fixed, commit `4b249c5`

**Root cause**: `parse_bidder_folder()` only ever set `total_contract_price`
by parsing a dedicated summary-of-all-lots file. Bidders with no separate
summary file (just 3 per-lot files — e.g. Spaceage) got `None`, even though
every lot's own total was already extracted correctly.

**Fix**: Falls back to summing lot totals when no summary file's total is
available, mirroring logic the PDF-router path already had.

**Impact measured**: Spaceage: `None` → AED 208.5M.

---

## BUG-004

**Title**: Lot-summary document misparsed as detail BOQ (ELMEC)
**Severity**: High — garbled unit/qty values, one bidder's data unusable
**Component**: `backend/extraction/router.py`, `backend/api/routes.py`
**Found**: 2026-07-06
**Status**: Fixed (bidder excluded from comparison), commit `4b249c5`

**Root cause**: ELMEC's `original/` folder only contains
`D-111808BOQ-SummaryofLot1,2&3.pdf` — a lot-*comparison* summary (one row
per top-level category, columns laid out as Lot1-CIF/Erection/Total,
Lot2-..., Lot3-... side by side), not a per-item detail BOQ. The detail-BOQ
column parser assumed the wrong layout, reading lot-comparison columns as
unit/qty/rate.

**Fix**: Detect when every available PDF for a round is summary-shaped (no
detail-shaped alternative) and treat it as no extractable data, rather than
misparsing it. `GET /api/sample/bidders` now only lists bidders whose data
actually extracts to something.

**Impact**: ELMEC dropped from the original-round comparison (7 bidders now,
down from 8); everyone else unaffected. Note: ELMEC's `round1`/`round2`
folders *do* have proper detail files — only the original submission lacks
one in this sample set.

---

## BUG-005

**Title**: Inflated effective column count from stray formula artifacts
**Severity**: Medium — per-item `total` field silently blanked (lot/contract
totals unaffected, since those sum `cif_total`/`erection_total` directly)
**Component**: `backend/extraction/excel_parser.py`
**Found**: 2026-07-07, Week 1 spot-check (see `SPRINT_PLAN.md`)
**Status**: Fixed

**Root cause**: `parse_lot_file()` used `ws.max_column` to decide a sheet's
column layout (6-column spare-parts vs. 9-column full layout). openpyxl's
`max_column` can be inflated by content that has nothing to do with the
real header — Ray's Lot 2 "Items 9" sheet reported `max_column=10` (vs. 6 on
the otherwise-identical Lot 1/Lot 3 sheets) because subtotal rows further
down the sheet had leftover `#REF!` corrupted-formula values sitting in
columns 8-10. That pushed every real item through the wrong column-count
branch, reading blank cells as `total` instead of falling back to
`total = cif_total`.

**Fix**: Added `_effective_col_count()`, which derives column count from the
sheet's own header block (the "Item" row plus the two rows below it,
capturing the 3-row header structure used across these BOQ templates)
instead of trusting `max_column`.

**Impact measured**: Ray's spare-parts items (9.1.1-9.1.4) `total` field:
`None` → correct CIF value, matching Lot 1/Lot 3. Re-verified zero
regressions on Site, Spaceage, AGPOWER, AL Geemi, POWER LINES.

---

## DATA-001

**Title**: OCR digit misread, 100x inflation
**Severity**: Critical (data quality, not code)
**Bidder**: DANWAY, Lot 3, item `3.16` "Substation Lighting and Small Power"
**Found**: 2026-07-07, Week 1 spot-check
**Status**: Not code-fixable — now auto-detected (see cross-lot flag below)

**Detail**: DANWAY's only source file is a 95-page scanned PDF with no
digital text layer, forcing the full Azure OCR path (no Excel to fall back
to). Extracted CIF total for this item: **49,950,000**. Actual value on the
source page (visually confirmed, page 80 / "Page 16 of 17" of the Lot 3
section): **499,500**. Exactly 100x. This is Azure misreading a digit on a
scanned cell — nothing in our parsing logic to fix, since it's not our code
that read the number.

**Mitigation implemented**: the cross-lot consistency check (see
"Cross-lot consistency flag" below) catches this automatically going
forward — this specific value now surfaces as a `critical` flag rather than
silently feeding into the contract total. A reviewer can now also fix it
directly via the manual correction tool (see "Manual correction fail-safe"
below) — verified end-to-end: correcting item `3.16`'s CIF total to 499,500
drops Lot 3's `total_cif` from 86.2M to 36.8M (matching Lots 1/2) and makes
the cross-lot flag for this item disappear on the next comparison.

---

## DATA-002

**Title**: Bidder's own cross-lot pricing inconsistency
**Severity**: Medium (data quality, not code)
**Bidder**: Site, Lot 2, item `1.14.3` "Supply, installation, testing and
commissioning of Tele-control Communication Interface..."
**Found**: 2026-07-07, verifying the cross-lot consistency flag
**Status**: Not code-fixable — confirmed present in Site's raw source file

**Detail**: Site's own Lot 2 Excel file shows CIF total **202,808** for this
item, vs. **1,421** (Lot 1) and **1,414** (Lot 3) — confirmed directly in the
raw `.xlsx` cells, not an extraction artifact. Either a genuine data-entry
error in Site's own bid submission, or an unexplained ~140x cost difference
for identical scope across lots. Exactly the kind of thing worth a
negotiation clarification question, per the manual process described in
`project_details/power_transcript.md`.

---

## Cross-lot consistency flag (mitigation for DATA-001, DATA-002)

**Added**: 2026-07-07, `backend/analysis/comparator.py::_detect_cross_lot_flags()`

Flags items where a bidder's own price swings across their own lots far
more than peer bidders' prices swing for that same item. Naive
"bidder's-own-cross-lot-ratio" detection produces heavy false positives —
tried first, threw 19 flags on the sample data, 18 of which were legitimate
lot-to-lot quantity variation (e.g. cable/excavation work scales with each
substation's physical layout, so every bidder's price for those items
swings ~5x by lot). Refined to compare each bidder's cross-lot ratio against
the *peer-median* ratio for the same item — a bidder swinging in line with
everyone else isn't flagged; a bidder swinging dramatically more than peers
is. Final result on the sample data: exactly 2 flags, both confirmed real
(DATA-001, DATA-002 above).

---

## Manual correction fail-safe (fix for DATA-001, DATA-002)

**Added**: 2026-07-07, `backend/analysis/corrections.py`

Detection (the cross-lot flag above) only surfaces a suspect value — it
doesn't fix it. This closes the loop: a reviewer looking at the Explorer
table can override any field on any item directly, and the correction
feeds every downstream calculation (lot/contract totals, the Compare
table, flag detection) without re-running extraction.

- Corrections are layered on top of the raw parsed data on every read,
  never mutate it — reverting a correction always recovers the true
  original OCR/parsed value, even after multiple edits.
- Lot/contract totals are adjusted by the *delta* of the correction
  (`new - old`), not re-summed from scratch, so the fix doesn't silently
  change how totals are computed for the rest of a bidder's data.
- Verified against the real DATA-001 bug: correcting DANWAY item `3.16`'s
  CIF total (49,950,000 → 499,500) drops Lot 3's `total_cif` from 86.2M to
  36.8M — in line with Lots 1/2 — and removes the cross-lot flag for that
  item on the next `/api/sample/compare` call. Reverting restores 86.2M
  exactly, confirming no data is lost.
- Frontend: Explorer table rows get an edit (pencil) / revert (undo) icon
  and an amber "Corrected" badge; the Compare table marks corrected cells
  with a small amber `*` so the correction is visible from either page.
- **Known scope limit**: in-memory only, lost on server restart — same
  limitation as the rest of this POC's sample-data model. Should be
  persisted together with `/api/upload` results (see `SPRINT_PLAN.md`
  Week 3) if this moves beyond a demo.
