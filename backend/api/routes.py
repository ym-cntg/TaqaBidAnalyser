"""FastAPI routes for the bid analyzer.

Original-bidding skeleton: this branch only ever looks at each bidder's
'original' round submission. Negotiation-round tracking, ad-hoc file
upload, and multi-round comparison are out of scope here.
"""

import dataclasses
import hashlib
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..extraction.excel_parser import BOQExtraction, parse_bidder_folder_all_rounds
from ..extraction.router import parse_bidder_folder_pdf as parse_bidder_folder
from ..analysis.comparator import ComparisonResult, compare_round, compute_peer_recommendations
from ..analysis.corrections import (
    EDITABLE_FIELDS,
    apply_corrections,
    clear_correction,
    list_corrections,
    record_correction,
)
from ..analysis.match_overrides import (
    clear_match_override,
    list_match_overrides,
    record_match_override,
)
from ..analysis.rounds import build_round_trend
from .projects import get_power_project_root
from ..reporting.comparison_export import build_comparison_excel
from ..reporting.digest import build_report_digest
from ..reporting.excel_export import build_excel_report
from ..reporting.html_export import build_html_report
from ..reporting.llm_report import ReportUnavailable, generate_recommendation_report
from .serializers import serialize_extraction, serialize_comparison, serialize_round_trend

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


def _build_gap_skeleton(bidder_path: Path, bidder_name: str) -> BOQExtraction | None:
    """Build a manual-entry skeleton for a bidder with no extractable BOQ.

    Policy for data gaps (bidders like ELMEC, whose original-round folder
    only contains a lot-summary document, not a per-item BOQ): don't
    silently exclude them. Clone the item structure (item_no, description,
    unit, qty — identical across bidders per the ADDC-standard template)
    from another bidder that does have real original-round data, wipe every
    pricing field, and mark each item `is_missing=True`. This becomes a
    normal-looking extraction with nothing priced yet — a reviewer fills it
    in through the same correction/edit endpoints used for OCR fixes.
    """
    original_dir = bidder_path / "original"
    has_original = original_dir.is_dir() and (
        (original_dir / "excel").exists() or (original_dir / "pdf").exists()
    )
    if not has_original:
        return None  # nothing was even submitted — not a data-gap case

    reference = None
    for d in sorted(bidder_path.parent.iterdir()):
        if not d.is_dir() or d.name == bidder_name:
            continue
        ref_raw = _get_raw_extractions(d, d.name)
        if ref_raw:
            reference = ref_raw[0]
            break
    if reference is None:
        return None  # no other bidder's structure to clone from

    blank_lots = []
    for lot in reference.lots:
        blank_sheets = []
        for sheet in lot.sheets:
            blank_items = tuple(
                dataclasses.replace(
                    item,
                    cif_unit_rate=None,
                    cif_total=None,
                    erection_unit_rate=None,
                    erection_total=None,
                    total=None,
                    raw_cif=None,
                    raw_erection=None,
                    is_corrected=False,
                    is_missing=not item.is_section_header,
                )
                for item in sheet.items
            )
            blank_sheets.append(dataclasses.replace(sheet, items=blank_items))
        blank_lots.append(dataclasses.replace(
            lot,
            sheets=tuple(blank_sheets),
            total_cif=None,
            total_erection=None,
            total_price=None,
        ))

    return BOQExtraction(
        tender_no=reference.tender_no,
        bidder=bidder_name,
        round_name="original",
        lots=tuple(blank_lots),
        total_contract_price=None,
        data_gap=(
            "No per-item detail BOQ was found for this bidder's original-round "
            "submission (only a lot-summary document, if anything, was "
            "available to extract). The item structure below is the "
            "ADDC-standard template, cloned from another bidder's submission "
            "for reference — every price needs manual entry before this "
            "bidder can be meaningfully compared."
        ),
    )


def _get_base_extractions(bidder_path: Path, bidder_name: str):
    """Raw parsed extraction, or a data-gap skeleton if nothing could be
    extracted at all but the bidder did submit an original-round folder."""
    raw = _get_raw_extractions(bidder_path, bidder_name)
    if raw:
        return raw
    skeleton = _build_gap_skeleton(bidder_path, bidder_name)
    return [skeleton] if skeleton else []


