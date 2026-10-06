"""Excel-upload projects: create, add vendor/round files, review, edit,
confirm.

BETA. The feature is labelled as such in the UI and the reasons are
real: uploaded BOQs live in a process-local store (see
backend/uploads/store.py) and are lost on restart, and cross-vendor line
matching relies on vendors numbering their BOQ items consistently, which
is true of the ADDC template but is not guaranteed of every submission.

The flow is deliberately two-phase. Files are extracted into a staged,
editable BOQ, and nothing drives the comparison until an analyst
confirms it. Extraction is good but not infallible, so the analyst sees
and fixes what was read before any of it becomes an evaluation.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, HTTPException, Query, Request

from backend.excel_boq.parser import parse_workbook
from backend.uploads.models import (
    ORIGINAL,
    UploadedBoq,
    UploadedLine,
    UploadedPrice,
    UploadedSubmission,
)
from backend.uploads.source import UploadedSource
from backend.uploads.store import get_store

router = APIRouter(tags=["uploads"])

ACCEPTED_SUFFIXES = (".xlsx", ".xlsm")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _require(project_id: str) -> UploadedBoq:
    boq = get_store().get(project_id)
    if boq is None:
        raise HTTPException(404, f"No uploaded project {project_id!r}.")
    return boq


def _require_editable(project_id: str) -> UploadedBoq:
    boq = _require(project_id)
    if boq.confirmed:
        raise HTTPException(
            409,
            "This BOQ is confirmed and in use by the analysis tabs. "
            "Reopen it for editing first.",
        )
    return boq


@dataclass
class CreateUploadProject:
    name: str
    user_id: str
    user_label: str | None = None


@router.post("/uploads", status_code=201)
async def create_upload_project(body: CreateUploadProject):
    if not body.name.strip():
        raise HTTPException(400, "Project name is required.")
    boq = UploadedBoq(
        project_id=uuid.uuid4().hex,
        name=body.name.strip(),
        created_by=body.user_id,
        created_by_label=body.user_label,
        created_at=_now(),
    )
    get_store().put(boq)
    return _serialise(boq)


@router.get("/uploads")
async def list_upload_projects():
    store = get_store()
    out = []
    for pid in store.project_ids():
        boq = store.get(pid)
        if boq is None:
            continue
        out.append(
            {
                "project_id": boq.project_id,
                "name": boq.name,
                "created_by": boq.created_by,
                "created_by_label": boq.created_by_label,
                "created_at": _iso(boq.created_at),
                "confirmed": boq.confirmed,
                "vendor_count": len(boq.vendor_names),
                "round_count": len(boq.rounds_present),
                "line_count": len(boq.lines),
            }
        )
    return {"projects": out}


@router.get("/uploads/{project_id}")
async def get_upload_project(project_id: str):
    return _serialise(_require(project_id))


def _normalise_item_no(item_no: str | None) -> str | None:
    if item_no is None:
        return None
    text = str(item_no).strip()
    return text or None


def _match_or_create_line(boq: UploadedBoq, item_no: str | None, description: str,
                          unit: str | None, quantity: float | None,
                          section: str | None, by_item: dict[str, float],
                          by_desc: dict[str, float]) -> float:
    """Find the existing BOQ line this extracted row belongs to, or make
    a new one.

    Item number first, because that is what the ADDC template
    standardises and what Maximo's own RFQLINENUM join relies on.
    Description is a deliberate second resort for vendors who strip or
    renumber the item column; it is matched case-insensitively on the
    exact text, never fuzzily, since a near-match on a BOQ description
    would silently merge two genuinely different items.
    """
    key = _normalise_item_no(item_no)
    if key and key in by_item:
        return by_item[key]

    desc_key = description.strip().lower()
    if not key and desc_key and desc_key in by_desc:
        return by_desc[desc_key]

    line_number = boq.next_line_number()
    boq.lines[line_number] = UploadedLine(
        line_number=line_number,
        item_no=key,
        description=description,
        unit=unit,
        quantity=quantity,
        section=section,
    )
    if key:
        by_item[key] = line_number
    if desc_key:
        by_desc.setdefault(desc_key, line_number)
    return line_number


@router.post("/uploads/{project_id}/files", status_code=201)
async def add_file(
    project_id: str,
    request: Request,
    vendor: str = Query(...),
    round_label: str = Query(ORIGINAL),
    vendor_name: str | None = Query(None),
    filename: str = Query("upload.xlsx"),
):
    """Extract one vendor's priced spreadsheet at one round into the
    staged BOQ.

    The spreadsheet arrives as the raw request body with its metadata in
    the query string, rather than as a multipart form. That is
    deliberate: FastAPI's File/Form require python-multipart, which is
    an extra dependency to install at deploy time, and adding it broke
    the package install. A single file needs no multipart envelope
    anyway, so this removes the dependency rather than pinning around
    it.
    """
    boq = _require_editable(project_id)

    vendor = vendor.strip()
    if not vendor:
        raise HTTPException(400, "A vendor code or name is required for each file.")
    round_label = (round_label or ORIGINAL).strip() or ORIGINAL
    if round_label != ORIGINAL:
        try:
            # Normalised to the float form the round-snapshot builder
            # produces ("1" becomes "1.0"). Without this the store and
            # the engines disagree on the label for the same round, and
            # the round selector sends a value the comparison rejects.
            round_label = str(float(round_label))
        except ValueError:
            raise HTTPException(
                400,
                f"Round must be {ORIGINAL!r} or a number such as '1' or '2', got {round_label!r}.",
            )

    name = (filename or "upload.xlsx").strip() or "upload.xlsx"
    if not name.lower().endswith(ACCEPTED_SUFFIXES):
        raise HTTPException(
            400,
            f"{name} is not an .xlsx/.xlsm file. "
            "Legacy .xls and PDF submissions are not supported.",
        )
    payload = await request.body()
    if not payload:
        raise HTTPException(400, f"{name} is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{name} is {len(payload)/1_048_576:.1f}MB, over the 25MB limit.")

    try:
        document = parse_workbook(BytesIO(payload), name)
    except Exception as exc:
        raise HTTPException(400, f"Could not read {name}: {type(exc).__name__}: {exc}")

    if not document.boq_sheets:
        raise HTTPException(
            422,
            f"No priced BOQ table found in {name}. "
            f"Sheets examined: {', '.join(s.sheet_name for s in document.skipped) or 'none'}.",
        )

    # Rebuild the match indexes from what is already staged, so a second
    # vendor's file lands on the same lines as the first.
    by_item = {l.item_no: n for n, l in boq.lines.items() if l.item_no}
    by_desc: dict[str, float] = {}
    for n, l in boq.lines.items():
        by_desc.setdefault(l.description.strip().lower(), n)

    added = 0
    for sheet in document.boq_sheets:
        for line in sheet.lines:
            if line.kind != "item":
                continue
            line_number = _match_or_create_line(
                boq, line.item_no, line.description, line.unit, line.quantity,
                line.section, by_item, by_desc,
            )
            existing = boq.lines[line_number]
            # Quantity and unit belong to the BOQ, not to a vendor. The
            # first file to supply them wins; a later vendor disagreeing
            # is a real finding for the analyst, not something to
            # silently overwrite.
            if existing.quantity is None and line.quantity is not None:
                existing.quantity = line.quantity
            if not existing.unit and line.unit:
                existing.unit = line.unit

            unit_cost = line.unit_rate
            if unit_cost is None and line.cif_unit_rate is not None:
                unit_cost = (line.cif_unit_rate or 0.0) + (line.erection_unit_rate or 0.0)
            line_cost = line.line_total
            if unit_cost is None and line_cost is not None and existing.quantity:
                unit_cost = line_cost / existing.quantity

            boq.prices[(line_number, vendor, round_label)] = UploadedPrice(
                line_number=line_number,
                vendor=vendor,
                round_label=round_label,
                unit_cost=unit_cost,
                line_cost=line_cost,
            )
            added += 1

    boq.vendor_names.setdefault(vendor, None)
    if vendor_name and vendor_name.strip():
        boq.vendor_names[vendor] = vendor_name.strip()

    reconciliation = document.reconciliation
    boq.submissions.append(
        UploadedSubmission(
            submission_id=uuid.uuid4().hex,
            vendor=vendor,
            round_label=round_label,
            filename=name,
            uploaded_at=_now(),
            line_count=added,
            extracted_total=document.grand_total,
            stated_total=document.summary_total,
            reconciles=reconciliation.agrees if reconciliation else None,
        )
    )
    get_store().put(boq)
    return _serialise(boq)


@dataclass
class LineEdit:
    description: str | None = None
    unit: str | None = None
    quantity: float | None = None
    item_no: str | None = None


@router.patch("/uploads/{project_id}/lines/{line_number}")
async def edit_line(project_id: str, line_number: float, body: LineEdit):
    boq = _require_editable(project_id)
    line = boq.lines.get(line_number)
    if line is None:
        raise HTTPException(404, f"No line {line_number} in this BOQ.")

    if body.description is not None:
        line.description = body.description
    if body.unit is not None:
        line.unit = body.unit or None
    if body.item_no is not None:
        line.item_no = _normalise_item_no(body.item_no)
    if body.quantity is not None:
        if body.quantity <= 0:
            raise HTTPException(400, "Quantity must be greater than zero.")
        line.quantity = body.quantity
        # Line totals are quantity times rate, so changing the quantity
        # has to recompute every vendor's total on this line or the two
        # stop agreeing and the arithmetic check fires on the analyst's
        # own edit.
        for key, price in boq.prices.items():
            if key[0] == line_number and price.unit_cost is not None:
                price.line_cost = price.unit_cost * body.quantity

    get_store().put(boq)
    return _serialise(boq)


@router.delete("/uploads/{project_id}/lines/{line_number}")
async def delete_line(project_id: str, line_number: float):
    boq = _require_editable(project_id)
    if line_number not in boq.lines:
        raise HTTPException(404, f"No line {line_number} in this BOQ.")
    del boq.lines[line_number]
    for key in [k for k in boq.prices if k[0] == line_number]:
        del boq.prices[key]
    get_store().put(boq)
    return _serialise(boq)


@dataclass
class PriceEdit:
    line_number: float
    vendor: str
    round_label: str
    unit_cost: float | None


@router.patch("/uploads/{project_id}/prices")
async def edit_price(project_id: str, body: PriceEdit):
    boq = _require_editable(project_id)
    line = boq.lines.get(body.line_number)
    if line is None:
        raise HTTPException(404, f"No line {body.line_number} in this BOQ.")
    if body.vendor not in boq.vendor_names:
        raise HTTPException(400, f"{body.vendor!r} is not a vendor on this BOQ.")

    key = (body.line_number, body.vendor, body.round_label)
    if body.unit_cost is None:
        # Clearing a price makes the line unquoted for that vendor,
        # which is a real state, not a deletion of the row.
        boq.prices.pop(key, None)
    else:
        if body.unit_cost < 0:
            raise HTTPException(400, "Unit cost cannot be negative.")
        boq.prices[key] = UploadedPrice(
            line_number=body.line_number,
            vendor=body.vendor,
            round_label=body.round_label,
            unit_cost=body.unit_cost,
            line_cost=body.unit_cost * line.quantity if line.quantity else body.unit_cost,
        )
    get_store().put(boq)
    return _serialise(boq)


@router.delete("/uploads/{project_id}/files/{submission_id}")
async def remove_file(project_id: str, submission_id: str):
    """Drop one uploaded file and every price it contributed."""
    boq = _require_editable(project_id)
    match = next((s for s in boq.submissions if s.submission_id == submission_id), None)
    if match is None:
        raise HTTPException(404, "No such uploaded file on this project.")

    for key in [k for k in boq.prices if k[1] == match.vendor and k[2] == match.round_label]:
        del boq.prices[key]
    boq.submissions = [s for s in boq.submissions if s.submission_id != submission_id]

    # A vendor with no remaining prices anywhere is no longer on the
    # BOQ at all; leaving them would show an empty column.
    if not any(k[1] == match.vendor for k in boq.prices):
        boq.vendor_names.pop(match.vendor, None)

    get_store().put(boq)
    return _serialise(boq)


@router.post("/uploads/{project_id}/confirm")
async def confirm(project_id: str):
    boq = _require(project_id)
    if not boq.lines:
        raise HTTPException(400, "Nothing to confirm: no BOQ lines have been extracted yet.")
    if not boq.vendor_names:
        raise HTTPException(400, "Nothing to confirm: no vendor files have been uploaded yet.")
    boq.confirmed = True
    boq.confirmed_at = _now()
    get_store().put(boq)
    return _serialise(boq)


@router.post("/uploads/{project_id}/reopen")
async def reopen(project_id: str):
    boq = _require(project_id)
    boq.confirmed = False
    boq.confirmed_at = None
    get_store().put(boq)
    return _serialise(boq)


@router.delete("/uploads/{project_id}")
async def delete_upload_project(project_id: str):
    _require(project_id)
    get_store().delete(project_id)
    return {"deleted": project_id}


def source_for(project_id: str) -> UploadedSource:
    """Used by the analysis endpoints to read a confirmed uploaded BOQ."""
    boq = _require(project_id)
    if not boq.confirmed:
        raise HTTPException(
            409, "This BOQ has not been confirmed yet. Review and confirm it first."
        )
    return UploadedSource(boq)


def _serialise(boq: UploadedBoq) -> dict:
    lines = sorted(boq.lines.values(), key=lambda l: l.line_number)
    vendors = boq.vendors
    rounds = boq.rounds_present
    return {
        "project_id": boq.project_id,
        "name": boq.name,
        "source_type": "upload",
        "created_by": boq.created_by,
        "created_by_label": boq.created_by_label,
        "created_at": _iso(boq.created_at),
        "confirmed": boq.confirmed,
        "confirmed_at": _iso(boq.confirmed_at),
        "vendors": [{"vendor": v, "name": boq.vendor_names.get(v)} for v in vendors],
        "rounds": rounds,
        "line_count": len(lines),
        "submissions": [asdict(s) | {"uploaded_at": _iso(s.uploaded_at)} for s in boq.submissions],
        "lines": [
            {
                **asdict(line),
                "prices": {
                    f"{v}|{r}": {
                        "unit_cost": p.unit_cost,
                        "line_cost": p.line_cost,
                    }
                    for v in vendors
                    for r in rounds
                    if (p := boq.prices.get((line.line_number, v, r))) is not None
                },
            }
            for line in lines
        ],
    }
