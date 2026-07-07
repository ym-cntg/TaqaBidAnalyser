"""FastAPI routes for the bid analyzer.

Original-bidding skeleton: this branch only ever looks at each bidder's
'original' round submission. Negotiation-round tracking, ad-hoc file
upload, and multi-round comparison are out of scope here.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..extraction.router import parse_bidder_folder_pdf as parse_bidder_folder
from ..analysis.comparator import compare_round
from ..analysis.corrections import (
    EDITABLE_FIELDS,
    apply_corrections,
    clear_correction,
    list_corrections,
    record_correction,
)
from .serializers import serialize_extraction, serialize_comparison

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Cache parsed bidder data so Excel/PDF files are only read once. This is the
# raw, as-extracted data — user corrections are layered on top of it fresh on
# every read (see _get_bidder_extractions), so reverting a correction always
# recovers the true original OCR/parsed value.
_raw_bidder_cache: dict[str, list] = {}  # "bidder_path" -> parsed extractions


def _get_raw_extractions(bidder_path: Path, bidder_name: str):
    """Parse bidder folder once, return cached result on subsequent calls.

    Uses PDF extraction (with Azure fallback for scanned docs),
    falling back to Excel when no PDFs are available.
    """
    key = str(bidder_path)
    if key not in _raw_bidder_cache:
        _raw_bidder_cache[key] = parse_bidder_folder(bidder_path, bidder_name)
    return _raw_bidder_cache[key]


def _get_bidder_extractions(bidder_path: Path, bidder_name: str):
    """Raw extraction with any recorded user corrections applied."""
    raw = _get_raw_extractions(bidder_path, bidder_name)
    return [apply_corrections(ext, bidder_name) for ext in raw]


def _find_raw_item(extraction, lot_number: int, sheet_name: str, item_no: str):
    for lot in extraction.lots:
        if lot.lot_number != lot_number:
            continue
        for sheet in lot.sheets:
            if sheet.name != sheet_name:
                continue
            for item in sheet.items:
                if item.item_no == item_no:
                    return item
    return None


class ItemCorrectionRequest(BaseModel):
    lot_number: int
    sheet_name: str
    item_no: str
    fields: dict


class ItemCorrectionKey(BaseModel):
    lot_number: int
    sheet_name: str
    item_no: str


@router.get("/sample/bidders")
async def list_sample_bidders():
    """List bidders with genuinely extractable original-round data.

    Filesystem presence isn't enough — a bidder can have an original/
    folder that only contains a lot-summary document (no real per-item
    BOQ), which extracts to nothing. Only list bidders whose original
    round actually yields usable data, so the frontend never offers a
    selection that dead-ends.
    """
    power_dir = DATA_DIR / "power"
    if not power_dir.exists():
        return []

    bidders = []
    for d in sorted(power_dir.iterdir()):
        if not d.is_dir():
            continue
        original_dir = d / "original"
        has_original = original_dir.is_dir() and (
            (original_dir / "excel").exists() or (original_dir / "pdf").exists()
        )
        if not has_original:
            continue
        if _get_bidder_extractions(d, d.name):
            bidders.append({"name": d.name})
    return bidders


@router.get("/sample/extract/{bidder}")
async def extract_sample_bidder(bidder: str):
    """Extract the original-round submission for a sample bidder."""
    bidder_path = DATA_DIR / "power" / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    extractions = _get_bidder_extractions(bidder_path, bidder)
    if not extractions:
        raise HTTPException(404, f"No original-round data found for '{bidder}'")

    return serialize_extraction(extractions[0])


@router.get("/sample/compare")
async def compare_sample_bidders():
    """Compare all sample bidders' original-round submissions."""
    power_dir = DATA_DIR / "power"
    if not power_dir.exists():
        raise HTTPException(404, "No sample data found")

    original_extractions = {}
    for bidder_dir in sorted(power_dir.iterdir()):
        if not bidder_dir.is_dir():
            continue
        extractions = _get_bidder_extractions(bidder_dir, bidder_dir.name)
        if extractions:
            original_extractions[bidder_dir.name] = extractions[0]

    if not original_extractions:
        raise HTTPException(404, "No original-round data found")

    result = compare_round(original_extractions, "original")
    return serialize_comparison(result)


@router.post("/sample/extract/{bidder}/correct")
async def correct_item(bidder: str, body: ItemCorrectionRequest):
    """Override one or more fields on a single extracted item.

    This is the fail-safe for OCR/parsing mistakes: a reviewer looking at
    the Explorer table can fix a garbled value here, and every downstream
    calculation (lot/contract totals, the Compare table, flag detection)
    picks up the corrected value on its next read — nothing needs to be
    re-extracted or re-run.
    """
    bidder_path = DATA_DIR / "power" / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    raw = _get_raw_extractions(bidder_path, bidder)
    if not raw:
        raise HTTPException(404, f"No original-round data found for '{bidder}'")

    raw_item = _find_raw_item(raw[0], body.lot_number, body.sheet_name, body.item_no)
    if raw_item is None:
        raise HTTPException(404, "Item not found")

    unknown = set(body.fields) - EDITABLE_FIELDS
    if unknown:
        raise HTTPException(400, f"Unknown field(s): {', '.join(sorted(unknown))}")

    record_correction(bidder, body.lot_number, body.sheet_name, body.item_no, body.fields, raw_item)
    corrected = _get_bidder_extractions(bidder_path, bidder)[0]
    return serialize_extraction(corrected)


@router.post("/sample/extract/{bidder}/revert")
async def revert_item(bidder: str, body: ItemCorrectionKey):
    """Discard a correction and restore the original extracted value."""
    bidder_path = DATA_DIR / "power" / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    clear_correction(bidder, body.lot_number, body.sheet_name, body.item_no)
    corrected = _get_bidder_extractions(bidder_path, bidder)[0]
    return serialize_extraction(corrected)


@router.get("/sample/extract/{bidder}/corrections")
async def get_corrections(bidder: str):
    """List every correction currently applied to a bidder's data."""
    return list_corrections(bidder)
