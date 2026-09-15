# 09: Troubleshooting

Known issues actually encountered during development, with root cause
and fix, not a generic checklist.

## "A flag/overlay I expect isn't showing up"

**Check the grant status first, before assuming a logic bug.** Every
overlay fetch (`_fetch_corrections`, `_fetch_technical_status`,
`_fetch_manual_disqualifications`, `_fetch_partial_bids` in
`comparison.py`) is deliberately fail-open (see
[06-business-logic.md](06-business-logic.md)); if the underlying table
doesn't exist yet, or the query fails for any reason, the overlay simply
doesn't apply, silently. This is by design, not a bug, but it means a
missing `CREATE TABLE`/`INSERT` grant (see
[08-deployment-operations.md](08-deployment-operations.md)) looks
identical to "nobody has entered any corrections/disqualifications/
partial-bid flags yet." Confirm the grant status before debugging the
comparison logic itself.

## A write endpoint 503s with a permission-shaped error

Expected, not a bug, until the relevant Unity Catalog grant lands; see
the table in [08-deployment-operations.md](08-deployment-operations.md).
The error message is deliberately the real, unmodified exception text
from `databricks-sql-connector` (`f"Could not save X: {exc}"`), not a
guessed/rewritten one; see the next entry for why guessing is
explicitly avoided.

## Never pattern-match an error message to guess its cause

A real, fixed bug: an earlier version of the frontend's error display
guessed at "this is a pending grant issue" by checking whether the
backend's error string contained the word `"grant"`. Real, unrelated
errors that also happened to contain that word got silently mislabeled
with the wrong explanation. Fixed by always showing the backend's actual
`detail` message verbatim (see `api.ts`'s `ApiError`), never rewrite or
pattern-match an error for display. If you're tempted to special-case an
error message anywhere in this codebase, don't; add a distinct, real
error code/field to the response instead (see `AiUnavailableError`'s
`notConfigured` flag, driven by the actual HTTP status code, not string
matching).

## Databricks deployment error: "Error downloading source code... may not be a valid notebook"

Encountered when this app was (at one point) deployed from a Git-synced
folder that also contained `databricks/notebooks/*.ipynb` files. Root
cause: a notebook with a large embedded HTML cell output (~92KB) was
occasionally misidentified by file-type detection, and a Git-synced
Databricks deployment has **no per-file exclude mechanism** on its
initial sync (unlike a CLI `databricks sync` with `.databricksignore`).
Fix: the notebooks were removed from this branch entirely (they're
documentation-only, not runtime code, and are safely preserved on the
`maximo-data-analysis` branch). If this resurfaces, don't try to repair
the notebook's internal JSON format; check whether any notebook file is
present in whatever's being synced, and exclude the whole directory or
move it to a branch that isn't deployed.

## Local dev: page stuck on "Loading..." forever, no console error

Cause: the page was loaded from `http://127.0.0.1:3000` instead of
`http://localhost:3000`. `next dev`'s `allowedDevOrigins` check silently
rejects the Hot Module Reload WebSocket from `127.0.0.1`, which prevents
React hydration from ever completing, with no error printed anywhere.
Fix: always use `localhost`, never `127.0.0.1`, for the frontend dev
server URL (this includes any Playwright/automated browser scripts
against local dev).

## `uv sync` silently drops a needed test dependency

`starlette.testclient.TestClient` (used for any ad-hoc backend testing
via `fastapi.testclient`) needs `httpx` present, but a plain `uv sync`
against this project's lockfile does not keep it installed for that
purpose. If a scratch test script fails with an httpx-related import
error after running `uv sync`, re-run `uv pip install httpx2 -q`
(harmless if already present).

## A JSX space silently disappears next to a `<span>`

Two real instances found in `rfq-comparison.tsx`: text like
`` disqualified line, see the{" "} <span>disqualified</span> marker `` had
already correctly used an explicit `{" "}` **before** the tag, but the
plain space immediately **after** the closing `</span>` on the same
source line (`</span> marker`) was silently stripped by this project's
JSX/SWC transform, producing rendered text like `"disqualifiedmarker"`
with no space. This is a stricter behavior than the commonly-documented
JSX rule ("a newline adjacent to a tag is removed"): here, a plain
same-line space touching a `</span>` boundary was stripped too, with no
newline involved at all.

**Fix, and the rule to follow going forward**: whenever inline text
follows a `</span>` (or precedes an opening tag) on the same line,
insert an explicit `{" "}` immediately adjacent to the tag rather than
relying on a plain source-code space, exactly the pattern already used
elsewhere in this codebase, now applied consistently on both sides of a
tag boundary, not just one.

## Verifying against real data vs. mock/scratch fixtures

Several features (technical disqualification's `QL2` behavior on a real
detailed BOQ, `DISCOUNTHISTORY`/`DISCOUNTHISTORYLINE`'s exact
snapshot-vs-delta semantics, `companies`' full schema) were built against
an **explicit decision not to block on live verification first**: the
code is written to be safe either way (fail-open, or correct-by-
construction via forward-fill), and the real-data check is deferred to
first real deployment. If something in one of these areas behaves
unexpectedly against a live warehouse, that is the expected "first thing
to check" moment these decisions were flagged for. See
`databricks/FINDINGS.md` for the specific caveat attached to each one,
and don't assume the code itself is wrong before checking whether the
underlying assumption about the real data turned out to be false.

## AI feature response truncation

If a Model Serving response fails to parse as JSON on a large RFQ (many
vendors / many BOQ lines), suspect **truncation at the token budget**
before suspecting a prompt-format bug; this happened for real once (see
[06-business-logic.md](06-business-logic.md)'s narrative-feature note).
The fix pattern is: cap the *per-item* output size in the prompt
instructions (not just raise `max_tokens`), so the total expected output
size stays bounded regardless of how many vendors/lines are in play. This
is why `beta_pricing.py` batches by `BETA_BATCH_SIZE` rather than sending
the whole BOQ in one call.
