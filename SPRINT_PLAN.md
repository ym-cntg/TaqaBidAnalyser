# Sprint Plan — TAQA Bid Analyzer, Delivery by July 31

**Start**: Monday, July 6, 2026
**Target delivery**: Thursday, July 31, 2026 (4 working weeks)
**Plan owner**: engineering (this repo) — business owners per `CLAUDE.md`
(Salem Abdulrahim, Asim Hassan, Yaser Al Derei, Mariam Mohammed); SME
Mohammed Al Katheri for UAT.

This plan follows the same phased pattern we used on day one: **get one
thing verifiably correct on a narrow branch before widening scope**, rather
than building every feature at once against data we haven't validated. Day
one (see `PROGRESS.md`, 2026-07-06 entries) proved why: three real
extraction-correctness bugs surfaced the moment we spot-checked numbers
against `CLAUDE.md`'s hand-verified figures, on just 3 of 7 bidders. Assume
more exist until proven otherwise.

---

## Definition of done (July 31)

A procurement analyst can point the tool at a tender's bidder folder and
get, for **every negotiation round** (not just original):
1. Correctly extracted per-item and per-lot totals, matched across bidders.
2. Automated flags for unquoted items, arithmetic errors, outliers, and
   unbalanced bidding.
3. A round-over-round view showing how each bidder's pricing moved.
4. A downloadable comparison report (the artifact Mohammed's manual process
   currently produces by hand).

And the team has enough confidence in extraction accuracy to say so in
writing — meaning a defined regression check exists, not just spot-checks.

---

## Phase 0 — Complete (Monday, July 6)

Branch: `original-bid-analysis`. Scope: original round only, correctness
first, minimal UI. Already shipped today:

- [x] Restricted discovery/extraction/API to `original` round only
- [x] Trimmed frontend to 2 pages (Bid Comparison, BOQ Explorer)
- [x] Fixed subtotal-row leak inflating totals ~3x (PDF/OCR paths)
- [x] Fixed multi-lot boundary misattribution for combined-PDF bidders
- [x] Fixed missing contract-total fallback for bidders with no summary file
- [x] Excluded ELMEC from original-round comparison (no real detail BOQ
      source exists for it in this sample — data gap, not a code bug)
- [x] Collapsible parent/child rows for nested BOQ item numbers
- [x] Unmatched-item highlight toggle

**Exit criteria (met)**: all 7 remaining bidders show plausible,
tightly-clustered original-round totals; zero leaked subtotal rows; build
clean. See `PROGRESS.md` for full detail and verification steps.

---

## Week 1 (Jul 6–10) — Finish original-round correctness, merge to main

Goal: original-round data is *trustworthy enough to build on*. Don't widen
scope until this is true.

- [x] Spot-check remaining bidders (DANWAY, POWER LINES, Ray, Site, Spaceage)
      line-by-line against source PDFs/Excel, not just contract totals —
      found and fixed one more real bug (BUG-005: inflated effective column
      count) and confirmed two genuine data-quality issues that aren't code
      bugs (DATA-001: OCR digit misread; DATA-002: bidder's own cross-lot
      pricing inconsistency). See `BUG_TRACKER.md`.
- [x] Cross-lot consistency flag (emerged from the spot-check above, not
      originally planned) — catches DATA-001/DATA-002 automatically going
      forward. See `PROGRESS.md`, 2026-07-07.