def _get_bidder_extractions(bidder_path: Path, bidder_name: str):
    """Base extraction (raw, or a data-gap skeleton) with any recorded user
    corrections/manual entries applied."""
    base = _get_base_extractions(bidder_path, bidder_name)
    return [apply_corrections(ext, bidder_name) for ext in base]


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
    """List bidders with an original-round submission.

    A bidder whose original round has no genuine per-item BOQ source (e.g.
    ELMEC, whose folder only contains a lot-summary document) is still
    listed — with `data_gap` set to an explanation — rather than silently
    excluded. The frontend surfaces it as needing manual entry instead of
    the bidder just disappearing without a trace.
    """
    power_dir = get_power_project_root()
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
        extractions = _get_bidder_extractions(d, d.name)
        if not extractions:
            continue
        bidders.append({"name": d.name, "data_gap": extractions[0].data_gap})
    return bidders


@router.get("/sample/extract/{bidder}")
async def extract_sample_bidder(bidder: str):
    """Extract the original-round submission for a sample bidder."""
    bidder_path = get_power_project_root() / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    extractions = _get_bidder_extractions(bidder_path, bidder)
    if not extractions:
        raise HTTPException(404, f"No original-round data found for '{bidder}'")

    return serialize_extraction(extractions[0])


def _get_sample_comparison() -> ComparisonResult:
    """Shared by /sample/compare and /sample/report/* — every bidder's
    original-round submission, compared as one round."""
    power_dir = get_power_project_root()
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

    return compare_round(original_extractions, "original")


@router.get("/sample/compare")
async def compare_sample_bidders():
    """Compare all sample bidders' original-round submissions."""
    return serialize_comparison(_get_sample_comparison())


class MatchOverrideRequest(BaseModel):
    lot_number: int
    bidder: str
    original_item_no: str
    canonical_item_no: str


class MatchOverrideKey(BaseModel):
    lot_number: int
    bidder: str
    original_item_no: str


@router.get("/sample/compare/match-overrides")
async def get_match_overrides():
    """Every manual match-fix currently recorded, across all lots."""
    return list_match_overrides()


@router.post("/sample/compare/match-override")
async def set_match_override(body: MatchOverrideRequest):
    """Manually re-point a bidder's item to the correct canonical row — the
    fail-safe for a 4-tier match (exact/normalized/fuzzy/LLM) that paired
    the wrong two items, or left a real match as 'unmatched'. Returns the
    comparison recomputed with the override applied, same as /correct does
    for extraction fixes."""
    record_match_override(body.lot_number, body.bidder, body.original_item_no, body.canonical_item_no)
    return serialize_comparison(_get_sample_comparison())


@router.post("/sample/compare/match-override/clear")
async def clear_match_override_route(body: MatchOverrideKey):
    """Discard a manual match fix and let automatic matching decide again."""
    clear_match_override(body.lot_number, body.bidder, body.original_item_no)
    return serialize_comparison(_get_sample_comparison())


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    lo, hi = min(values), max(values)
    med = statistics.median(values)
    return {
        "min": lo,
        "max": hi,
        "median": med,
        "spread_pct": ((hi - lo) / med) if med else None,
    }


