# 08: Deployment & Operations

Deployed as a **Databricks App**: one container, one `command`, two
processes (FastAPI + Next.js) started by `start.sh`.

## `app.yaml`

```yaml
command: ["bash", "start.sh"]

env:
  - name: DATABRICKS_HTTP_PATH
    value: "/sql/1.0/warehouses/894ac035bea82a7f"  # test_sql_dbr
  - name: DATABRICKS_LLM_ENDPOINT
    value: "databricks-claude-haiku-4-5"
```

Confirmed working format as of the current deployment. `DATABRICKS_HTTP_PATH`
points at a specific SQL warehouse's connection path (found under that
warehouse's "Connection details" tab in the Databricks UI).
`DATABRICKS_LLM_ENDPOINT` is a Databricks-hosted, pay-per-token
foundation model endpoint on the target workspace
(`adb-3103344838598474.14.azuredatabricks.net`), confirmed working via a
direct notebook test using the OpenAI-compatible client before being
wired into the app. `databricks-gpt-oss-120b` is a documented alternative
on the same workspace if a larger open-weights model is ever preferred.

## `start.sh`: process orchestration

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8001 &
# ... liveness check: process alive + /health responds ...
PORT="${DATABRICKS_APP_PORT:-${PORT:-8080}}"
cd frontend && npm install && npm run build && exec npm run start
```

Key decisions, each with a reason baked into the script's own comments:

- **FastAPI binds `127.0.0.1:8001` only**, never exposed externally.
  Deliberately *not* 8000, since Databricks Apps may assign that as the
  externally-exposed port for the Next.js process; if both tried to bind
  the same port, whichever started first would win silently and the
  other would fail to bind invisibly.
- **An explicit startup check** (`kill -0` on the backend PID, then a
  `curl` against `/health`) fails loudly with `exit 1` and a clear
  message if FastAPI didn't actually come up, rather than silently
  starting Next.js against a dead backend.
- **The port Next.js binds to is not fully confirmed**: the exact env
  var Databricks Apps injects for "which port to bind to" was
  unconfirmed at time of writing. The script falls back through
  `DATABRICKS_APP_PORT`, then a generic `PORT`, then a hardcoded `8080`
  default. **If a deployed app fails to bind correctly, this is the
  first thing to check**: confirm the real variable name in the
  Databricks Apps docs/UI and fix the `PORT` line.

## Environment variables (local dev, `.env` copied from `.env.example`)

| Variable | Required? | Purpose |
|---|---|---|
| `DATABRICKS_HTTP_PATH` | Yes | SQL warehouse connection path, required in every environment |
| `DATABRICKS_SERVER_HOSTNAME` | Only with `DATABRICKS_TOKEN` | Workspace hostname, for the explicit-token auth path |
| `DATABRICKS_TOKEN` | No | A personal access token, simplest for local dev. Unset falls back to the SDK's default credential chain (a CLI profile locally, auto-injected credentials as a deployed app) |
| `DATABRICKS_LLM_ENDPOINT` | No | Model Serving endpoint name for both AI features. Unset means both 503 with a clear "not configured" message; everything else works fine |

## Unity Catalog permissions: the recurring operational gap

**As of the current state of this project, the app's service principal
has only `USE CATALOG` / `USE SCHEMA` / `SELECT`** on
`ingestion_framework_test.bid_data_exploration`. This is sufficient for
every read-only feature (the BOQ comparison itself, round tracking, the
negotiation report, RFQ browsing) but **not** for any app-owned overlay
table write:

| Feature | Needs |
|---|---|
| `bid_analyzer_users` (identity) | `CREATE TABLE` + `INSERT`/`UPDATE` |
| `bid_analyzer_projects` | `CREATE TABLE` + `INSERT`/`UPDATE` |
| `bid_analyzer_price_corrections` | `CREATE TABLE` + `INSERT` |
| `bid_analyzer_line_disqualifications` | `CREATE TABLE` + `INSERT` |
| `bid_analyzer_partial_bids` | `CREATE TABLE` + `INSERT` |
| Negotiation narrative | "Can Query" on the `DATABRICKS_LLM_ENDPOINT` serving endpoint |
| Beta pricing | Same "Can Query" grant (shared endpoint) |

Every write endpoint is designed to **503 with a clear, actionable
message** when the underlying grant is missing, rather than a bare stack
trace; this is intentional, not a bug to "fix" by catching the error
differently. When a grant does land, no code change is needed; the next
write attempt simply succeeds. See `databricks/schema/README.md` and
`databricks/FINDINGS.md` for the full, current status of each grant
request.

**Confirmed working, as a point of reference**: the negotiation narrative
feature's Model Serving "Can Query" grant *did* land and was verified
end-to-end on a real deploy, proving the request-and-grant cycle works;
it's simply been requested table-by-table rather than once for
everything.

## UAT / access notes

- The **dev Databricks App link is the correct thing to share for UAT**,
  no separate reverse-proxy/nginx setup is needed. Databricks Apps
  already handles the externally-routable HTTPS endpoint; a person just
  needs to (a) have access to the underlying Databricks workspace and
  (b) be granted access to the specific app.
- Access is granted per-user directly on the Databricks App resource
  (workspace admin action), not via anything this codebase controls.

## Git-synced deployment note: no per-file exclude on initial sync

If this app (or another one on this workspace) is ever deployed via a
Databricks **Git-synced folder** rather than a direct file upload, be
aware there is **no per-file exclude mechanism for the initial sync**
(unlike a `databricks sync` CLI invocation, which can support a
`.databricksignore`). A file that fails Databricks' notebook-format
validation anywhere in the synced folder can break the whole deployment.
This is why `databricks/notebooks/*.ipynb` (documentation-only Jupyter
notebooks with large embedded HTML outputs) were removed from this
branch entirely rather than fixed in place; they're safely preserved on
the `maximo-data-analysis` branch instead. If a future deployment error
mentions "Error downloading source code" or "may not be a valid
notebook," check for exactly this class of problem first.
