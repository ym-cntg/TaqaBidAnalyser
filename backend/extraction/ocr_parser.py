"""Extract structured BOQ data from scanned PDFs using Azure Document Intelligence."""

import os
import tempfile
from pathlib import Path

import fitz

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from .excel_parser import BOQItem, BOQLot, BOQSheet


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    cleaned = val.strip().replace(",", "").replace(" ", "").replace("\n", "")
    if cleaned in ("", "-", "N/A", "Included", "n/a", "NaN"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _get_client() -> DocumentIntelligenceClient:
    endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    if not endpoint or not key:
        raise ValueError(
            "Azure Document Intelligence credentials not configured. "
            "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY "
            "in your .env file."
        )
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )


def _detect_lot_from_text(text: str) -> tuple[str, int]:
    upper = text.upper()
    if "LOT 1" in upper or "SHBPRY" in upper:
        return "Lot 1: Shobaisi PRY (SHBPRY)", 1
    if "LOT 2" in upper or "LOT-2" in upper or "DRPRY" in upper:
        return "Lot 2: Defence Residence PRY (DRPRY)", 2
    if "LOT 3" in upper or "SMHPRY" in upper:
        return "Lot 3: Samha PRY (SMHPRY)", 3
    return "Unknown Lot", 0


def _classify_sheet(item_no: str, is_header: bool, current: str) -> str:
    """Determine which BOQ sheet section an item belongs to."""
    if not is_header:
        return current
    if item_no in ("1", "2", "3"):
        return "Items 1,2,3-Construction Works"
    if item_no == "4":
        return "Items 4-Load Diversion Works"
    if item_no in ("5", "6", "7", "8"):
        return "Items 5-8 Dismantl & Modif work"
    if item_no == "9":
        return "Items 9- Spare Parts (Optional)"
    return current


def _parse_azure_table_row(cells: list[str], col_count: int) -> BOQItem | None:
    """Parse a row of cell values into a BOQItem."""
    if not cells or all(not c or c.strip() == "" for c in cells):
        return None

    item_no = cells[0].strip() if cells[0] else ""
    desc = cells[1].strip() if len(cells) > 1 and cells[1] else ""

    # Skip header/meta rows
    lower_item = item_no.lower()
    lower_desc = desc.lower()
    if lower_item in ("item", "nan", "") and lower_desc in (
        "description", "nan", "", "unit rate (b)", "total (a*b)",
    ):
        return None
    if "a + b" in lower_desc or "unit rate" in lower_desc:
        return None
    if "technical specifications" in lower_desc:
        return None
    if "total price" in lower_desc or "sub total" in lower_desc:
        return None
    if "total contract" in lower_desc:
        return None

    if col_count >= 9:
        unit = cells[2].strip() if len(cells) > 2 and cells[2] else None
        qty = _safe_float(cells[3]) if len(cells) > 3 else None
        cif_rate = _safe_float(cells[4]) if len(cells) > 4 else None
        cif_total = _safe_float(cells[5]) if len(cells) > 5 else None
        erect_rate = _safe_float(cells[6]) if len(cells) > 6 else None
        erect_total = _safe_float(cells[7]) if len(cells) > 7 else None
        total = _safe_float(cells[8]) if len(cells) > 8 else None
        raw_cif = cells[4].strip() if len(cells) > 4 and cells[4] else None
        raw_erect = cells[6].strip() if len(cells) > 6 and cells[6] else None
    elif col_count >= 6:
        unit = cells[2].strip() if len(cells) > 2 and cells[2] else None
        qty = _safe_float(cells[3]) if len(cells) > 3 else None
        cif_rate = _safe_float(cells[4]) if len(cells) > 4 else None
        cif_total = _safe_float(cells[5]) if len(cells) > 5 else None
        erect_rate = None
        erect_total = None
        total = cif_total
        raw_cif = cells[4].strip() if len(cells) > 4 and cells[4] else None
        raw_erect = None
    else:
        return None

    is_header = (
        item_no != ""
        and desc != ""
        and unit is None
        and qty is None
        and cif_rate is None
    )

    if not item_no and not desc:
        return None

    return BOQItem(
        item_no=item_no,
        description=desc,
        unit=unit,
        qty=qty,
        cif_unit_rate=cif_rate,
        cif_total=cif_total,
        erection_unit_rate=erect_rate,
        erection_total=erect_total,
        total=total,
        is_section_header=is_header,
        raw_cif=raw_cif,
        raw_erection=raw_erect,
    )