@router.get("/sample/insights")
async def get_sample_insights():
    """Headline numbers for the insights dashboard — bidder ranking, price
    spread per lot, and flag counts by bidder/severity/category. Reuses the
    same digest the LLM recommendation report is built from (see
    reporting/digest.py) so the two views never disagree on the numbers."""
    result = _get_sample_comparison()
    digest = build_report_digest(result)

    lot_spread = []
    for lot in result.lots:
        totals = [
            t["total"] for b, t in lot.bidder_totals.items()
            if b not in digest["data_gap_bidders"] and t.get("total") is not None
        ]
        lot_spread.append({
            "lot_name": lot.lot_name,
            "lot_number": lot.lot_number,
            "spread": _spread(totals),
        })

    contract_totals = [t for t in digest["ranked_totals"] if t["rank"] is not None]
    contract_spread = _spread([t["grand_total"] for t in contract_totals])

    return {
        "tender_no": result.tender_no,
        "round_name": result.round_name,
        "ranked_totals": digest["ranked_totals"],
        "data_gap_bidders": digest["data_gap_bidders"],
        "flag_counts": digest["flag_counts"],
        "flag_summary": {
            "critical": len([f for f in result.flags if f.severity == "critical"]),
            "warning": len([f for f in result.flags if f.severity == "warning"]),
            "info": len([f for f in result.flags if f.severity == "info"]),
        },
        "contract_spread": contract_spread,
        "lot_spread": lot_spread,
        "flags": [
            {
                "severity": f.severity, "category": f.category, "bidder": f.bidder,
                "lot": f.lot, "item_no": f.item_no, "description": f.description, "detail": f.detail,
            }
            for f in result.flags
        ],
    }


@router.get("/sample/comparison/export.xlsx")
async def export_comparison_xlsx():
    """Plain consolidated comparison workbook — no AI narrative, every
    flag included. This is the artefact an analyst produces by hand today
    (feature 17), distinct from the AI recommendation report."""
    result = _get_sample_comparison()
    buf = build_comparison_excel(result)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="D-111808_comparison_report.xlsx"'},
    )


_round_trend_cache: dict[str, list] = {}


@router.get("/sample/rounds")
async def get_sample_round_trend():
    """Round-over-round price movement across original/round1/round2/round3
    for every bidder that has multi-round Excel data (features 14-15)."""
    power_dir = get_power_project_root()
    if not power_dir.exists():
        raise HTTPException(404, "No sample data found")

    bidder_round_extractions: dict[str, dict[str, BOQExtraction]] = {}
    for bidder_dir in sorted(power_dir.iterdir()):
        if not bidder_dir.is_dir():
            continue
        key = str(bidder_dir)
        if key not in _round_trend_cache:
            _round_trend_cache[key] = parse_bidder_folder_all_rounds(bidder_dir, bidder_dir.name)
        extractions = _round_trend_cache[key]
        if extractions:
            bidder_round_extractions[bidder_dir.name] = {e.round_name: e for e in extractions}

    if not bidder_round_extractions:
        raise HTTPException(404, "No round data found")

    trend = build_round_trend(bidder_round_extractions)
    return serialize_round_trend(trend)


@router.post("/sample/extract/{bidder}/correct")
async def correct_item(bidder: str, body: ItemCorrectionRequest):
    """Override one or more fields on a single extracted item.

    This is the fail-safe for OCR/parsing mistakes: a reviewer looking at
    the Explorer table can fix a garbled value here, and every downstream
    calculation (lot/contract totals, the Compare table, flag detection)
    picks up the corrected value on its next read — nothing needs to be
    re-extracted or re-run.
    """
    bidder_path = get_power_project_root() / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    base = _get_base_extractions(bidder_path, bidder)
    if not base:
        raise HTTPException(404, f"No original-round data found for '{bidder}'")

    raw_item = _find_raw_item(base[0], body.lot_number, body.sheet_name, body.item_no)
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
    bidder_path = get_power_project_root() / bidder
    if not bidder_path.exists():
        raise HTTPException(404, f"Bidder '{bidder}' not found")

    clear_correction(bidder, body.lot_number, body.sheet_name, body.item_no)
    corrected = _get_bidder_extractions(bidder_path, bidder)[0]
    return serialize_extraction(corrected)


@router.get("/sample/extract/{bidder}/corrections")
async def get_corrections(bidder: str):
    """List every correction currently applied to a bidder's data."""
    return list_corrections(bidder)


