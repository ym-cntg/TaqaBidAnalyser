"""Extract structured BOQ data from scanned PDFs using Azure Document Intelligence."""

import logging
import os
from pathlib import Path

import fitz

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from .excel_parser import BOQItem, BOQLot, BOQSheet

logger = logging.getLogger(__name__)


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


def _prepare_pdf_for_azure(filepath: Path) -> bytes:
    """Prepare PDF for Azure — filter to scanned/BOQ pages, skip cover letters.

    For fully scanned PDFs, skips early non-BOQ pages (cover letters, certificates)
    to reduce Azure processing cost and time.
    """
    doc = fitz.open(str(filepath))

    # Check if it's fully scanned (no text on most pages)
    sample_text = "".join(doc[i].get_text().strip() for i in range(min(5, doc.page_count)))
    is_scanned = len(sample_text) < 200

    if not is_scanned:
        # Digital PDF — send as-is
        doc.close()
        with open(filepath, "rb") as f:
            return f.read()

    # Scanned PDF — filter to pages with images (skip blank/cover pages)
    filtered = fitz.open()
    for i in range(doc.page_count):
        page = doc[i]
        images = page.get_images()
        if len(images) > 0:
            filtered.insert_pdf(doc, from_page=i, to_page=i)

    if filtered.page_count == 0:
        filtered.close()
        doc.close()
        with open(filepath, "rb") as f:
            return f.read()

    logger.info("Prepared %d/%d pages for Azure from %s", filtered.page_count, doc.page_count, filepath.name)
    pdf_bytes = filtered.tobytes()
    filtered.close()
    doc.close()
    return pdf_bytes


def _detect_lot_from_table_header(grid: list[list[str]]) -> list[tuple[str, int, int]]:
    """Detect lot columns in a summary table (all lots side by side).

    Returns list of (lot_name, lot_number, start_col_index).
    """
    if not grid:
        return []
    header = " ".join(cell for cell in grid[0])
    lots = []
    for col_idx, cell in enumerate(grid[0]):
        upper = cell.upper()
        if "LOT 1" in upper or "SHBPRY" in upper:
            lots.append(("Lot 1: Shobaisi PRY (SHBPRY)", 1, col_idx))
        elif "LOT-2" in upper or "LOT 2" in upper or "DRPRY" in upper:
            lots.append(("Lot 2: Defence Residence PRY (DRPRY)", 2, col_idx))
        elif "LOT 3" in upper or "SMHPRY" in upper:
            lots.append(("Lot 3: Samha PRY (SMHPRY)", 3, col_idx))
    return lots


def _is_detail_table(col_count: int) -> bool:
    """Detail BOQ tables have 9 columns (or 6 for spare parts)."""
    return col_count in (6, 7, 8, 9, 10)


def _is_summary_table(grid: list[list[str]]) -> bool:
    """Summary tables have lot names in the header row and 10+ columns."""
    if not grid or len(grid[0]) < 10:
        return False
    header_text = " ".join(grid[0]).upper()
    return "LOT" in header_text or "SHBPRY" in header_text or "DRPRY" in header_text


def _items_to_lot(items: list[BOQItem], lot_name: str, lot_number: int) -> BOQLot:
    """Build a BOQLot from a flat list of items, grouping into sheets."""
    sheets_dict: dict[str, list[BOQItem]] = {}
    current_sheet = "BOQ Items"
    for item in items:
        current_sheet = _classify_sheet(item.item_no, item.is_section_header, current_sheet)
        if current_sheet not in sheets_dict:
            sheets_dict[current_sheet] = []
        sheets_dict[current_sheet].append(item)

    sheets = tuple(
        BOQSheet(name=name, items=tuple(sheet_items))
        for name, sheet_items in sheets_dict.items()
        if sheet_items
    )

    total_cif = sum(
        item.cif_total or 0 for sheet in sheets
        for item in sheet.items if not item.is_section_header
    )
    total_erection = sum(
        item.erection_total or 0 for sheet in sheets
        for item in sheet.items if not item.is_section_header
    )

    return BOQLot(
        lot_name=lot_name,
        lot_number=lot_number,
        sheets=sheets,
        total_cif=total_cif if total_cif > 0 else None,
        total_erection=total_erection if total_erection > 0 else None,
        total_price=(total_cif + total_erection) if total_cif and total_erection else total_cif or total_erection,
    )


def _detect_lot_boundaries(items: list[BOQItem]) -> dict[int, list[BOQItem]]:
    """Split a flat list of items into lots by detecting item number resets.

    When item numbers restart (e.g., after 9.x we see 1.x again), it's a new lot.
    """
    if not items:
        return {}

    lots: dict[int, list[BOQItem]] = {}
    current_lot = 1
    lots[current_lot] = []
    seen_high_section = False

    for item in items:
        if item.is_section_header and item.item_no in ("1", "2", "3"):
            if seen_high_section:
                # Item numbers reset — new lot
                current_lot += 1
                lots[current_lot] = []
                seen_high_section = False
        if item.is_section_header and item.item_no in ("5", "6", "7", "8", "9"):
            seen_high_section = True
        lots.setdefault(current_lot, []).append(item)

    return lots


LOT_NAMES = {
    1: "Lot 1: Shobaisi PRY (SHBPRY)",
    2: "Lot 2: Defence Residence PRY (DRPRY)",
    3: "Lot 3: Samha PRY (SMHPRY)",
}


def parse_scanned_boq(filepath: str | Path) -> list[BOQLot]:
    """Parse a scanned BOQ PDF using Azure Document Intelligence.

    Returns multiple BOQLots if the PDF contains data for multiple lots.
    """
    filepath = Path(filepath)
    client = _get_client()

    pdf_bytes = _prepare_pdf_for_azure(filepath)
    logger.info("Sending %s (%.1fMB) to Azure Document Intelligence...",
                filepath.name, len(pdf_bytes) / 1024 / 1024)

    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=pdf_bytes),
    )
    result = poller.result()
    logger.info("Azure returned %d tables, %d chars of text",
                len(result.tables or []), len(result.content or ""))

    # Parse all detail tables into items
    all_items: list[BOQItem] = []

    for table in (result.tables or []):
        row_count = table.row_count
        col_count = table.column_count
        grid: list[list[str]] = [[""] * col_count for _ in range(row_count)]
        for cell in table.cells:
            grid[cell.row_index][cell.column_index] = cell.content or ""

        # Skip summary tables (all lots side by side)
        if _is_summary_table(grid):
            continue

        # Skip tables with too few or too many columns
        if not _is_detail_table(col_count):
            continue

        for row_idx in range(1, row_count):
            item = _parse_azure_table_row(grid[row_idx], col_count)
            if item is not None:
                all_items.append(item)

    if not all_items:
        raise ValueError(
            "Azure Document Intelligence could not extract any BOQ items "
            "from this PDF. The document may not contain recognizable table structures."
        )

    # Detect lot boundaries from item number resets
    lot_items = _detect_lot_boundaries(all_items)

    lots = []
    for lot_num, items in sorted(lot_items.items()):
        lot_name = LOT_NAMES.get(lot_num, f"Lot {lot_num}")
        lots.append(_items_to_lot(items, lot_name, lot_num))

    logger.info("Extracted %d lots with %d total items from %s",
                len(lots), len(all_items), filepath.name)
    return lots
