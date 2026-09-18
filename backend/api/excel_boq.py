"""Upload a vendor Excel file and get a normalized BOQ back.

Deliberately stateless and storage-free: nothing uploaded here is
written to disk, to Unity Catalog, or to Maximo. The file is parsed in
memory and the result returned in the response, so this endpoint needs
no Databricks grant at all and cannot affect any existing data. That
also means there is no upload history; re-uploading is the only way to
see a previous result again.
"""

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.excel_boq.generator import to_dict, to_workbook
from backend.excel_boq.parser import parse_workbook

router = APIRouter(tags=["excel-boq"])

ACCEPTED_SUFFIXES = (".xlsx", ".xlsm")
# Large enough for every sample file in this repo by a wide margin,
# small enough that a mistaken upload cannot exhaust app memory.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
        return parse_workbook(stream, name)
    except HTTPException:
        raise
    except Exception as exc:
        # The real reason, not a guessed one: a corrupt zip, a password
        # -protected workbook and an unsupported format all land here
        # and the caller needs to tell them apart.
        raise HTTPException(400, f"Could not read {name}: {type(exc).__name__}: {exc}")


@router.post("/excel-boq/parse")
async def parse_excel_boq(file: UploadFile = File(...)):
    """Parse one workbook and return the extracted BOQ as JSON."""
    stream, name = await _read_upload(file)
    document = _parse_or_400(stream, name)
    if not document.sheets:
        raise HTTPException(
            422,
            f"No BOQ table found in {name}. "
            f"Sheets examined: {', '.join(s.sheet_name for s in document.skipped) or 'none'}.",
        )
    return to_dict(document)


@router.post("/excel-boq/export")
async def export_excel_boq(file: UploadFile = File(...)):
    """Parse one workbook and return the normalized BOQ workbook."""
    stream, name = await _read_upload(file)
    document = _parse_or_400(stream, name)
    if not document.sheets:
        raise HTTPException(422, f"No BOQ table found in {name}.")

    output = to_workbook(document)
    download_name = f"{name.rsplit('.', 1)[0]}-BOQ.xlsx"
    return StreamingResponse(
        output,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