@router.get("/sample/extract/{bidder}/recommendations")
async def get_recommendations(bidder: str):
    """Peer-median suggested values for manually filling in a bidder with a
    data gap (see `BOQExtraction.data_gap`) — computed from every other
    bidder that has real pricing, excluding any other data-gap bidders
    (a skeleton has nothing real to offer as a peer value). Purely advisory:
    a reviewer can accept, adjust, or ignore these when correcting an item.
    """
    power_dir = get_power_project_root()
    if not power_dir.exists():
        raise HTTPException(404, "No sample data found")

    peer_extractions = {}
    for bidder_dir in sorted(power_dir.iterdir()):
        if not bidder_dir.is_dir() or bidder_dir.name == bidder:
            continue
        extractions = _get_bidder_extractions(bidder_dir, bidder_dir.name)
        if extractions and not extractions[0].data_gap:
            peer_extractions[bidder_dir.name] = extractions[0]

    if not peer_extractions:
        raise HTTPException(404, "No peer data available for recommendations")

    return compute_peer_recommendations(peer_extractions)


class ReportGenerateRequest(BaseModel):
    force: bool = False


# In-memory, per-round cache — same limitation as _raw_bidder_cache and the
# corrections store (lost on restart). digest_hash lets the frontend know a
# cached report is stale (data changed since it was generated) without
# forcing an automatic, potentially costly, re-call on every page load.
_report_cache: dict[str, dict] = {}  # round_name -> {"report", "generated_at", "digest_hash"}


def _digest_hash(result: ComparisonResult) -> str:
    digest = build_report_digest(result)
    return hashlib.sha256(json.dumps(digest, sort_keys=True, default=str).encode()).hexdigest()


@router.get("/sample/report/status")
async def get_report_status():
    """Whether a recommendation report is cached, and whether the LLM is
    even configured — lets the frontend show a clean 'not configured' state
    instead of letting the user click into a guaranteed failure."""
    llm_configured = bool(
        os.environ.get("AZURE_OPENAI_API_KEY")
        and os.environ.get("AZURE_OPENAI_ENDPOINT")
        and os.environ.get("AZURE_OPENAI_API_VERSION")
        and os.environ.get("AZURE_OPENAI_MODEL")
    )
    cached = _report_cache.get("original")
    stale = False
    if cached:
        result = _get_sample_comparison()
        stale = _digest_hash(result) != cached["digest_hash"]
    return {
        "cached": cached is not None,
        "generated_at": cached["generated_at"] if cached else None,
        "llm_configured": llm_configured,
        "stale": stale,
    }


@router.post("/sample/report/generate")
async def generate_report(body: ReportGenerateRequest):
    """Generate (or return the cached) LLM recommendation report for the
    original round. A paid LLM call only happens when there's no cached
    report, the underlying comparison has changed since it was cached, or
    the caller explicitly forces a regenerate — never on a plain reload."""
    result = _get_sample_comparison()
    digest_hash = _digest_hash(result)

    cached = _report_cache.get("original")
    if not body.force and cached and cached["digest_hash"] == digest_hash:
        return {
            "report": cached["report"],
            "generated_at": cached["generated_at"],
            "from_cache": True,
        }

    try:
        report = generate_recommendation_report(result)
    except ReportUnavailable as e:
        raise HTTPException(503, detail={"reason": e.reason, "message": e.message})

    generated_at = datetime.now(timezone.utc).isoformat()
    _report_cache["original"] = {
        "report": report,
        "generated_at": generated_at,
        "digest_hash": digest_hash,
    }
    return {"report": report, "generated_at": generated_at, "from_cache": False}


@router.get("/sample/report/export.xlsx")
async def export_report_xlsx():
    """Download the cached report as an Excel workbook. Never triggers LLM
    generation itself — generate first via POST /sample/report/generate."""
    cached = _report_cache.get("original")
    if not cached:
        raise HTTPException(404, "No report generated yet — generate one first")

    result = _get_sample_comparison()
    buf = build_excel_report(result, cached["report"])
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="D-111808_recommendation_report.xlsx"'},
    )


@router.get("/sample/report/export.html")
async def export_report_html():
    """Download the cached report as a standalone HTML document."""
    cached = _report_cache.get("original")
    if not cached:
        raise HTTPException(404, "No report generated yet — generate one first")

    result = _get_sample_comparison()
    html_str = build_html_report(result, cached["report"])
    return Response(
        content=html_str,
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="D-111808_recommendation_report.html"'},
    )
