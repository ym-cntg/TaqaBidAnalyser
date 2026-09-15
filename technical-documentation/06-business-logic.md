# 06 — Cross-Cutting Business Logic

Rules and patterns that show up in more than one feature, documented
once here rather than repeated per-module.

## The fail-open overlay fetch pattern

Every overlay fetch that reads app-owned or uncertain-schema data wraps
its query in a bare `try/except Exception: return {}`:

- `_fetch_corrections`
- `_fetch_technical_status`
- `_fetch_manual_disqualifications`
- `_fetch_partial_bids`

The reasoning: a missing table (the `CREATE TABLE` grant hasn't landed
yet), a missing column (`QL2` might not exist on every environment's
`quotationline`), or any other transient failure on one of these
*optional, additive* overlays must never take down the core, read-only
comparison view. The cost of failing open is that a real flag silently
doesn't apply; the alternative — failing closed — would mean a grant gap
in one small feature breaks the entire BOQ comparison page. This is a
deliberate, repeated tradeoff, not an oversight, and it's called out
explicitly in `databricks/FINDINGS.md` as the first thing to check if a
flag that should be showing up isn't (see
[09-troubleshooting.md](09-troubleshooting.md)).

Contrast this with `_fetch_vendor_roster` and `_fetch_quotationlines` in
`comparison.py` — these are **not** fail-open; a failure there raises a
503, because they're the core data the whole view depends on, not an
optional overlay.

## The "OR enforcement" pattern for add-only overrides

Manual disqualification must never be able to *undo* a real Maximo
`QL2='TNA'` rejection — only add to what Maximo already flagged, or undo
an analyst's own earlier manual entry. This is enforced with zero
special-case validation code:

```python
technically_disqualified = ql2_disqualified or manual_disqualified
```

No code path checks "is this trying to override Maximo?" — it falls
directly out of the boolean `OR`. A `disqualified=false` write against a
`QL2='TNA'` line is accepted and stored (the row exists in the overlay
table), it simply has no effect on the merged result. This is the
preferred pattern in this codebase for "X can add to, but never
override, Y": express it as a boolean combination read at display time,
not as a write-time gate. It's simpler to verify (one line to read) and
impossible to accidentally bypass by adding a new write path later.

## Append-only overlay tables, latest-row-wins

Every `bid_analyzer_price_corrections` / `bid_analyzer_line_disqualifications`
/ `bid_analyzer_partial_bids` write is an `INSERT`, never an `UPDATE` or
`DELETE`. "Undoing" something is a new row with the opposite value
(`disqualified=false`, `is_partial=false`). Resolution to "what's the
current value" happens in Python, not SQL: fetch all rows for the RFQ
`ORDER BY <timestamp> ASC`, then overwrite a dict keyed by the entity —
the last write in iteration order naturally wins.

Why not `ORDER BY ... DESC LIMIT 1` per key in SQL instead? Because every
fetch needs *every* key's latest row in one query (there's no single key
being looked up), and the Python dict-overwrite achieves that in one
pass over one query result, with no per-key subquery.

## Identity — deliberately not real authentication

`backend/api/users.py` resolves "who is this" two ways: a forwarded
platform identity header (several candidate header names are checked;
**it is unverified whether Databricks Apps actually sends any of
these**), or a self-reported display name that the frontend caches in
`localStorage` under the key `bid-analyzer.identity`
(`frontend/src/lib/identity.ts`).

This is explicitly **not** a real auth system. The actual access
boundary is already being an authorized, signed-in user in TAQA's
Databricks workspace — required just to reach the deployed app at all.
Self-reported identity exists only to attribute corrections/
disqualifications/partial-bid flags to a readable name in the UI (`"Fixed
by Ada Analyst"`), not to gate access to anything. A self-reported
`display_name` is matched case-insensitively against existing users
(`email IS NULL` scoped, so it can never collide with a real forwarded
identity of the same name) — meaning two different people could
plausibly present as the same self-reported name and share an identity
row. That's an accepted limitation of this trust model, not a bug.

## SQL construction — string interpolation, not parameterized queries