- [x] Manual correction fail-safe (also emerged from the spot-check —
      detection alone doesn't fix a bad number, a reviewer needs to) — any
      BOQ item field can be overridden in the Explorer table, and the
      correction flows into totals, flags, and Compare automatically.
      Verified against the real DANWAY OCR bug. In-memory only for now;
      needs persistence before this is more than a demo (see Week 3). See
      `PROGRESS.md` and `BUG_TRACKER.md`, 2026-07-07.
- [x] Decide & implement a policy for bidders with data gaps like ELMEC's —
      went with **manual add with recommendations** rather than silent
      exclusion or flag-only: the bidder is listed with `data_gap` set, its
      item structure is cloned from a reference bidder as an unpriced
      skeleton, and a reviewer fills it in through the same edit UI as an
      OCR correction, sped up by peer-median suggestions. Also fixed a
      real trust bug this surfaced: a partially-filled data-gap bidder was
      winning "Lowest" on an incomplete total — now excluded from that
      ranking until real. See `PROGRESS.md` and `BUG_TRACKER.md`,
      2026-07-07.
- [x] Add a lightweight regression check (`backend/regression_check.py`,
      `uv run python -m backend.regression_check`) that fails (exit 1) if:
      a lot's CIF+Erection split is wildly asymmetric vs. peers with no
      flag already explaining it, any item's description/item_no looks
      like a subtotal/recap row, or a bidder's contract total is `None`
      without a documented `data_gap`. Verified it actually catches
      regressions (not just passing trivially) by injecting each failure
      mode into synthetic data — all three triggered correctly. Currently
      passes clean against the full sample dataset (7 bidders, 21 lots).
- [ ] Decide long-term fate of `src/` (the frozen CLI pipeline) — merge its
      useful parts (report generation, round tracking) into `backend/`, or
      formally deprecate it, rather than letting two implementations drift
- [ ] Merge `original-bid-analysis` → `main` once the above is done

**Friday checkpoint**: demo original-round comparison for all 7 bidders,
walk through the regression check, get a go/no-go on merging to `main`.

---

## Week 2 (Jul 13–17) — Negotiation rounds return, server-side

Goal: re-introduce round1/round2/round3 — this time on top of *validated*
extraction logic, and with round-comparison as a real backend feature, not
just a client-side chart.

- [ ] Restore round-aware discovery/extraction (reverse of Phase 0's
      restriction), re-applying all three Week-0 correctness fixes to every
      round, not just original
- [ ] Port `src/analysis/round_tracker.py`'s round-movement logic into
      `backend/` — per-bidder, per-lot % change from first to last round
- [ ] Add a new flag category: suspicious round-over-round jumps (e.g. a
      line item that moves >2x between rounds with no explanation) — this
      is the literal "negotiation rounds" step from Mohammed's transcript,
      currently unautomated in either pipeline
- [ ] Rebuild the Dashboard page (dropped in Phase 0) with the corrected,
      server-computed round data — KPI cards, round-over-round chart
- [ ] Rebuild the Flags & Insights page (dropped in Phase 0), wired to the
      corrected comparison data

**Friday checkpoint**: demo round1→round2→round3 price movement for at
least 2 bidders, with flags on any anomalous jumps.

---

## Week 3 (Jul 20–24) — Feature completeness

Goal: close the gaps between "the pipeline works" and "this replaces
Mohammed's manual process."

- [ ] **Report export** — port `src/reporting/` (Excel + HTML generation)
      into `backend/` as a `GET /api/report/{round}` (or similar) endpoint;
      add a "Download Report" button to the frontend. This is the single
      biggest missing piece — the live app currently has no output artifact
      at all, only an on-screen view
- [ ] **Cache extraction failures** — right now, files that fail extraction
      retry a real (slow, costly) Azure OCR call on every request; cache
      the failure too, with a manual bust mechanism
- [ ] **Persist `/api/upload` results and item corrections** — both are
      currently in-memory only, lost on restart; decide whether upload is a
      real workflow feature (re-add the page) or descope it for this
      delivery, and give corrections a real store (even a JSON file per
      tender would beat losing a reviewer's fixes on every restart)
- [ ] **Description-change detection** — Mohammed explicitly checks that
      bidders didn't alter BOQ wording (`power_transcript.md`); nothing in
      either pipeline currently diffs descriptions across bidders/rounds.
      New flag category: description similarity below a threshold vs. the
      reference bidder's wording for the same item number
- [ ] Stretch (time-permitting): initial look at water/other tender types
      per `CLAUDE.md`'s original next-steps — likely descoped to "confirmed
      out of scope for this delivery" if Week 1–2 ran long

**Friday checkpoint**: demo a full downloaded report for a real tender
round; demo description-change flag catching a deliberately-edited item.

---

## Week 4 (Jul 27–31) — Hardening, UAT, deployment

Goal: ship it.

- [ ] Full regression pass: every bidder × every round × every lot,
      re-verified against the Week 1 regression check
- [ ] **UAT with Mohammed Al Katheri**: have him run the tool against
      D-111808 and compare its output line-by-line against his own manual
      consolidated sheet (the one referenced in the transcript — worth
      getting a copy if we still don't have it). This is the real
      acceptance test, not our own spot-checks
- [ ] Time the tool-assisted process vs. his stated manual baseline (~7
      hrs/bid) — this is the number the business case is built on
- [ ] Deploy to Azure App Service (steps already documented in `README.md`)
- [ ] Final docs pass: `CLAUDE.md` sample-data section and Next Steps
      checklist are already known-stale (says 2 bidders, there are 7-8;
      lists things now built) — bring it in line with reality
- [ ] Stakeholder demo + sign-off

**Friday checkpoint**: go/no-go for production use, signed off by the
business-case owners.

---

## AI / intelligence feature roadmap

What "AI-driven" actually means in this codebase today vs. what's designed
but not built, so this doesn't stay implicit across `backend/analysis/`.

| Feature | Intelligence type | Status | Phase |
|---|---|---|---|
| 4-tier item matching (exact → normalized → fuzzy → LLM) | Rules (tiers 1–3) + real LLM call, opt-in (tier 4) | Shipped — `backend/analysis/item_matcher.py` | — |
| Flag detection: unquoted, arithmetic, outlier, unbalanced, cross-lot, missing | Rule/threshold-based (medians, ratios — no ML) | Shipped — `backend/analysis/comparator.py` | — |
| Peer-median recommendations for data-gap manual entry | Rule-based (median) | Shipped — `backend/analysis/corrections.py` | Week 1 |
| Round-over-round anomaly flags (jump >2x with no explanation) | Rule-based | Planned | Week 2 |
| Description-change detection across bidders/rounds | Rule-based (text similarity) | Planned | Week 3 |
| **LLM recommendation report** — executive summary, award recommendation, per-bidder negotiation notes | Genuine LLM (Claude, on-demand button) | Designed this session, not yet built | New — propose Week 3, alongside report export |
| Vendor financial-standing / capacity risk narrative (per Business Case "final evaluation" step) | Would be LLM, but needs financial/capacity documents we don't currently ingest | Not started — blocked on data source, not effort | Backlog, no ETA |

**LLM recommendation report — design summary** (full plan in session notes,
not yet a tracked file): one on-demand endpoint builds a compact *digest*
from the existing `ComparisonResult` (ranked totals, flag counts, top
flags per bidder — never the raw per-item tables) and sends it to Claude
for a structured JSON response (`executive_summary`, `recommendation`,
`bidder_notes`, `caveats`). Hard rule carried over from the Compare-page
fix earlier this week: **data-gap bidders (`extraction.data_gap` set) can
never be shortlisted or recommended for award**, enforced both in the
prompt and defensively after parsing the LLM's response. Delivered both
in-app (`/report`, new page) and as downloadable Excel/HTML, cached
in-memory per round with an explicit "regenerate" action so re-viewing the
page never silently re-triggers a paid LLM call. Reuses the same
`ANTHROPIC_API_KEY`/graceful-degradation pattern already proven in
`item_matcher.py`.

**Standing rule for any future LLM feature** (added 2026-07-07 after
finding an injected instruction in `frontend/node_modules/next/dist/docs/`
— see `PROGRESS.md`): only feed models structured, code-built digests of
our own data, never raw third-party file content or anything an external
party could have authored, and never let repo/dependency content be
treated as instructions.

---

## Feature backlog (prioritized)

| Priority | Feature | Phase |
|---|---|---|
| Must | Original-round extraction correctness | Week 1 |
| Must | Regression check for extraction correctness | Week 1 |
| Must | Negotiation-round tracking (server-side) | Week 2 |
| Must | Round-over-round anomaly flags | Week 2 |
| Must | Report export (Excel/HTML download) | Week 3 |
| Should | LLM recommendation report (award recommendation + negotiation notes) | Week 3 |
| Must | UAT against Mohammed's manual sheet | Week 4 |
| Must | Manual correction fail-safe for OCR/extraction errors | Week 1 |
| Must | Data-gap policy (manual add + peer recommendations) | Week 1 |
| Should | Dashboard page rebuild | Week 2 |
| Should | Flags & Insights page rebuild | Week 2 |
| Should | Cache extraction failures | Week 3 |
| Should | Description-change detection | Week 3 |
| Could | Persist upload results / item corrections / re-add Upload page | Week 3 |
| Could | Azure deployment | Week 4 |
| Won't (this cycle) | Water/other tender-type support | — |
| Won't (this cycle) | Multi-tender support (currently hardcoded to D-111808) | — |

---

## Evaluation metrics

### Data-quality / engineering metrics

| Metric | Target | How measured |
|---|---|---|
| Contract-total accuracy vs. manually-verified figures | Within 2% for every bidder that has one | Compare against `CLAUDE.md`/business-context figures and Mohammed's manual sheet |
| Leaked subtotal/recap rows in comparison output | Zero | Regression check (Week 1) scanning for total/subtotal keywords in `item_no` |
| Item match rate (exact + normalized) | ≥ 90% per lot | `match_summary` counts already returned by `/api/sample/compare` |
| Bidders with `total_contract_price: None` | Zero (excluding genuinely-excluded data gaps like ELMEC) | Direct API check across all bidders |
| Known open data-integrity bugs | Zero | Tracked in `PROGRESS.md` |
| `/api/sample/compare` latency (cache warm) | < 5s | Manual timing; currently minutes on cold cache due to Azure OCR fallback (Week 3 fix) |

### Business-value metrics (ties back to the original business case)

| Metric | Target (per business case) | How measured |
|---|---|---|
| Bid-analysis time reduction | 40–80% vs. ~7 hrs/bid manual baseline | Week 4 UAT: time Mohammed's manual process vs. tool-assisted, same tender |
| Accuracy vs. manual consolidated sheet | Line-for-line match (0% variance) | Week 4 UAT direct comparison |
| Negotiation-round coverage | 100% of rounds present in sample data (currently up to round3) | Feature check, Week 2 |
| Stakeholder sign-off | Yes/No from business-case owners | Week 4 demo |

---

## Risks & assumptions

- **Data quality risk is the dominant risk.** Three non-trivial bugs
  surfaced from checking just 3 of 7 bidders' *totals* — checking every
  bidder's *line items* in Week 1 may surface more. If it does, Week 2's
  start may slip; better to know in Week 1 than discover it in Week 4 UAT.
- **Sample data is single-tender (D-111808), power-only.** This plan
  delivers a validated pipeline for this tender's shape; generalizing to
  other tenders/water bids is explicitly out of scope for July (see
  backlog).
- **No automated test suite exists today.** The Week 1 "regression check"
  is a new addition, not a hardening of something already in place — budget
  real time for it, not a rubber stamp.
- **UAT depends on Mohammed's availability** and on actually obtaining his
  manual consolidated-sheet template (requested on the discovery call per
  the transcript, not confirmed received). Chase this early, not in Week 4.
- **`src/` vs `backend/` duplication** adds ongoing risk of the two drifting
  further apart if not resolved in Week 1 — every fix found today would
  need porting twice otherwise.
