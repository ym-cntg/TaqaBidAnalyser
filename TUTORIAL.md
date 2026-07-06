# TAQA Bid Analyzer — End-to-End Tutorial

This document explains **why this project exists, what problem it solves, and exactly
how the code solves it** — from the raw PDF a bidder emails in, to the pixel on screen
a procurement analyst looks at. It reflects the actual state of the repo as of
2026-07-06, not the aspirational plan.

---

## Part 1 — The Business Problem

### Who this is for

TAQA / **ADDC** (Abu Dhabi Distribution Company) runs procurement tenders for power
and water infrastructure. The Business Unit is Procurement, owned by **Salem
Abdulrahim, Asim Hassan, Yaser Al Derei, Mariam Mohammed**, with **Mohammed Al
Katheri** as the subject-matter expert (a procurement analyst on the power team) who
walked our team through the process. Our build team: **Shiladitya Biswas, Vanden
Jain, Aleksandr Uvarov, Sunish Rajendran Narayanan**.

### The manual process, in Mohammed's own words

The project's discovery call (`project_details/power_transcript.md`) is worth reading
directly, but here's the process he described, step by step:

1. **Download offers.** Bidders submit through **Maximo (IBM)**, TAQA's procurement
   portal. *"They submit offers through Maximo, usually as Excel sheets. Some of the
   bidders... only submit PDF."*
2. **Force everything into Excel.** If a bidder only sends a PDF, Mohammed either asks
   them to resend as Excel, or — if that's too slow — **manually retypes it**:
   *"if it's taking time, then we need to manually [enter it] into our sheet."* He is
   explicit that this is the single biggest time sink: *"The hassle is really copy and
   pasting... this is really taking time, at least for me... I think everyone will
   share the same thing. But other than that, I really enjoy numbers."*
3. **Build one consolidated comparison sheet.** Every bidder's prices get copied into
   one spreadsheet, one column-group per bidder, aligned against ADDC's own
   standardized **BOQ (Bill of Quantities)** — *"we provide the BOQ to the bidders and
   they provide, they quote based on our BOQ."* Because the BOQ item numbers are fixed
   by ADDC, item 1.1 from one bidder is directly comparable to item 1.1 from another —
   **as long as nobody altered the template**, which he also checks for.
4. **Check for problems**, while consolidating:
   - **Unquoted items** — qty exists but no price was given.
   - **Arithmetic errors** — line totals that don't equal qty × rate.
   - **Description changes** — a bidder subtly altering the BOQ text (there's
     supposed to be protection against this, but he checks anyway).
5. **Spot outliers and unbalanced bids.** *"Bidders can reduce... have lower prices in
   the electrical and higher prices in the civil because these are the milestones
   where they will complete [first]... to have a better cash flow."* This is
   **unbalanced/front-loaded bidding** — loading cost onto early-delivery line items to
   get paid sooner — and it's explicitly something he flags even when a bidder's
   overall total looks fine.
6. **Prepare negotiation notes.** Everything flagged above becomes talking points for
   the negotiation round. *"At the first round, we usually don't eliminate any
   bidder"* — outliers might just be a misunderstanding of the BOQ, not bad faith.
7. **Repeat across 3–4 negotiation rounds**, re-extracting and re-comparing each time
   the bidder revises their offer.
8. **Final award decision** also folds in things outside this tool's scope: technical
   evaluation (pass/fail gate before commercial evaluation even starts), financial
   standing, liquidity, and capacity/current project load — *"this is not shared with
   the bidder, this is internally."*
9. **Lots.** A tender like D-111808 bundles *construction of three separate primary
   substations* (SHBPRY, DRPRY, SMHPRY) as three **lots**, which can be awarded
   together or split across different contractors depending on commercial/technical/
   financial evaluation — hence every price in this system is tracked per-lot, not
   just per-tender.

### The business case (from `project_details/bid_use_case.png`)

| Driver | Value |
|---|---|
| Total bids/year (3-yr avg award value) | 2,812 |
| Hours spent per bid today | 7 |
| AI-driven bid analysis time reduction | 40–80% |
| Total annual procurement award value | AED 2,040M |
| FTE annual cost | AED 360–700K |
| **5-year cumulative impact** | **AED 8–36M** |
| **Upfront investment** | **AED 3.5M** |
| **5-year ROI** | **x2–10** |
| Annual OPEX | AED 0.2M |

Use case description straight from the charter: **"Bid document intelligence"** (read
and extract specs/pricing from bid documents) + **"Commercial evaluation insights &
recommendations"** (stage-wise summaries culminating in recommended award scenarios,
scalable without adding headcount).

The throughline for every design decision below: **Mohammed doesn't want help
analyzing — he's good at that and enjoys it.** He wants the copy-paste eliminated and
the obvious red flags surfaced automatically so his time goes to judgment calls, not
data entry.