Every query in this codebase is a Python f-string, not a parameterized
query with bound placeholders. User-controllable values (`rfqnum`,
`vendor`, free-text `note`/`reason`, search terms) are always passed
through `escape_sql_literal()` (doubles embedded single quotes — standard
ANSI SQL string escaping) before being interpolated into a `'...'`
literal, and free-text search additionally escapes `%`/`_`/`\` for
`ILIKE` patterns (`_escape_like_pattern` in `rfqs.py`). Numeric values
(`rfqlinenum`, `unit_cost`) are interpolated directly as Python-formatted
numbers, never quoted — since they're validated as floats/numbers by the
request dataclass before reaching SQL, they can't carry injected string
content.

This is a conscious tradeoff for this codebase's scale, not a
recommended general pattern: `databricks-sql-connector`'s Delta/SQL
warehouse driver support for a fully parameterized `execute(sql, params)`
call was not the path taken here. Any new query added to this codebase
should follow the existing `escape_sql_literal()` convention exactly —
never skip escaping on a new interpolated string value.

## AI feature guardrails

Two AI features exist, deliberately built to very different risk
profiles — see `databricks/FINDINGS.md` for the full discussion that
preceded building each.

### Negotiation narrative (`negotiation_narrative.py`) — low-risk, fact-bound

- **Only system-computed data enters the prompt**: vendor codes/names,
  computed totals/ranks/flag counts, and the digest's own issue-detail
  strings. The one free-text user input anywhere in this app (a price
  correction's `note` field) is **deliberately excluded** from the
  prompt — a stated prompt-injection guardrail, not an oversight.
- **No `primary_award`/recommendation field** in the output schema at
  all — advisory observations only, so the model structurally cannot
  produce an award decision.
- **A deterministic safety net runs after every response** — code the
  model's output can never override, not an instruction it might
  ignore: `_apply_safety_net()` strips any observation referencing a
  vendor that isn't actually one of this RFQ's real submitting vendors
  (blocks a hallucinated vendor reference), appending a caveat that
  explains what was removed rather than silently dropping it.
- **Error taxonomy**: `not_configured` (missing env var, 503),
  `api_error` (the Model Serving call itself failed, 502 — usually a
  missing "Can Query" grant), `parse_error` (response wasn't the
  expected JSON shape, 502).

### Beta pricing (`beta_pricing.py`) — deliberately higher-risk, flagged before building

The model is explicitly asked to **invent** a unit price from general
knowledge, with real vendor quotes given only as context, "not a formula
to average or anchor to." This is the opposite of the narrative
feature's "never invent a number" rule, and that difference was
surfaced to the user *before* building it, who explicitly chose this
design after being told the tradeoff. Every other guardrail is arguably
*more* important here as a result:

- Always advisory, always opt-in — never computed on page load, never
  persisted anywhere
- Every single estimate carries a **self-reported confidence level**
  (`low`/`medium`/`high`), defaulted down to `low` if the model's answer
  is missing or invalid — never silently upgraded
- Visually distinct in the UI from real vendor prices (never green/red
  "cheapest/priciest" styling, never plain non-italic text — see
  [07-frontend.md](07-frontend.md)'s `BetaCell`)
- A safety net drops any estimate for a line number that wasn't actually
  in the batch it was given (blocks a hallucinated line reference), and
  any non-positive or non-numeric price

### Why both features batch/cap their output

`negotiation_narrative.py`'s first live run against a 9-vendor RFQ hit a
real bug: the response got truncated before finishing valid JSON at the
original 1200-token budget. Fixed by raising the token budget *and*
capping each vendor's write-up length in the prompt, so output size
stays bounded regardless of vendor count. `beta_pricing.py` was designed
from the start with this lesson applied: rather than one large call with
a big budget, it splits the BOQ into small batches
(`BETA_BATCH_SIZE = 20` lines) so no single call's expected output size
scales with the whole BOQ.

## Why AI features use Databricks Model Serving, not an external API

An explicit choice made after a completed AI Impact Assessment for this
project: `WorkspaceClient().serving_endpoints.query()` reuses the exact
same auto-detected credential chain `db.py`'s SQL connection already
relies on (no new secret to manage), and vendor pricing data never
leaves TAQA's governed Databricks workspace. `DATABRICKS_LLM_ENDPOINT`
is currently `databricks-claude-haiku-4-5`, a Databricks-hosted
foundation model endpoint on the target workspace (confirmed working via
a direct test) — not a custom-deployed model, so there's no separate
serving capacity to manage.
