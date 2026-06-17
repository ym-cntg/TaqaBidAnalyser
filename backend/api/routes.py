"""FastAPI routes for the bid analyzer."""

import tempfile
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from ..extraction.excel_parser import parse_lot_file, parse_bidder_folder
from ..extraction.pdf_parser import parse_pdf_boq
from ..analysis.comparator import compare_round
from .serializers import (
    serialize_extraction,
    serialize_lot,
    serialize_comparison,
)

router = APIRouter()

# In-memory store for uploaded extractions
_extractions: dict[str, dict] = {}  # upload_id -> {bidder, round, extraction_data}
DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Cache parsed bidder data so Excel files are only read once
_bidder_cache: dict[str, list] = {}  # "bidder_path" -> parsed extractions


def _get_bidder_extractions(bidder_path: Path, bidder_name: str):
    """Parse bidder folder once, return cached result on subsequent calls."""
    key = str(bidder_path)
    if key not in _bidder_cache:
        _bidder_cache[key] = parse_bidder_folder(bidder_path, bidder_name)
    return _bidder_cache[key]


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), bidder: str = "", round_name: str = "uploaded"):
    """Upload a PDF or Excel BOQ file and extract structured data."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".xlsx", ".pdf"):
        raise HTTPException(400, f"Unsupported file type: {suffix}. Use .xlsx or .pdf")

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix == ".xlsx":
            lot = parse_lot_file(tmp_path)
        else:
            try:
                lot = parse_pdf_boq(tmp_path)
            except ValueError as e:
                raise HTTPException(422, str(e))

        upload_id = str(uuid.uuid4())[:8]
        lot_data = serialize_lot(lot)

        _extractions[upload_id] = {
            "upload_id": upload_id,
            "filename": file.filename,
            "bidder": bidder or "Unknown Bidder",
            "round_name": round_name,
            "lot": lot_data,
        }

        return {
            "upload_id": upload_id,
            "filename": file.filename,
            "lot": lot_data,
            "summary": {
                "lot_name": lot.lot_name,
                "total_items": lot_data["total_items"],
                "total_cif": lot.total_cif,
                "total_erection": lot.total_erection,
                "total_price": lot.total_price,
                "sheets": len(lot.sheets),
            },
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/extractions")
async def list_extractions():
    """List all uploaded extractions."""
    return list(_extractions.values())


@router.get("/extractions/{upload_id}")
async def get_extraction(upload_id: str):
    """Get a specific extraction by upload ID."""
    if upload_id not in _extractions:
        raise HTTPException(404, "Extraction not found")
    return _extractions[upload_id]


@router.get("/sample/bidders")
async def list_sample_bidders():
    """List available sample bidders from the data directory."""
    power_dir = DATA_DIR / "power"
    if not power_dir.exists():
        return []

    bidders = []
    for d in sorted(power_dir.iterdir()):
        if d.is_dir():
            rounds = sorted([
                r.name for r in d.iterdir()
                if r.is_dir() and (r / "excel").exists()
            ])
            bidders.append({"name": d.name, "rounds": rounds})
    return bidders


@router.get("/sample/extract/{bidder}")
async def extract_sample_bidder(bidder: str):
    """Extract all rounds for a sample bidder."""
    bidder_path = DATA_DIR / "power" / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    extractions = _get_bidder_extractions(bidder_path, bidder)
    return [serialize_extraction(e) for e in extractions]


@router.get("/sample/compare/{round_name}")
async def compare_sample_bidders(round_name: str):
    """Compare all sample bidders for a given round."""
    power_dir = DATA_DIR / "power"
    if not power_dir.exists():
        raise HTTPException(404, "No sample data found")

    round_extractions = {}
    for bidder_dir in sorted(power_dir.iterdir()):
        if not bidder_dir.is_dir():
            continue
        extractions = _get_bidder_extractions(bidder_dir, bidder_dir.name)
        for ext in extractions:
            if ext.round_name == round_name:
                round_extractions[bidder_dir.name] = ext

    if not round_extractions:
        raise HTTPException(404, f"No data found for round '{round_name}'")

    result = compare_round(round_extractions, round_name)
    return serialize_comparison(result)


@router.get("/sample/rounds")
async def list_sample_rounds():
    """List all available rounds across all bidders."""
    power_dir = DATA_DIR / "power"
    if not power_dir.exists():
        return []

    rounds = set()
    for bidder_dir in power_dir.iterdir():
        if not bidder_dir.is_dir():
            continue
        for round_dir in bidder_dir.iterdir():
            if round_dir.is_dir() and (round_dir / "excel").exists():
                rounds.add(round_dir.name)

    return sorted(rounds)
