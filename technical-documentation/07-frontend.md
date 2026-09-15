# 07 — Frontend

Next.js (App Router), TypeScript, Tailwind CSS. No global state
management library — each page/tab owns its own `useState`/`useEffect`
data fetching, and cross-tab state (identity, which round is selected)
is either recomputed per-tab or passed down as simple props.

## Page map

| Route | File | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Projects landing page: identity resolution, project list, "New project" panel with an RFQ picker |
| `/rfqs` | `app/rfqs/page.tsx` | Standalone RFQ browse/search/filter/paginate table |
| `/projects/[id]` | `app/projects/[id]/page.tsx` → `project-detail-client.tsx` | Project detail shell with three tabs |

### The three project-detail tabs

`project-detail-client.tsx` holds `activeTab` state (`"comparison" |
"rounds" | "report"`) and conditionally renders one of:

- **`rfq-comparison.tsx`** — BOQ Comparison (by far the largest and most
  interactive tab — see below)
- **`round-tracking.tsx`** — the round-over-round trend chart + flags
  table (see [03-round-negotiation-tracking.md](03-round-negotiation-tracking.md))
- **`negotiation-report.tsx`** — the ranked negotiation-prep digest, AI
  summary card, and Excel export link

## `rfq-comparison.tsx` — the most complex component

State: `data` (the fetched `ComparisonResponse`), `round` (selected
round or `undefined` for original), plus **three independent inline-edit
modes**, each with its own `{target, value, saving, error}` state group:
`editing` (price correction), `disqualifying` (line disqualification),
and a per-vendor `partialSaving`/`partialError` pair for the partial-bid
checkbox. A `betaState` union tracks the AI Beta-pricing toolbar
separately.

### `PriceCell` — one component, mutually exclusive render branches

Every price cell in the table is rendered by a single `PriceCell`
component with three exclusive branches, checked in order:

1. **`isEditing`** — a numeric input + Check/X icons (price correction)
2. **`isDisqualifying`** — either a reason text input (new
   disqualification) or a one-click "Re-qualify this line?" confirm
   (undoing an existing manual disqualification) + Check/X icons
3. **Default display branch** — the price itself, with hover-revealed
   action icons layered in front of it:
   - **Pencil** (`editable` — original round + identified user): starts
     a price correction
   - **Lock**, non-interactive (Maximo-locked, `QL2='TNA'`) — no click
     handler at all, deliberately, rather than a button that would
     silently do nothing if pressed (see the "OR enforcement" rule in
     [06-business-logic.md](06-business-logic.md))
   - **ShieldOff** (manually disqualified) — click opens the re-qualify
     confirm; tooltip shows who disqualified it and why
   - **Ban** (`canDisqualify`, not yet disqualified) — starts a new
     disqualification

All hover-revealed icons use `opacity-0 group-hover/cell:opacity-100`
on a parent `group/cell` class — nothing is visible until the cell is
hovered, keeping the default table view clean.

### Every write refetches, never patches locally

`saveEdit`, `confirmDisqualify`, and `togglePartialBid` all call
`await load(round)` after a successful write, rather than optimistically
updating the one cell that changed. A single correction, disqualification,
or partial-bid flag can change `is_lowest`, contract totals, and
split-award totals for the *entire* line or vendor — not just the one
cell that was edited — so a full refetch is the only way to keep every
downstream computed value correct.

### The "Lowest" badge computation lives in the frontend, not the backend

```typescript
const fullScopeTotals = data.vendors.filter((v) => !v.is_partial_bid).map((v) => v.contract_total);
const lowestTotal = fullScopeTotals.length > 0 ? Math.min(...fullScopeTotals) : null;
```

The backend's `contract_total` field is never altered by the partial-bid
flag — only this frontend-side "who's eligible to be Lowest" computation
changes. This keeps the backend's numbers honest and puts the
presentation decision where it belongs.

### `BetaCell`

Deliberately never uses `priceColor`'s green/red styling or plain
non-italic text — Beta must never look visually equivalent to a real
vendor quote at any confidence level. `CONFIDENCE_STYLE` maps
`low`/`medium`/`high` to increasingly less-muted italic text, and the
tooltip always shows the model's stated confidence and rationale.

## `frontend/src/lib/`

| File | Purpose |
|---|---|
| `api.ts` | Every fetch wrapper + response/request TypeScript type, one `ApiError`/`AiUnavailableError` class hierarchy for error handling |
| `identity.ts` | `getCachedIdentity()`/`resolveIdentity()`/`clearCachedIdentity()` — the `localStorage` identity cache, key `bid-analyzer.identity` |
| `format.ts` | `formatNumber`/`formatAED`/`formatDate` — centralized so every page formats numbers/dates the same way |
| `boq-category.ts` | Labels/badge-variant/order for the four `BoqCategory` values |
| `orgs.ts` | The `ORG_OPTIONS` dropdown list (`ADDCORG`, `TRANSORG`, etc., plus `"all"`) |
| `rounds.ts` | `formatRoundLabel()` — turns `"original"`/`"1.0"` into display labels |
| `utils.ts` | Generic helpers (e.g. the shadcn `cn()` class-merge utility) |

### `api.ts` error handling pattern

Every fetch wrapper funnels non-OK responses through a shared
`handleJson<T>()` that throws `ApiError` (carries `status` +
the backend's `detail` message verbatim — **never rewritten or
pattern-matched**, per a fixed bug: an earlier version guessed at
"pending an admin grant" by matching the word "grant" in the error text,
which also matched unrelated real errors and mislabeled them). The two
AI endpoints (`generateNegotiationNarrative`, `generateBetaPricing`) use
a separate `AiUnavailableError` class instead, whose `notConfigured`
flag is `true` exactly when the backend returned 503 — letting the UI
show setup instructions only in the one case that's actually about
configuration.

## `frontend/src/components/ui/`

A minimal shadcn-style set: `Badge`, `Button`, `Card` (+ subcomponents).
Not a full design system — just enough shared primitives to keep
badges/buttons/cards visually consistent across pages without a larger
dependency.

## Known frontend quirks worth knowing about

- **`localhost` vs `127.0.0.1` in dev**: `next dev`'s `allowedDevOrigins`
  check rejects the HMR WebSocket when the page is loaded from
  `127.0.0.1` instead of `localhost`, which silently prevents React
  hydration entirely (the page looks stuck on "Loading…" with no console
  error). Always develop against `http://localhost:3000`.
- **JSX/SWC whitespace stripping**: a plain space character directly
  touching a `</span>` boundary on the same source line can be silently
  stripped by this project's JSX transform, even with no intervening
  newline — not just the documented "newline adjacent to a tag" case.
  Two real instances of this were found and fixed by using an explicit
  `{" "}` immediately after the closing tag. See
  [09-troubleshooting.md](09-troubleshooting.md) for the reproduction.