---

## Part 2 — Two implementations live in this repo

```
bid_analyzer_demo/
  src/          CLI batch pipeline (Excel/HTML report generator). Frozen since early on.
  backend/      FastAPI service. This is "the app" — every recent commit touches only this.
  frontend/     Next.js 16 / React 19 UI that talks to backend/ over HTTP.
  data/power/   Sample bidder submissions for tender D-111808.
  .cache/       Content-hash cache of expensive PDF/OCR extractions.
```

`src/` was the first proof-of-concept: point it at a folder, it walks every file,
extracts, analyzes, and writes a static `.xlsx`/`.html` report to `output/`. It still
runs (`python main.py`), but it hasn't been touched since commit `1d6e98d`, and its
Azure OCR fallback is dead code (`src/extraction/router.py` imports
`src/extraction/azure_parser.py`, which was never created). Treat it as a reference
implementation, not the product.

`backend/` + `frontend/` is the real, live system — a FastAPI JSON API and a React
dashboard, built independently with its own (very similar but not identical) BOQ
parsing logic. **This is what the rest of this tutorial covers.**

---

## Part 3 — The data, concretely

`CLAUDE.md` still says there are 2 sample bidders (AGPOWER, AL Geemi). **That's
stale** — `data/power/` currently has **8**:

| Bidder | Rounds available |
|---|---|
| AGPOWER | original, round1, round2 |
| AL Geemi | original, round1, round2, round3 |
| DANWAY | original, round1, round2 |
| ELMEC | original, round1, round2 |
| POWER LINES | original, round1, round2, round3 |
| Ray | original, round1, round2 |
| Site | original, round1, round2, round3 |
| Spaceage | original, round1, round2, round3 |

Every round folder looks like:

```
{Bidder}/{round}/
  excel/   *.xlsx   (BOQ per lot, plus a "Final Summary" file)
  pdf/     *.pdf    (same content as PDF — sometimes scanned/stamped, sometimes digital)
```

A **BOQ Excel file** has one sheet per work category (Construction Works, Load
Diversion, Dismantling, Spare Parts), each with the same 9 columns: `Item,
Description, Unit, Qty, CIF Unit Rate, CIF Total, Erection Unit Rate, Erection Total,
Total (A+B)`. **CIF** = supply/import cost, **Erection** = installation labor cost —
the split that matters for detecting front-loaded bidding (Part 1, step 5).

Confirmed live via `/api/sample/extract/AGPOWER` while verifying this tutorial:
AGPOWER's *original* round totals **AED 579.5M** across 3 lots (Lot 1: 195.4M, Lot 2:
192.9M, Lot 3: 191.2M), split as AED 103.7M CIF / AED 91.8M Erection on Lot 1 — a
roughly 53/47 split, i.e. not front-loaded.

---

## Part 4 — Backend: the end-to-end pipeline

Every one of these steps exists because of a specific line in Mohammed's transcript.
Start: `uvicorn backend.main:app --reload --port 8000` (see `backend/main.py` — just a
FastAPI app with CORS open to `localhost:3000/3001` and everything mounted under `/api`).

### 4.1 Discovery & routing — replaces "download offers, decide Excel vs PDF"

