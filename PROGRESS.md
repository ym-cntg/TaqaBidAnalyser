# Progress Log

Living log of notable changes to this project — feature work, bug fixes, and
investigations worth remembering. Newest entries at the top. This is separate
from `TUTORIAL.md` (which explains how the system works end-to-end) — this
file tracks *what changed and why*, chronologically.

---

## 2026-07-06 — `original-bid-analysis` branch: unmatched-items highlight toggle

- **Feature — clickable "Unmatched" filter in the match-quality legend.**
  The "Unmatched (N)" legend entry in `frontend/src/app/page.tsx` is now a
  toggle button instead of a plain label. Clicking it highlights every
  `unmatched` row in red (row + sticky item-no cell), and auto-expands any
  collapsed parent group that contains at least one unmatched child so the
  highlighted rows are actually visible without manually expanding each
  category first. Toggling off reverts highlighting and collapse state
  cleanly. Verified interactively (click-on, scroll, click-off) via
  Playwright against the live backend — confirmed rows 1.3, 1.5, 1.16, 3.3
  highlight correctly and their parent groups (1, 3) auto-expand while
  unrelated groups (2) stay collapsed.

## 2026-07-06 — `original-bid-analysis` branch: ELMEC data-gap exclusion + collapsible hierarchy

Found while manually reviewing the Compare table: item "1" (a bare top-level
BOQ category) showed a value for ELMEC only, with garbled `unit`/`qty`
fields, while every other bidder showed "-".

- **Fix — exclude bidders with no genuine detail BOQ for the original round.**
  ELMEC's `original/` folder only contains `D-111808BOQ-SummaryofLot1,2&3.pdf`
  — a lot-*comparison* summary (one row per top-level category, columns laid
  out as Lot1-CIF/Erection/Total, Lot2-..., Lot3-... side by side), not a
  per-item detail BOQ. (Its `round1`/`round2` folders *do* have proper
  per-lot detail files — only the original submission is missing detail
  data in this sample set.) `router.py` was running this summary table
  through the detail-BOQ column parser (`[item, desc, unit, qty, cif_rate,
  cif_total, ...]`), which doesn't match the summary table's real column
  layout — hence the garbled `unit`/`qty` values. Added a check: if every
  available PDF for a round is summary-shaped (no detail-shaped alternative),
  treat the round as having no extractable data rather than misparsing it.
  Also updated `GET /api/sample/bidders` to only list bidders with data that
  actually extracts to something, instead of just checking file presence, so
  the frontend never offers a bidder that dead-ends. **Impact: ELMEC dropped
  from the original-round comparison entirely** (7 bidders now, down from 8);
  everyone else's numbers unaffected.

