# Excel BOQ Extractor: standalone Databricks App

A self-contained app for client testing. Upload a vendor's priced
spreadsheet, get a normalized bill of quantities plus an extraction
report, and download it as a clean workbook.

Deliberately separate from the main bid analyzer. This app has **no
Databricks dependency at all**: no SQL warehouse, no Unity Catalog, no
Maximo, no identity, and therefore no grant to wait on. Uploads are
parsed in memory and discarded, so nothing is stored and nothing can
affect UAT data.

## Deploying to Databricks Apps

Point a new Databricks App at **this folder** (`excel_boq_app/`) as its
source directory, not the repo root. The repo root holds the main bid
analyzer's own `app.yaml`, and the two must not be deployed as one app.

```
excel_boq_app/            <- app source directory
  app.yaml                command: ["python", "main.py"]
  requirements.txt        fastapi, uvicorn, openpyxl, python-multipart
  main.py                 the server
  static/index.html       the whole frontend, one file, no build step
  excel_boq/              the parser
```

There is no Node, no npm install and no build step, so a deploy is just
the Python install. Access is granted per user on the Databricks App
resource itself, the same workspace-admin action as the main app.

`main.py` binds the port from `DATABRICKS_APP_PORT`, falling back to
`PORT` and then 8080, matching the fallback chain in the main app's
`start.sh` because the exact variable Databricks Apps injects was
unconfirmed at time of writing. If the app fails to bind, check that
first.

## Running locally

```bash
python excel_boq_app/main.py          # http://127.0.0.1:8080
DATABRICKS_APP_PORT=8099 python excel_boq_app/main.py
```

## Endpoints

| Route | Purpose |
|---|---|
| `GET /` | the upload page |
| `GET /health` | liveness check |
| `POST /api/parse` | extracted BOQ as JSON |
| `POST /api/export` | normalized `.xlsx` workbook |

Both POST routes take a single multipart `file`. Limits: `.xlsx`/`.xlsm`
only, 25MB. Legacy `.xls` and PDF are rejected with a clear message
rather than a stack trace.

## Relationship to the main app

The parser in `excel_boq/` is the single source of truth and is shared.
The main bid analyzer imports it at `backend/api/excel_boq.py` and
exposes the same feature at `/excel-boq` inside the Next.js frontend.
Both surfaces, and the CLI, run the same extraction code, so a fix here
applies everywhere.

See [excel_boq/README.md](excel_boq/README.md) for what the extractor
actually does, the layouts it handles, the reconciliation check, and its
known limitations.

## Testing

```bash
python -m tests.test_excel_boq                       # from the repo root
python -m excel_boq_app.excel_boq.cli <files.xlsx>   # CLI over a folder
```
