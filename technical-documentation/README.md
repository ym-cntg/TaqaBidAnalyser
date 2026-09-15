# TAQA Bid Analyzer — Technical Documentation

An AI-assisted commercial bid-analysis tool for TAQA/ADDC procurement,
built against real tender and vendor-bid data ingested from IBM Maximo
into Databricks Unity Catalog. It compares vendor pricing line-by-line
across a BOQ (Bill of Quantities), flags commercial risk (unquoted
lines, arithmetic errors, statistical outliers, technical/manual
disqualification, partial-scope bids), tracks pricing across negotiation
rounds, and produces negotiation-prep summaries — with two optional,
clearly-labeled AI-assisted features layered on top.

Deployed as a single Databricks App: a FastAPI backend reading/writing
Unity Catalog, and a Next.js frontend, running as two processes in one
container. See [01-architecture.md](01-architecture.md) for the full
picture.

## How this documentation is organized

| # | Chapter | What it covers |
|---|---|---|
| 01 | [Architecture](01-architecture.md) | System overview, tech stack, request flow, the read-only-Maximo/additive-app-data principle, directory structure |
| 02 | [BOQ Comparison Engine](02-boq-comparison-engine.md) | The core three-pass comparison algorithm: outlier detection, technical/manual disqualification, partial bids, corrections, split-award totals |
| 03 | [Round-over-Round Negotiation Tracking](03-round-negotiation-tracking.md) | Reconstructing full pricing history from `DISCOUNTHISTORY(LINE)` via forward-fill, and the anomaly-flag rules built on top of it |
| 04 | [Data Model](04-data-model.md) | Every Maximo table and app-owned overlay table actually used, with schema, relationships, and known caveats |
| 05 | [Application](05-application.md) | Backend module-by-module reference, full API endpoint table, shared conventions |
| 06 | [Business Logic](06-business-logic.md) | Cross-cutting rules: fail-open overlays, the "OR enforcement" pattern, identity model, SQL construction, AI guardrails |
| 07 | [Frontend](07-frontend.md) | Page map, the `rfq-comparison.tsx`/`PriceCell` deep dive, `lib/` reference, known frontend quirks |
| 08 | [Deployment & Operations](08-deployment-operations.md) | `app.yaml`/`start.sh`, environment variables, the Unity Catalog grant status, UAT access notes |
| 09 | [Troubleshooting](09-troubleshooting.md) | Known issues actually hit during development, with root cause and fix |
| 10 | [Development Guide](10-development-guide.md) | Local setup, the testing approach, how to add a new overlay-table feature, code style conventions |
| 11 | [Limitations & Roadmap](11-limitations-roadmap.md) | What's known-incomplete today, and what's next |

## Reading order

- **New to the codebase?** Read 01 → 04 → 05 in order, then 02 and 03 for
  the two features with the most going on underneath them.
- **About to build a new feature?** Read 06 (the rules that apply
  everywhere) and 10 (the exact pattern to follow) first.
- **Something's broken?** Start at 09, then 08 if it looks
  permission/deployment-shaped.
- **Scoping what's left to do?** 11.

## Source of truth vs. this documentation

`databricks/FINDINGS.md` remains the authoritative, chronological
data-exploration and design-decision log — every real query result, row
count, corrected theory, and the exact reasoning behind each product
decision lives there, in the order it was discovered. This
`technical-documentation/` set is a **distilled, current-state reference**
built from it and from the code itself, organized by topic rather than by
when it was learned. When the two disagree, treat the code as ground
truth and `FINDINGS.md` as the detailed historical record of *why* it
looks that way; update both together going forward.