- **Feature — collapsible parent/child rows in the Compare table.**
  BOQ item numbers nest (`1` → `1.1` → `1.1.1` — category → sub-section →
  line item). Added `groupByTopLevel()` in `frontend/src/app/page.tsx` to
  group items by their top-level segment; top-level categories now render as
  a single collapsed row with a per-bidder rolled-up total (sum of all its
  numbered children — the bare category row itself is a label, not a
  separately-priced line in any bidder's real BOQ), with a chevron to expand
  and reveal the detail rows. Search auto-expands and filters to matching
  groups. Verified interactively (click-to-expand, search-to-filter) via a
  Playwright script against the live backend, not just code review.

## 2026-07-06 — `original-bid-analysis` branch: extraction-correctness fixes

Found while manually spot-checking the Compare table against known-good
figures from `CLAUDE.md`'s business-context table.

- **Fix — subtotal/recap rows leaking in as fake line items.**
  `pdf_parser.py` and `ocr_parser.py` only checked the *description* field for
  total/subtotal keywords, never the *item_no* field — but rows like
  `"Item-1 Sub Total - Installation of New 33/11kV Primary station..."` carry
  that text in `item_no`, not `description`. The Excel parser already guarded
  against this; the PDF/OCR paths didn't. These leaked rows were being summed
  *in addition to* the real line items they recapped, inflating contract
  totals by up to ~3x for any bidder extracted via PDF/OCR.
  **Impact: AGPOWER's original-round total corrected from AED 579.5M → AED
  195.5M** (now matches `CLAUDE.md`'s hand-verified ~64.2M/lot).

- **Fix — multi-lot boundary misattribution for combined PDFs.**
  Bidders whose only PDF is a single document covering all 3 lots (AL Geemi,
  Spaceage) relied on an item-number-reset heuristic
  (`_detect_lot_boundaries`) to split it into lots. That heuristic silently
  misfires when OCR doesn't cleanly reproduce bare top-level item numbers
  ("1", "2", "3"...), bleeding items across lots. Fixed by making
  `router.py` prefer the bidder's known-reliable per-lot Excel files whenever
  no PDF filename identifies a specific lot (rather than trusting the guessed
  split). **Impact: AL Geemi's original-round total corrected from AED 460.9M
  (wildly uneven lots: 123.8M/254.6M/82.4M) → AED 179.4M (evenly split
  ~58-61M/lot)** — matches `CLAUDE.md` almost exactly.

- **Fix — missing contract-total fallback in the Excel parser.**
  Bidders with no separate summary-of-all-lots file (just 3 per-lot files —
  e.g. Spaceage) got `total_contract_price: None`, even though every lot's
  own total was already correct. `excel_parser.py::parse_bidder_folder()` now
  falls back to summing lot totals when no summary file exists, mirroring
  logic the PDF-router path already had. **Impact: Spaceage: None → AED
  208.5M.**

- **Result**: all 8 sample bidders now show plausible, tightly-clustered
  original-round totals (AED 112.6M–273.6M), zero leaked subtotal rows, no
  missing totals. Verified via live `/api/sample/compare` output, not just
  code review.

## 2026-07-06 — `original-bid-analysis` branch: skeleton scope reduction

Branched off `main` to focus on getting original-round bid values correct
before re-adding negotiation-round tracking. Per explicit scoping decisions:

- **Backend**: discovery/extraction (`router.py`, `excel_parser.py`) now only
  ever scans each bidder's `original/` folder — round1/round2/round3 are
  never touched. API simplified: dropped `GET /api/sample/rounds` and the
  entire `/api/upload` ad-hoc upload feature (in-memory store included);
  `GET /api/sample/compare` no longer takes a round param (always original);
  `GET /api/sample/extract/{bidder}` now returns one extraction object
  instead of a list.
- **Frontend**: trimmed from 5 pages to 2 — Bid Comparison (merged into `/`,
  former `/compare` page minus its now-pointless round selector) and BOQ
  Explorer (`/explorer`, same). Deleted Dashboard, Upload & Extract, and
  Flags & Insights pages, plus the now-unused `price-chart.tsx`. Sidebar nav
  trimmed to match.
- **Kept intact** (explicit decision): all 4 flag categories (unquoted,
  arithmetic, outlier, unbalanced) and the 4-tier item matcher — these still
  compute server-side even though there's no dedicated Flags page right now.
- Verified: `npm run build` clean (2 routes, 0 type errors), backend 404s on
  all removed routes, 200s with correct data on the new ones.

## 2026-07-06 — `main` branch: frontend restyle + tutorial rewrite

- **Feature — cohesive teal brand theme** (commit `30c47e5`). Replaced the
  flat grayscale shadcn default with an actual color system across
  `globals.css` (new OKLCH palette, gradient background wash), `Card`
  component (soft shadow instead of flat ring border), sidebar (gradient
  logo, active-nav accent bar), and per-page table/tab polish (Compare,
  Explorer, Flags, Upload). Purely visual — no behavior changes, verified
  page-by-page via Playwright screenshots against the real backend.
- **Docs — `TUTORIAL.md` rewritten end-to-end** (commit `88f2d85`). Grounded
  in the actual discovery-call transcript
  (`project_details/power_transcript.md`) and business-case slide
  (`project_details/bid_use_case.png`) rather than a generic summary — traces
  every backend/frontend step back to the specific manual pain point it
  automates. Also corrected stale facts (8 sample bidders now, not the 2
  `CLAUDE.md` documents; backend has no round-tracking equivalent to
  `src/analysis/round_tracker.py`).

## Earlier history

Predates this log — see `git log` for the full history. Notable prior
milestones: initial POC (`1d544fb`), `src/` CLI batch pipeline added
(`1d6e98d`), Docker setup (`bd10607`, `e520ad6`), 4-tier item matching +
Azure OCR caching added to `backend/` (`eb11bea`), PDF parsing refinements
(`3e995b6`).
