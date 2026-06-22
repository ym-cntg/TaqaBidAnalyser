from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from src.config import BOQConfig
from src.models import (
    ExtractedBOQ,
    ExtractionMethod,
    LineItem,
    SectionData,
)


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().replace(",", "").replace(" ", "")
    if cleaned in ("", "-", "N/A", "n/a", "NA", "Nil", "nil", "INCLUDED", "Inc"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _looks_like_item_no(val: str) -> bool:
    """Check if a string looks like a BOQ item number (e.g., '1', '1.1', '4.2.3')."""
    return bool(re.match(r"^\d+(\.\d+)*$", val.strip()))


def extract_boq_from_pdf(
    file_path: Path,
    config: BOQConfig,
    bidder: str,
    round_name: str,
    lot: str,
) -> ExtractedBOQ:
    """Extract BOQ data from a digital PDF using PyMuPDF table detection."""
    doc = pymupdf.open(file_path)

    all_tables: list[list[list[str | None]]] = []

    for page in doc:
        tables = page.find_tables()
        for table in tables:
            extracted = table.extract()
            if extracted and len(extracted) > 1:
                all_tables.append(extracted)

    doc.close()

    sections = _parse_tables_to_sections(all_tables)

    return ExtractedBOQ(
        bidder=bidder,
        round=round_name,
        lot=lot,
        source_file=file_path,
        extraction_method=ExtractionMethod.PYMUPDF,
        sections=tuple(sections),
    )


def _parse_tables_to_sections(
    tables: list[list[list[str | None]]],
) -> list[SectionData]:
    """Parse extracted PDF tables into sections with line items.

    We detect the ADDC BOQ structure by looking for:
    - Header rows with 'Item', 'Description', 'Unit', etc.
    - Data rows with numeric item numbers
    """
    sections: list[SectionData] = []
    current_items: list[LineItem] = []
    current_section = "Main"

    for table in tables:
        col_map = _detect_columns(table)
        if col_map is None:
            continue

        for row in table:
            if len(row) < 3:
                continue

            item_val = _cell_str(row, col_map.get("item_no"))
            desc_val = _cell_str(row, col_map.get("description"))

            if not item_val and not desc_val:
                continue

            # Skip header rows
            if item_val.lower() in ("item", "item no", "item no."):
                continue
            if "total" in desc_val.lower() and "price" in desc_val.lower():
                continue

            if not _looks_like_item_no(item_val) and not desc_val:
                continue

            if not _looks_like_item_no(item_val):
                continue

            item = LineItem(
                item_no=item_val,
                description=desc_val,
                unit=_cell_str(row, col_map.get("unit")) or None,
                qty=_safe_float(_cell_str(row, col_map.get("qty"))),
                cif_unit_rate=_safe_float(_cell_str(row, col_map.get("cif_unit_rate"))),
                cif_total=_safe_float(_cell_str(row, col_map.get("cif_total"))),
                erection_unit_rate=_safe_float(
                    _cell_str(row, col_map.get("erection_unit_rate"))
                ),
                erection_total=_safe_float(
                    _cell_str(row, col_map.get("erection_total"))
                ),
                total_price=_safe_float(_cell_str(row, col_map.get("total_price"))),
            )
            current_items.append(item)

    if current_items:
        sections.append(SectionData(name=current_section, line_items=tuple(current_items)))

    return sections


def _detect_columns(table: list[list[str | None]]) -> dict[str, int] | None:
    """Detect column mapping from table header rows."""
    for row_idx, row in enumerate(table[:5]):  # Check first 5 rows for headers
        header_map = {}
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            cell_lower = cell.lower().strip()

            if cell_lower in ("item", "item no", "item no."):
                header_map["item_no"] = col_idx
            elif cell_lower == "description":
                header_map["description"] = col_idx
            elif cell_lower == "unit":
                header_map["unit"] = col_idx
            elif "qty" in cell_lower or "quantity" in cell_lower:
                header_map["qty"] = col_idx
            elif "cif" in cell_lower and "unit" in cell_lower:
                header_map["cif_unit_rate"] = col_idx
            elif "cif" in cell_lower and "total" in cell_lower:
                header_map["cif_total"] = col_idx
            elif "erection" in cell_lower and "unit" in cell_lower:
                header_map["erection_unit_rate"] = col_idx
            elif "erection" in cell_lower and "total" in cell_lower:
                header_map["erection_total"] = col_idx
            elif "total price" in cell_lower or cell_lower == "total":
                header_map["total_price"] = col_idx

        if "item_no" in header_map and "description" in header_map:
            # Also try to map columns by position if ADDC standard layout
            _fill_positional_columns(header_map, len(row))
            return header_map

    # Fallback: assume ADDC standard 9-column layout if table has enough columns
    if table and len(table[0]) >= 9:
        return {
            "item_no": 0,
            "description": 1,
            "unit": 2,
            "qty": 3,
            "cif_unit_rate": 4,
            "cif_total": 5,
            "erection_unit_rate": 6,
            "erection_total": 7,
            "total_price": 8,
        }

    return None


def _fill_positional_columns(header_map: dict[str, int], num_cols: int) -> None:
    """Fill missing column mappings based on ADDC standard positional layout."""
    if num_cols < 9:
        return

    defaults = {
        "item_no": 0,
        "description": 1,
        "unit": 2,
        "qty": 3,
        "cif_unit_rate": 4,
        "cif_total": 5,
        "erection_unit_rate": 6,
        "erection_total": 7,
        "total_price": 8,
    }
    for key, idx in defaults.items():
        if key not in header_map:
            header_map[key] = idx


def _cell_str(row: list[str | None], col_idx: int | None) -> str:
    if col_idx is None or col_idx >= len(row):
        return ""
    val = row[col_idx]
    return str(val).strip() if val is not None else ""


def estimate_confidence(extracted: ExtractedBOQ, config: BOQConfig) -> float:
    """Estimate extraction confidence (0.0 to 1.0).

    Higher confidence means:
    - Many line items extracted
    - Most have numeric pricing data
    - Item numbers look valid
    """
    items = extracted.all_line_items
    if not items:
        return 0.0

    total_items = len(items)

    # Check: how many items have at least one numeric price
    priced = sum(
        1 for item in items
        if any(v is not None for v in (
            item.cif_total, item.erection_total, item.total_price
        ))
    )

    # Check: how many have valid-looking item numbers
    valid_item_nos = sum(
        1 for item in items
        if _looks_like_item_no(item.item_no)
    )

    price_ratio = priced / total_items if total_items > 0 else 0
    item_no_ratio = valid_item_nos / total_items if total_items > 0 else 0

    # Expect at least 20 items for a typical BOQ section
    volume_score = min(total_items / 20, 1.0)

    return (price_ratio * 0.4 + item_no_ratio * 0.3 + volume_score * 0.3)
