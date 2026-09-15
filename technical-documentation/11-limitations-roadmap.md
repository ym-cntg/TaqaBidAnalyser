# 11: Known Limitations & Roadmap

## Current limitations, by area

### Data / Maximo integration

- **`companies` is unprofiled.** Only ever used via a single join to
  resolve vendor names; its full schema, timestamp columns (if any),
  and row count are unknown.
- **No reliable incremental-load watermark on most tables.** Of the six
  Maximo tables the app uses, only `DISCOUNTHISTORY`/`DISCOUNTHISTORYLINE`
  have a confirmed `ROWSTAMP` audit column. `quotationline`, the
  largest table at 1.66M rows, has no change-timestamp at all: a
  confirmed real gap (a post-quote discount was applied to 46% of lines
  on one BOQ with zero timestamp trail of when). See
  [04-data-model.md](04-data-model.md).
- **`QL2`'s real behavior on `quotationline` for a detailed construction
  BOQ is unverified.** Its value distribution was only directly measured
  on `altquotationline` (a smaller, non-construction sample). Built
  fail-open specifically to de-risk this; worth confirming against a
  real detailed BOQ post-deployment.
- **No lot-level rollup.** No lot column or structure exists anywhere in
  the real Maximo schema for a multi-lot tender; contract totals are
  computed as a flat sum across all of a vendor's lines, with no
  lot-level subtotal.
- **`DISCOUNTHISTORY`/`DISCOUNTHISTORYLINE`'s full-snapshot-vs-delta
  semantics are still unconfirmed** against live data, mitigated by the
  forward-fill reconstruction (correct either way), not resolved.

### BOQ Comparison Engine

- **`LINES_CAP = 500`**: a BOQ larger than this is truncated in the
  returned line list (though every aggregate is still computed over the
  *full* line set). The negotiation report inherits this same cap
  through its BOQ-issue collection.
- **Only `QL2 = 'TNA'` counts as a technical disqualification.**
  `NOQUOTE`/`Cancel`/`CNA` are left as-is, an explicit product decision,
  not a completeness gap, but worth revisiting if TAQA's real usage
  expects more statuses to disqualify.
- **No bulk operations** on price corrections, disqualifications, or
  partial-bid flags; every write is one line/vendor at a time.
- **No listing endpoint** for "everything disqualified/corrected/flagged
  on this RFQ and why," beyond what's visible per-cell in the comparison
  table itself.
- **The negotiation report and AI narrative don't yet know about
  partial bids.** A partial bidder's contract total could still be
  described there without the "not directly comparable to a full-scope
  bid" caveat the comparison page now shows.

### Round tracking

- Anomaly-flag thresholds (`INCREASE_TOLERANCE`, `PEER_DEVIATION_THRESHOLD`,
  `PEER_MIN_SAMPLE`) are first-pass values, not yet tuned against a large
  volume of real negotiation-round data.

### AI features

- Both features depend on `DATABRICKS_LLM_ENDPOINT` being configured and
  granted "Can Query", confirmed working for the narrative feature on a
  real deploy, but this is a per-endpoint grant, not a durable platform
  guarantee.
- Beta pricing is capped at `BETA_LINES_CAP = 60` lines per RFQ; a BOQ
  larger than that only gets estimates for its first 60 lines.

### Identity / access

- Not real authentication (by design, see
  [06-business-logic.md](06-business-logic.md)). Two different people
  presenting the same self-reported display name will share one identity
  row.
- Whether Databricks Apps actually forwards any platform identity header
  is unverified; the self-reported fallback path is what's actually
  exercised in practice today.

### Document extraction (from `CLAUDE.md`, not yet built into the app)

The original business case included extracting BOQ prices directly from
bidder-submitted PDF/Excel documents (the biggest manual pain point per
the source process). This proof-of-concept work (`openpyxl` for Excel,
PyMuPDF `find_tables()` for digital PDFs at ~95% accuracy, OCR needed for
scanned/stamped submissions) exists as exploratory findings but is
**not** wired into the deployed app; the current app reads exclusively
from already-ingested Maximo data, not from raw bid documents.

## Roadmap

Carried forward from `CLAUDE.md`'s "Next Steps" and the natural
extensions of work already documented in `databricks/FINDINGS.md`:

- [ ] Confirm `QL2`'s real value distribution on a live detailed
      construction BOQ (the single highest-value verification given how
      much of the comparison engine depends on it)
- [ ] Resolve the outstanding Unity Catalog grants for every
      `bid_analyzer_*` table (see [08-deployment-operations.md](08-deployment-operations.md))
- [ ] Surface partial-bid status in the negotiation report and AI
      narrative, not just the BOQ Comparison tab
- [ ] Bulk correction/disqualification (multi-select rows, one write)
- [ ] A listing/audit view of every manual override on an RFQ
- [ ] OCR path for scanned/stamped bidder PDF submissions (Azure
      Document Intelligence or Google Document AI recommended for
      production; docTR/Surya evaluated for POC)
- [ ] A document-extraction pipeline wiring the PDF/Excel POC work into
      the live app, for tenders whose pricing isn't yet in Maximo's
      structured tables at all (the exact situation found on tender
      D-111808, per `CLAUDE.md`'s sample-data notes)
- [ ] Explore water/other utility bid types, expected to have a
      different BOQ structure than the power-sector tenders profiled so
      far
- [ ] Tune round-tracking anomaly-flag thresholds against a larger
      volume of real negotiation history once available
