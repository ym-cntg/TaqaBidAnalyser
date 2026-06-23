"""Unified extraction router: PDF (PyMuPDF -> Azure fallback) -> Excel fallback.

This is the single entry point for extracting BOQ data from a bidder's folder.
It decides which parser to use based on available files and extraction quality.
"""

import logging
from pathlib import Path

from .cache import load_cached, save_cached
from .excel_parser import BOQExtraction, BOQItem, BOQLot, parse_bidder_folder as _parse_excel_bidder
from .ocr_parser import _detect_lot_boundaries, _items_to_lot, LOT_NAMES
from .pdf_parser import parse_pdf_boq

logger = logging.getLogger(__name__)


def _detect_lot_from_filename(filename: str) -> tuple[str, int]:
    """Detect lot from filename — most reliable for per-lot PDF files."""
    upper = filename.upper()
    if "LOT 1" in upper or "LOT-1" in upper or "SHBPRY" in upper:
        # Only match SHBPRY if it's not in a title that mentions all lots
        if "DRPRY" not in upper and "SMHPRY" not in upper:
            return "Lot 1: Shobaisi PRY (SHBPRY)", 1
        if "LOT 1" in upper or "LOT-1" in upper:
            return "Lot 1: Shobaisi PRY (SHBPRY)", 1
    if "LOT 2" in upper or "LOT-2" in upper or "DRPRY" in upper:
        return "Lot 2: Defence Residence PRY (DRPRY)", 2
    if "LOT 3" in upper or "LOT-3" in upper or "SMHPRY" in upper:
        return "Lot 3: Samha PRY (SMHPRY)", 3
    return "Unknown Lot", 0


def _extract_pdf_pymupdf(pdf_path: Path) -> list[BOQLot]:
    """Try PyMuPDF extraction. Returns empty list if no tables found."""
    lot = parse_pdf_boq(pdf_path)
    if lot is None:
        return []
    # Check if extraction has meaningful data (not just headers)
    non_header_items = sum(
        1 for sheet in lot.sheets
        for item in sheet.items
        if not item.is_section_header and item.total is not None
    )
    if non_header_items < 3:
        logger.info("PyMuPDF found only %d priced items in %s — insufficient", non_header_items, pdf_path.name)
        return []

    # Fix lot detection using filename (more reliable than first-page text)
    fname_lot_name, fname_lot_num = _detect_lot_from_filename(pdf_path.name)

    if fname_lot_num != 0:
        # Single-lot PDF — apply filename-based lot number
        if lot.lot_number != fname_lot_num:
            lot = BOQLot(
                lot_name=fname_lot_name,
                lot_number=fname_lot_num,
                sheets=lot.sheets,
                total_cif=lot.total_cif,
                total_erection=lot.total_erection,
                total_price=lot.total_price,
            )
        return [lot]

    # Multi-lot PDF (filename mentions all lots or is generic)
    # Try splitting by detecting item number resets
    all_items: list[BOQItem] = []
    for sheet in lot.sheets:
        all_items.extend(sheet.items)

    lot_items = _detect_lot_boundaries(all_items)
    if len(lot_items) > 1:
        lots = []
        for lot_num, items in sorted(lot_items.items()):
            lot_name = LOT_NAMES.get(lot_num, f"Lot {lot_num}")
            lots.append(_items_to_lot(items, lot_name, lot_num))
        logger.info("Split multi-lot PDF %s into %d lots", pdf_path.name, len(lots))
        return lots

    # Could not split — return as-is with lot_number=0
    return [lot]


def _extract_pdf_azure(pdf_path: Path) -> list[BOQLot]:
    """Use Azure Document Intelligence. Returns empty list on failure."""
    try:
        from .ocr_parser import parse_scanned_boq
        return parse_scanned_boq(pdf_path)
    except ValueError as e:
        logger.warning("Azure extraction failed for %s: %s", pdf_path.name, e)
        return []
    except Exception as e:
        logger.error("Azure extraction error for %s: %s", pdf_path.name, e)
        return []