`backend/extraction/router.py::parse_bidder_folder_pdf()` walks a bidder's folder
round by round. For each round it **prefers PDF over Excel** (the opposite of what you'd
expect, and the opposite of `src/`'s preference) because in production a bidder's
"official" submission is the signed PDF — Excel is a convenience copy. It:

- Filters out non-BOQ PDFs by filename (`cover`, `trade license`, `manpower`,
  `financial statement`, `cv`, `hse award`, ... — see the `skip_exact` list) so a
  bidder's cover letter or company profile never gets mistaken for pricing data.
- Falls back to Excel per-round if PDF extraction produced nothing, only
  `lot_number: 0` (unidentified lots), or one suspiciously oversized unsplit lot
  (>500 items — a sign multiple lots got parsed as one table).

### 4.2 Extraction — replaces "manually retype the PDF into Excel"

`backend/extraction/router.py::extract_pdf()` is the single entry point per file:

```
check .cache/extractions/<sha256-of-file-content>.json   → hit? return cached lots
  ↓ miss
PyMuPDF table detection (backend/extraction/pdf_parser.py) — free, fast
  ↓ found < 3 priced non-header line items? treat as failure
Azure Document Intelligence "prebuilt-layout" (backend/extraction/ocr_parser.py)
  ↓
save successful result to cache
```

This is the direct automation of Mohammed's *"if it's taking time, we do it
manually"* step — for a clean digital PDF, PyMuPDF's `find_tables()` gets ~95%
accuracy for free. For a scanned/stamped PDF (photocopied signature pages are common
in real submissions), it falls back to real OCR via Azure.

**Caching gotcha worth knowing**: caching is keyed on file *content* hash, and **only
successful extractions are cached** (`cache.py::save_cached` is only called when
`lots` is non-empty). Files that fail extraction — a few specific ones in the sample
data throw a real Azure API round-trip *every single request*, adding minutes to
`/api/sample/compare/*` calls. This is a real perf bug worth fixing eventually, not
something we've patched.

### 4.3 Item matching across bidders — replaces "align columns in the consolidated sheet"

Mohammed's sheet-building step only works if every bidder used identical item
numbers. In practice they don't — OCR mangles "1.03" into "1,03", bidders occasionally
skip an item. `backend/analysis/item_matcher.py::match_items()` is a 4-tier waterfall,
cheapest first:

1. **Exact** `item_no` match.
2. **Normalized** — strips leading zeros, fixes `,`/`;` used instead of `.` (a common
   OCR artifact): `"1.03"` → `"1.3"`.
3. **Fuzzy** description match — `difflib.SequenceMatcher` on cleaned text (stopwords
   like "supply", "of", "the" stripped), threshold ≥ 0.85, greedy assignment by
   descending score. Skipped above 10,000 candidate pairs as a cost guard.
4. **LLM** (opt-in via `ENABLE_LLM_MATCHING=true` + `ANTHROPIC_API_KEY`) — only the
   still-unmatched items get sent, one batch call, to `claude-haiku-4-5-20251001`,
   asking it to match semantically equivalent line items across bidders. Anything
   below 0.7 confidence is discarded.

`backend/analysis/comparator.py::compare_round()` picks the first bidder
alphabetically as the **reference** and matches every other bidder against it, lot by
lot.

### 4.4 Flagging — replaces "check for problems" and "prepare negotiation notes"

Still in `comparator.py`, `_detect_flags()` runs per lot per bidder and produces the
exact list of things Mohammed manually looks for:

| Flag category | Logic | Transcript quote it automates |
|---|---|---|
| `unquoted` | qty > 0 but no CIF/Erection/Total price at all | *"if there is any quoted or unquoted items"* |
| `arithmetic` | `qty × cif_unit_rate` differs from `cif_total` by > 1.0 AED | *"any arithmetical or calculation errors"* |
| `outlier` | one bidder's item total is >3x or <0.33x another bidder's for the same item | *"someone is quoting very at a discount"* |
| `unbalanced` | a lot's CIF is >90% of (CIF + Erection) | *"loading the cost on the earlier milestones"* |

Severities: `critical` (arithmetic), `warning` (unquoted, unbalanced, high outliers),
`info` (low-side outliers — "potential underpricing", worth a note but not urgent).

**Gap worth knowing**: Mohammed's process explicitly spans *"3–4 negotiation
rounds, re-extract and compare each time."* `src/analysis/round_tracker.py` computes
this (per-bidder, per-lot % change from first to last round) — but **the backend has
no equivalent**. The frontend's round-over-round line chart (`price-chart.tsx`) is
built entirely client-side by calling `extractBidder` once per bidder and grouping by
`round_name` — there's no server-side "did this bidder's price jump suspiciously
between rounds" flag yet.

### 4.5 API surface (`backend/api/routes.py`)

- `POST /api/upload` — one-off file upload (xlsx or pdf), parsed and returned
  immediately. **In-memory only** — restarting the server loses it, there's no
  persistence layer.
- `GET /api/sample/bidders`, `/api/sample/rounds` — what's available under `data/power/`.
- `GET /api/sample/extract/{bidder}` — every round for one bidder.
- `GET /api/sample/compare/{round_name}` — the main comparison payload (matched
  items + flags + totals) that drives Compare, Flags, and (looped per-bidder) the
  Dashboard.

---

## Part 5 — Frontend: page by page

Next.js 16 (App Router) + React 19, talking to the backend purely over `fetch`
(`frontend/src/lib/api.ts`). No auth, no server-side rendering of bid data — every
page is `"use client"` and fetches on mount.

We recently gave the whole UI a **cohesive visual pass** (colors/spacing/typography
only — zero behavior changes, verified against the real API and screenshotted every
page before/after):

- **New color system** (`frontend/src/app/globals.css`) — replaced the previous flat
  grayscale shadcn default with an actual brand palette: a deep teal/blue primary
  (`oklch(0.46 0.12 224)`), a warmer 5-color chart palette, and a subtle two-tone
  radial gradient wash behind the main content area (`.bg-app-gradient`). Both light
  and dark CSS variable sets were updated, though the app has no theme toggle wired up
  yet — dark mode is defined but currently unreachable.
- **Sidebar** (`components/sidebar.tsx`) — gradient logo mark, a left accent bar +
  tinted background on the active nav item, and a "Live data connected" status
  indicator in the footer.
- **Card** (`components/ui/card.tsx`) — swapped a flat `ring-1` border for a soft
  drop shadow that lifts slightly on hover, used everywhere (KPI tiles, lot summaries,
  flag cards).
- Compare/Explorer/Upload pages — lot/sheet tabs became a segmented pill control
  (`bg-muted` track, active tab gets `bg-card` + shadow), table headers became
  uppercase/tracking-wide with sticky first columns, rows got subtle zebra striping.
- Flags page — severity colors (critical/warning/info) moved from flat
  `bg-red-50`-style Tailwind swatches to opacity-mixed brand-consistent tints that also
  have real dark-mode variants.

### Dashboard (`/`)
On load: fetches bidders + rounds, then `compareRound(firstRound)` for lot/flag
summary KPIs, then **loops `extractBidder()` once per bidder** to build the
round-over-round price chart. With 8 bidders this is the slowest page to first
paint — see the perf note in 4.2.

### Upload & Extract (`/upload`)
Drag-and-drop a single `.xlsx`/`.pdf`, hits `POST /api/upload`, renders the parsed
sheets/items immediately. This is the most direct answer to *"the hassle is really
copy and pasting"* — one file in, structured data out, no spreadsheet touched.

### Compare Bidders (`/compare`)
Round selector + lot tabs, side-by-side line-item comparison table with a match-
quality dot (exact/normalized/fuzzy/LLM/unmatched) per row and min/max price
highlighting per item — this *is* Mohammed's consolidated comparison sheet, rebuilt
as a live table.

### Flags & Insights (`/flags`)
Every `Flag` from 4.4, filterable by severity/category/bidder — this is the
negotiation-prep note list.

### BOQ Explorer (`/explorer`)
Drill into one bidder → round → lot → sheet → raw line items. The "just show me what
they actually submitted" view.

---

## Part 6 — Running it locally

```bash
# Backend
cd bid_analyzer_demo
uv run uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000/health, http://localhost:8000/api/...

# Frontend
cd frontend
npm run dev
# → http://localhost:3000

# Or both, via nginx-fronted Docker:
docker compose up --build
# → http://localhost
```

Two environment gotchas we hit and resolved while verifying this tutorial (neither is
a code bug — both are local-machine state):

1. **`.venv` was built on a different machine** (`pyvenv.cfg` points at
   `/Users/ksahu/.local/share/uv/python/...`, a path that doesn't exist here) — its
   `python` symlink is dangling. We ran the backend against system
   `/opt/miniconda3/bin/uvicorn` after `pip install`-ing the handful of missing
   packages (`pymupdf`, `python-multipart`, `azure-ai-documentintelligence`,
   `azure-core`) instead of rebuilding the venv. Rebuilding `.venv` properly
   (`uv sync`) is the real fix if you're setting this up fresh.
2. **`node_modules/**/*.node` were quarantine-flagged by macOS** (`com.apple.quarantine`,
   apparently stamped by however the folder was transferred), which blocks Next.js's
   native SWC/lightningcss bindings from loading (`library load disallowed by system
   policy`). Fixed with `find node_modules -name "*.node" -exec xattr -d
   com.apple.quarantine {} \;`.
3. **`/api/sample/compare/*` can take minutes**, not seconds — a few sample PDFs fail
   local extraction and fall back to a real Azure Document Intelligence call every
   time (failures aren't cached — see 4.2). Upload and BOQ Explorer don't hit this path
   and load fast.

---

## Part 7 — What's actually next

Ranked by how directly each one maps back to a line in Mohammed's transcript:

- **Cache extraction failures too** (or at least the "no Azure credentials configured /
  Azure returned nothing" case), so `/api/sample/compare/*` doesn't re-attempt the same
  doomed Azure call on every request.
- **Server-side round-tracking + flags** (port `src/analysis/round_tracker.py`'s logic
  into `backend/`, and consider flagging suspiciously large jumps between rounds) —
  directly serves the "3–4 negotiation rounds" step, currently only a client-side chart.
- **Report export** — the backend has no "download a comparison report" feature;
  `src/reporting/` (Excel + HTML generation) exists but isn't wired to the live app.
- **Persist `/api/upload` results** — currently in-memory, lost on restart.
- **Description-change detection** — Mohammed explicitly checks bidders didn't alter
  BOQ wording; nothing in either pipeline currently diffs descriptions across bidders
  or rounds.
- **Update `CLAUDE.md`** — sample data (2 bidders documented vs. 8 present) and the
  "Next Steps" checklist are both stale relative to what's built.