def _extract_scanned_pages(filepath: Path) -> bytes:
    """Extract only scanned pages (images, no text) into a smaller PDF.

    This avoids sending 100+ pages to Azure when only ~80 are actual scanned BOQ.
    """
    doc = fitz.open(str(filepath))
    scanned_doc = fitz.open()

    # Skip early pages (cover letters, certificates) — BOQ tables start later
    START_PAGE = 14  # 0-indexed, so page 15 in the PDF
    for i in range(START_PAGE, doc.page_count):
        page = doc[i]
        text = page.get_text().strip()
        images = page.get_images()
        # A scanned page has images but very little or no extractable text
        if len(images) > 0 and len(text) < 50:
            scanned_doc.insert_pdf(doc, from_page=i, to_page=i)

    # Cap pages for demo — enough to show capability without long wait
    MAX_OCR_PAGES = 5
    if scanned_doc.page_count > MAX_OCR_PAGES:
        trimmed = fitz.open()
        trimmed.insert_pdf(scanned_doc, from_page=0, to_page=MAX_OCR_PAGES - 1)
        scanned_doc.close()
        scanned_doc = trimmed

    if scanned_doc.page_count == 0:
        # Fallback: send the whole PDF
        scanned_doc.close()
        with open(filepath, "rb") as f:
            return f.read()

    pdf_bytes = scanned_doc.tobytes()
    scanned_doc.close()
    doc.close()
    return pdf_bytes


def parse_scanned_boq(filepath: str | Path) -> BOQLot:
    """Parse a scanned BOQ PDF using Azure Document Intelligence.

    Uses the prebuilt-layout model which extracts tables from document images.
    Filters to scanned-only pages first to reduce processing time.
    """
    filepath = Path(filepath)
    client = _get_client()

    pdf_bytes = _extract_scanned_pages(filepath)

    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=pdf_bytes),
    )

    result = poller.result()

    # Collect lot info from extracted text
    lot_name = "Unknown Lot"
    lot_number = 0
    if result.content:
        lot_name, lot_number = _detect_lot_from_text(result.content[:3000])

    # Parse tables into BOQItems
    sheets_dict: dict[str, list[BOQItem]] = {}
    current_sheet = "BOQ Items"

    for table in (result.tables or []):
        # Build a 2D grid from Azure's cell data
        row_count = table.row_count
        col_count = table.column_count
        grid: list[list[str]] = [[""] * col_count for _ in range(row_count)]

        for cell in table.cells:
            grid[cell.row_index][cell.column_index] = cell.content or ""

        # Parse each row (skip header row at index 0)
        for row_idx in range(1, row_count):
            row = grid[row_idx]
            item = _parse_azure_table_row(row, col_count)
            if item is None:
                continue

            current_sheet = _classify_sheet(
                item.item_no, item.is_section_header, current_sheet,
            )
            if current_sheet not in sheets_dict:
                sheets_dict[current_sheet] = []
            sheets_dict[current_sheet].append(item)

    if not sheets_dict:
        raise ValueError(
            "Azure Document Intelligence could not extract any BOQ tables "
            "from this PDF. The document may not contain recognizable table structures."
        )

    sheets = tuple(
        BOQSheet(name=name, items=tuple(items))
        for name, items in sheets_dict.items()
        if items
    )

    total_cif = sum(
        item.cif_total or 0
        for sheet in sheets
        for item in sheet.items
        if not item.is_section_header
    )
    total_erection = sum(
        item.erection_total or 0
        for sheet in sheets
        for item in sheet.items
        if not item.is_section_header
    )

    return BOQLot(
        lot_name=lot_name,
        lot_number=lot_number,
        sheets=sheets,
        total_cif=total_cif if total_cif > 0 else None,
        total_erection=total_erection if total_erection > 0 else None,
        total_price=(total_cif + total_erection) if total_cif and total_erection else None,
    )