def extract_pdf(pdf_path: Path) -> list[BOQLot]:
    """Extract BOQ data from a PDF file using best available method.

    Strategy:
    1. Check cache (content-hash based)
    2. Try PyMuPDF (free, fast)
    3. Fall back to Azure Document Intelligence (paid, handles scanned)
    4. Cache the result
    """
    # Check cache first
    cached = load_cached(pdf_path)
    if cached is not None:
        return cached

    # Try PyMuPDF
    lots = _extract_pdf_pymupdf(pdf_path)
    if lots:
        logger.info("PyMuPDF extracted %d lots from %s", len(lots), pdf_path.name)
        save_cached(pdf_path, lots)
        return lots

    # Fall back to Azure
    logger.info("PyMuPDF failed for %s — trying Azure Document Intelligence", pdf_path.name)
    lots = _extract_pdf_azure(pdf_path)
    if lots:
        save_cached(pdf_path, lots)
        return lots

    logger.warning("All extraction methods failed for %s", pdf_path.name)
    return []


def parse_bidder_folder_pdf(bidder_path: Path, bidder_name: str) -> list[BOQExtraction]:
    """Parse all rounds for a bidder, preferring PDF extraction over Excel.

    For each round:
    1. If PDFs exist → extract from PDFs (PyMuPDF → Azure fallback)
    2. If no PDFs or extraction failed → fall back to Excel
    """
    extractions = []

    round_dirs = sorted(
        [d for d in bidder_path.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    for round_dir in round_dirs:
        round_name = round_dir.name
        pdf_dir = round_dir / "pdf"
        excel_dir = round_dir / "excel"

        lots: list[BOQLot] = []
        total_contract_price = None

        # Try PDF extraction first
        if pdf_dir.exists():
            pdf_files = sorted(pdf_dir.glob("*.pdf"))
            # Filter out cover letters, summaries, and non-BOQ files
            boq_pdfs = []
            for f in pdf_files:
                lower = f.name.lower()
                # Skip obvious non-BOQ files
                skip_exact = ("cover", "letter", "certificate", "icvmatch",
                              "company profile", "manpower", "trade license",
                              "financial statement", "financial_", "organization",
                              "cv ", "approval", "experience", "running projects",
                              "bidder_overview", "overview_", "hse award",
                              "icv certificate")
                if any(skip in lower for skip in skip_exact):
                    logger.debug("Skipping non-BOQ file: %s", f.name)
                    continue
                # Skip "summary" only if it doesn't also contain "boq" or "lot"
                if "summary" in lower and "boq" not in lower and "lot" not in lower:
                    logger.debug("Skipping summary file: %s", f.name)
                    continue
                boq_pdfs.append(f)

            for pdf_file in boq_pdfs:
                pdf_lots = extract_pdf(pdf_file)
                for lot in pdf_lots:
                    # Avoid duplicate lots (same lot_number from different files)
                    existing_nums = {l.lot_number for l in lots}
                    if lot.lot_number not in existing_nums or lot.lot_number == 0:
                        lots.append(lot)

        # Fall back to Excel if PDF extraction produced nothing usable
        # Also fall back if we got unsplit multi-lot data and Excel exists
        has_only_unknown_lots = lots and all(l.lot_number == 0 for l in lots)
        # Detect likely unsplit multi-lot: single lot with excessive items (>500)
        has_oversized_lot = (
            len(lots) == 1
            and sum(len(s.items) for lot in lots for s in lot.sheets) > 500
        )
        needs_fallback = not lots or has_only_unknown_lots or has_oversized_lot
        if needs_fallback and excel_dir.exists() and list(excel_dir.glob("*.xlsx")):
            if has_only_unknown_lots or has_oversized_lot:
                logger.info("PDF produced unsplit multi-lot data for %s/%s — falling back to Excel", bidder_name, round_name)
            else:
                logger.info("Falling back to Excel for %s/%s", bidder_name, round_name)
            excel_extractions = _parse_excel_bidder(bidder_path, bidder_name)
            for ext in excel_extractions:
                if ext.round_name == round_name:
                    extractions.append(ext)
            continue

        if lots:
            lots.sort(key=lambda l: l.lot_number)

            # Sum lot totals for contract price
            lot_totals = [l.total_price for l in lots if l.total_price is not None]
            if lot_totals:
                total_contract_price = sum(lot_totals)

            extractions.append(
                BOQExtraction(
                    tender_no="D-111808",
                    bidder=bidder_name,
                    round_name=round_name,
                    lots=tuple(lots),
                    total_contract_price=total_contract_price,
                )
            )

    return extractions
