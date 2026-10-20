# CI/CD

Two workflows. `ci.yml` runs itself; `deploy.yml` you trigger.

## CI, on every push and PR

| Job | Does | Why it is there |
|---|---|---|
| Backend | `uv sync --frozen`, import the app, ruff, pytest | The sync step fails the same way a deploy would if a dependency is undeclared, which is the failure that took the app down once. The import step catches a malformed route before a test has to. |
| Frontend | `npm ci`, `tsc --noEmit`, eslint, `npm run build` | The build is the one `start.sh` runs at deploy time, so a red build here is a failed deploy there. |
| Deployable | `app.yaml`, `start.sh` and `pyproject.toml` present, `APP_BUILD` set | Cheap guards on the deploy contract, which breaks in ways that point nowhere near the cause. |

eslint is non-blocking for now. It has never run against this codebase,
so failing on its first run would block every PR on pre-existing
findings. Make it blocking once that backlog is cleared.

### The test suite

66 tests, about 45 seconds, **no Databricks connection and no Unity
Catalog grant required**. That is deliberate: CI has neither, and
neither does the deployed app for the write paths. The suite runs
against the real environment, not an idealised one.

| File | Covers |
|---|---|
| `test_excel_parser.py` | Both BOQ templates, subtotal handling, cross-referenced prices, the self-inconsistent vendor file, workbook export |
| `test_comparison_engine.py` | That the Maximo path is unchanged by the upload source injection, and that the report prices at the latest round |
| `test_uploads_api.py` | The upload path end to end over HTTP, including the confirm gate and every rejected input |
| `test_ai_pricing.py` | That AI pricing degrades rather than 500s, across all four real failure modes |

Fixtures are five real vendor spreadsheets in `tests/fixtures`, 1.2MB.
The full 105-file corpus in `data/` is not committed at 276MB; the tests
that want it skip when it is absent, so a developer gets the wider run
locally and CI gets the representative one.

```bash
uv pip install -r requirements-dev.txt
uv run pytest
uv run pytest tests/test_comparison_engine.py -v
```

`requirements-dev.txt` is deliberately separate from `pyproject.toml`.
Databricks Apps installs from pyproject, and adding a dependency there
has already taken the whole app down once, so test tooling is kept
where it cannot do that.

## Deploy, manual

`workflow_dispatch` with a `staging` or `production` target. Manual on
purpose: there is one app and it is in production, so a push to the
live branch must not redeploy by itself. Make staging automatic once a
second app exists.

The job re-runs the tests, stamps the commit SHA into `app.yaml` as
`APP_COMMIT`, syncs to the workspace, deploys, then polls `/health`
until it reports that SHA. That last step is the point: a deploy that
succeeds while serving the previous build is the failure mode this
catches, and it has happened.

### Configuration needed before it will run

Nothing is set yet, and the workflow fails with a message naming what
is missing rather than half-deploying.

Per environment, under Settings, Environments:

| Kind | Name | Value |
|---|---|---|
| Secret | `DATABRICKS_HOST` | e.g. `https://adb-3103344838598474.14.azuredatabricks.net` |
| Secret | `DATABRICKS_CLIENT_ID` | Service principal for deployment |
| Secret | `DATABRICKS_CLIENT_SECRET` | Its secret |
| Variable | `DATABRICKS_APP_NAME` | The app's name in the workspace |
| Variable | `DATABRICKS_SOURCE_PATH` | Workspace path to sync into, e.g. `/Workspace/Users/.../bid-analyzer` |
| Variable | `DATABRICKS_APP_URL` | The app's URL, for the smoke test. Omitted means deploy without verifying. |

Add a required reviewer on the `production` environment so a release
needs a human approval.

Confirm the two `databricks` CLI invocations against your workspace on
the first run. They follow documented usage but were never executed
against this workspace from CI.

## What is still missing

- **No staging app.** Both environments point at the same place until a
  second one exists, so `production` is the only real target today.
- **`main` is 65 commits behind** the live branch. CI covers both, but
  the branch model needs a decision.
- **Grant-dependent paths are stubbed, not exercised.** Nothing tests a
  real write to Unity Catalog, because no environment can do one yet.
