"""Standalone Excel BOQ extractor, deployable as its own Databricks App.

Separate from the main bid-analyzer app on purpose. This one has no
Databricks dependency at all: no SQL warehouse, no Unity Catalog, no
Maximo, no identity, and therefore no grant to wait on. It parses an
uploaded spreadsheet in memory and returns the result, which is why it
can be handed to client testers without touching anything in UAT.

Run locally:  python excel_boq_app/main.py
Deployed:     app.yaml runs `python main.py` with this folder as root.
"""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

# Works both ways: as a package from the repo root (the main app's
# layout) and as the deploy root, where this folder itself is the app
# and `excel_boq` sits directly alongside.
try:
    from excel_boq.generator import to_dict, to_workbook
    from excel_boq.parser import parse_workbook
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from excel_boq.generator import to_dict, to_workbook
    from excel_boq.parser import parse_workbook

STATIC_DIR = Path(__file__).resolve().parent / "static"
ACCEPTED_SUFFIXES = (".xlsx", ".xlsm")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = FastAPI(
    title="Excel BOQ Extractor",
    description="Upload a vendor's priced spreadsheet, get a normalized bill of quantities.",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


async def _read_upload(upload: UploadFile) -> tuple[BytesIO, str]:
    name = upload.filename or "upload.xlsx"
    if not name.lower().endswith(ACCEPTED_SUFFIXES):
        raise HTTPException(
            400,
            f"{name} is not an .xlsx/.xlsm file. "
            "Legacy .xls and PDF submissions are not supported by this tool.",
        )
    payload = await upload.read()
    if not payload:
        raise HTTPException(400, f"{name} is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"{name} is {len(payload) / 1_048_576:.1f}MB, over the 25MB limit."
        )
    return BytesIO(payload), name


def _parse_or_400(stream: BytesIO, name: str):
    try:
        document = parse_workbook(stream, name)
    except Exception as exc:
        # Surface the real reason. A corrupt zip, a password-protected
        # workbook and an unsupported format all land here and a tester
        # needs to be able to tell them apart.
        raise HTTPException(400, f"Could not read {name}: {type(exc).__name__}: {exc}")
    if not document.sheets:
        raise HTTPException(
            422,
            f"No BOQ table found in {name}. "
            f"Sheets examined: {', '.join(s.sheet_name for s in document.skipped) or 'none'}.",
        )
    return document


@app.post("/api/parse")
async def parse(file: UploadFile = File(...)):
    stream, name = await _read_upload(file)
    return to_dict(_parse_or_400(stream, name))


@app.post("/api/export")
async def export(file: UploadFile = File(...)):
    stream, name = await _read_upload(file)
    document = _parse_or_400(stream, name)
    download_name = f"{name.rsplit('.', 1)[0]}-BOQ.xlsx"
    return StreamingResponse(
        to_workbook(document),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


if __name__ == "__main__":
    import uvicorn

    # Databricks Apps injects the externally-exposed port. The exact
    # variable name was unconfirmed at time of writing (see the main
    # app's start.sh, which has the same fallback chain), so try both
    # before the documented default.
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8080)
    uvicorn.run(app, host="0.0.0.0", port=port)
