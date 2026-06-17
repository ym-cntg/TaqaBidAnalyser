"""Extract structured BOQ data from PDF files using PyMuPDF."""

from pathlib import Path

import fitz

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


def _detect_lot_from_text(text: str) -> tuple[str, int]:
    upper = text.upper()
    if "LOT 1" in upper or "SHBPRY" in upper:
        return "Lot 1: Shobaisi PRY (SHBPRY)", 1
    if "LOT 2" in upper or "LOT-2" in upper or "DRPRY" in upper:
        return "Lot 2: Defence Residence PRY (DRPRY)", 2
    if "LOT 3" in upper or "SMHPRY" in upper:
        return "Lot 3: Samha PRY (SMHPRY)", 3
    return "Unknown Lot", 0


def _parse_table_row(row: list[str], col_count: int) -> BOQItem | None:
    """Parse a single table row into a BOQItem."""
    if not row or all(not v or v.strip() == "" for v in row):
        return None

    item_no = row[0].strip() if row[0] else ""
    desc = row[1].strip() if len(row) > 1 and row[1] else ""

    # Skip header/meta rows
    if item_no.lower() in ("item", "nan", "") and desc.lower() in (
        "description", "nan", "", "unit rate (b)", "total (a*b)"
    ):
        return None
    if "a + b" in desc.lower() or "unit rate" in desc.lower():
        return None
    if "technical specifications" in desc.lower():
        return None
    if "total price" in desc.lower() or "sub total" in desc.lower():
        return None

    if col_count >= 9:
        unit = row[2].strip() if len(row) > 2 and row[2] else None
        qty = _safe_float(row[3]) if len(row) > 3 else None
        cif_rate = _safe_float(row[4]) if len(row) > 4 else None
        cif_total = _safe_float(row[5]) if len(row) > 5 else None
        erect_rate = _safe_float(row[6]) if len(row) > 6 else None
        erect_total = _safe_float(row[7]) if len(row) > 7 else None
        total = _safe_float(row[8]) if len(row) > 8 else None
        raw_cif = row[4].strip() if len(row) > 4 and row[4] else None
        raw_erect = row[6].strip() if len(row) > 6 and row[6] else None
    elif col_count >= 6:
        unit = row[2].strip() if len(row) > 2 and row[2] else None
        qty = _safe_float(row[3]) if len(row) > 3 else None
        cif_rate = _safe_float(row[4]) if len(row) > 4 else None
        cif_total = _safe_float(row[5]) if len(row) > 5 else None
        erect_rate = None
        erect_total = None
        total = cif_total
        raw_cif = row[4].strip() if len(row) > 4 and row[4] else None
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


def parse_pdf_boq(filepath: str | Path) -> BOQLot:
    """Parse a BOQ PDF file into structured data using PyMuPDF table extraction."""
    doc = fitz.open(str(filepath))
    all_items: list[BOQItem] = []
    lot_name = "Unknown Lot"
    lot_number = 0

    # Detect lot from first page
    if doc.page_count > 0:
        first_text = doc[0].get_text()
        lot_name, lot_number = _detect_lot_from_text(first_text)

    current_sheet_name = "BOQ Items"
    sheets_dict: dict[str, list[BOQItem]] = {}

    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        tables = page.find_tables()

        for table in tables.tables:
            rows = table.extract()
            if not rows:
                continue

            col_count = len(rows[0]) if rows else 0

            for row in rows:
                item = _parse_table_row(row, col_count)
                if item is not None:
                    # Detect sheet transitions based on major item numbers
                    if item.item_no in ("1", "2", "3") and item.is_section_header:
                        current_sheet_name = "Items 1,2,3-Construction Works"
                    elif item.item_no == "4" and item.is_section_header:
                        current_sheet_name = "Items 4-Load Diversion Works"
                    elif item.item_no in ("5", "6", "7", "8") and item.is_section_header:
                        current_sheet_name = "Items 5-8 Dismantl & Modif work"
                    elif item.item_no == "9" and item.is_section_header:
                        current_sheet_name = "Items 9- Spare Parts (Optional)"

                    if current_sheet_name not in sheets_dict:
                        sheets_dict[current_sheet_name] = []
                    sheets_dict[current_sheet_name].append(item)

    if not sheets_dict:
        # No tables found — likely a scanned PDF, try OCR
        from .ocr_parser import parse_scanned_boq
        return parse_scanned_boq(filepath)

    sheets = tuple(
        BOQSheet(name=name, items=tuple(items))
        for name, items in sheets_dict.items()
        if items
    )

    # Calculate totals from items
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
