"""FastAPI routes for the bid analyzer.

Original-bidding skeleton: this branch only ever looks at each bidder's
'original' round submission. Negotiation-round tracking, ad-hoc file
upload, and multi-round comparison are out of scope here.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..extraction.router import parse_bidder_folder_pdf as parse_bidder_folder
from ..analysis.comparator import compare_round
from .serializers import serialize_extraction, serialize_comparison

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Cache parsed bidder data so Excel/PDF files are only read once
_bidder_cache: dict[str, list] = {}  # "bidder_path" -> parsed extractions


def _get_bidder_extractions(bidder_path: Path, bidder_name: str):
    """Parse bidder folder once, return cached result on subsequent calls.

    Uses PDF extraction (with Azure fallback for scanned docs),
    falling back to Excel when no PDFs are available.
    """
    key = str(bidder_path)
    if key not in _bidder_cache:
        _bidder_cache[key] = parse_bidder_folder(bidder_path, bidder_name)
    return _bidder_cache[key]


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
