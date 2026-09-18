"""Detect and extract BOQ line items from an arbitrary vendor workbook.

Built against the two real layouts in this repo's sample data, which
differ enough that hardcoding either one would fail on the other:

  ADDC power template  Item | Description | Unit | Est Qty | CIF Unit
                       Rate | CIF Total | Erection Unit Rate | Erection
                       Total | Total Price, under a two-row merged
                       header (the group label on one row, "Unit Rate"/
                       "Total" on the next).
  Water template       Sl.No | Description | UNIT | Quantity | Unit Rate
                       | Total Line Costs, under a single header row.

So nothing here keys off a fixed row or column number. The header row is
found by scoring, columns are mapped by keyword, and anything that does
not look like a BOQ (cover pages, summary sheets) is skipped and
reported rather than parsed into noise.
"""

from __future__ import annotations

import re
from typing import Any

import openpyxl

from backend.excel_boq.models import (
    BoqDocument,
    BoqLine,
    BoqSheet,
    ColumnMap,
    SkippedSheet,
)

# How far into a sheet to look for the header. Real files put it as low
# as row 6 (water) after a block of title rows; 20 is generous margin.
HEADER_SEARCH_ROWS = 20
# Relative tolerance for the qty * rate == total check. Vendor sheets
# carry full float precision (a real line reads 4147.346075159003), so
# an exact comparison would flag almost everything.
ARITHMETIC_TOLERANCE = 0.01

_ITEM_NO_PATTERN = re.compile(r"^\d+(\.\d+)*[a-z]?$", re.IGNORECASE)
# Rows that restate other rows. Counting these as line items is the
# single easiest way to silently double the contract value, so they get
# their own kind and are excluded from every total.
_TOTAL_PATTERN = re.compile(
    r"^(sub[\s-]*total|grand[\s-]*total|total\b)|\b(sub[\s-]*total|grand[\s-]*total)\b",
    re.IGNORECASE,
)
# Gaps the ADDC template leaves where an item was withdrawn.
_PLACEHOLDER_PATTERN = re.compile(r"^no\s+boq\s+item$", re.IGNORECASE)
# A whole cell that is a number, optionally with a currency prefix and
# thousands separators. Anchored, so prose never matches.
_NUMERIC_TEXT_PATTERN = re.compile(
    r"\s*(?:aed|usd|\$)?\s*([-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|[-+]?\d*\.?\d+)\s*",
    re.IGNORECASE,
)
# A heading is a short label; a paragraph in the description column is
# specification narrative that happens to sit on a numbered row.
MAX_SECTION_DESCRIPTION = 150


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _resolve_merged(ws) -> dict[tuple[int, int], Any]:
    """Map every cell inside a merged range to that range's value.

    openpyxl returns the value only in a merged range's top-left cell and
    None everywhere else, which is exactly what breaks the power
    template's two-row header ("CIF / Local (AED) - A" spans two columns,
    so the second column reads as None).
    """
    filled: dict[tuple[int, int], Any] = {}
    for rng in ws.merged_cells.ranges:
        anchor = ws.cell(row=rng.min_row, column=rng.min_col).value
        if anchor is None:
            continue
        for row in range(rng.min_row, rng.max_row + 1):
            for col in range(rng.min_col, rng.max_col + 1):
                filled[(row, col)] = anchor
    return filled


def _row_values(ws, row: int, merged: dict[tuple[int, int], Any], width: int) -> list[Any]:
    out = []
    for col in range(1, width + 1):
        value = ws.cell(row=row, column=col).value
        if value is None:
            value = merged.get((row, col))
        out.append(value)
    return out


_HEADER_HINTS = (
    "description",
    "unit",
    "qty",
    "quantity",
    "rate",
    "total",
    "amount",
    "item",
    "sl.no",
    "sl no",
)


def _score_header_row(values: list[Any]) -> int:
    text = " ".join(_norm(v) for v in values)
    if not text.strip():
        return 0
    score = sum(1 for hint in _HEADER_HINTS if hint in text)
    # A header row is labels, not data. A row carrying several numbers is
    # a priced line that happens to mention "total", not the header.
    if sum(1 for v in values if _is_number(v)) >= 3:
        score -= 3
    return score


def find_header_row(ws, merged: dict[tuple[int, int], Any], width: int) -> int | None:
    best_row, best_score = None, 0
    for row in range(1, min(HEADER_SEARCH_ROWS, ws.max_row) + 1):
        score = _score_header_row(_row_values(ws, row, merged, width))
        if score > best_score:
            best_row, best_score = row, score
    # Two hints is the floor: "description" plus any one money/qty label.
    # Below that it is a title block, not a table.
    return best_row if best_score >= 2 else None


def _is_band_row(values: list[Any]) -> bool:
    """True if this row looks like part of the header band.

    Two guards matter. A row with numbers is data, not a label. And a
    full-width title banner ("ABU DHABI DISTRIBUTION COMPANY", merged
    across every column) resolves to the same single value in every
    column, so requiring at least two distinct labels excludes it while
    keeping a real header row.
    """
    if any(_is_number(v) for v in values):
        return False
    distinct = {_norm(v) for v in values if _norm(v)}
    return len(distinct) >= 2


def _combined_headers(
    ws, header_row: int, merged: dict[tuple[int, int], Any], width: int
) -> list[str]:
    """Fold a multi-row header band into one label per column.

    The ADDC power template needs this: its group labels ("CIF / Local
    (AED) - A", "Erection (AED) - B") sit one row above the "Unit Rate"/
    "Total" sub-labels and are merged across two columns each, while the
    Item/Description/Unit/Qty columns are merged vertically down through
    both rows. Scoring therefore picks the lower row, and reading only
    that row would collapse two different "Unit Rate" columns into one,
    silently losing the CIF-vs-Erection split that the whole comparison
    depends on. So the band is expanded outward from the scored row and
    every layer is concatenated per column.
    """
    top = header_row
    while top - 1 >= 1 and header_row - (top - 1) < 3:
        if not _is_band_row(_row_values(ws, top - 1, merged, width)):
            break
        top -= 1

    bottom = header_row
    while bottom + 1 <= ws.max_row and (bottom + 1) - header_row < 2:
        candidate = _row_values(ws, bottom + 1, merged, width)
        if not _is_band_row(candidate):
            break
        if not any(
            text and ("rate" in text or "total" in text)
            for text in (_norm(v) for v in candidate)
        ):
            break
        bottom += 1

    labels = []
    for col in range(width):
        parts: list[str] = []
        for row in range(top, bottom + 1):
            text = _norm(_row_values(ws, row, merged, width)[col])
            # Vertically merged cells repeat their value down the band;
            # only keep each distinct layer once.
            if text and text not in parts:
                parts.append(text)
        labels.append(" ".join(parts))
    return labels, top, bottom


def _classify_header(label: str) -> str | None:
    """Map one combined header label to a canonical column name."""
    if not label:
        return None

    is_rate = "rate" in label
    is_total = "total" in label or "amount" in label
    is_cif = "cif" in label or "local" in label
    is_erection = "erection" in label or "installation" in label

    if is_cif and is_rate:
        return "cif_unit_rate"
    if is_cif and is_total:
        return "cif_total"
    if is_erection and is_rate:
        return "erection_unit_rate"
    if is_erection and is_total:
        return "erection_total"

    if "description" in label or "particular" in label:
        return "description"
    if any(key in label for key in ("sl.no", "sl no", "s.no", "item no", "item")) and not (
        is_rate or is_total
    ):
        return "item_no"
    if ("qty" in label or "quantity" in label) and not is_rate:
        return "quantity"
    # Checked after the rate branches so "unit rate" never lands here.
    if "unit" in label and not is_rate and not is_total:
        return "unit"
    if is_rate:
        return "unit_rate"
    if is_total:
        return "line_total"
    return None


def build_column_map(labels: list[str]) -> tuple[ColumnMap, str, str]:
    column_map = ColumnMap()
    for index, label in enumerate(labels):
        field = _classify_header(label)
        # First match wins: vendor sheets frequently repeat a "Total"
        # label in a trailing notes/VAT column, and the leftmost one is
        # the real data column.
        if field and getattr(column_map, field) is None:
            setattr(column_map, field, index)

    if column_map.cif_unit_rate is not None or column_map.erection_unit_rate is not None:
        layout = "power"
    elif column_map.unit_rate is not None:
        layout = "water"
    else:
        layout = "generic"

    # A rollup sheet lists other sheets' totals and has no quantities to
    # price against; a real BOQ sheet always has a quantity column. That
    # single difference separates "Final Summary" / "Project Summary"
    # from the priced bills in every sample file, and keeps summary
    # figures out of the document total.
    role = "boq" if column_map.quantity is not None else "summary"
    return column_map, layout, role


def _cell(row: list[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def _number(row: list[Any], index: int | None) -> tuple[float | None, str | None]:
    """Return (number, leftover_text). A priced BOQ routinely carries a
    cross-reference like "included in BOQ item 1.1" in a money column;
    that is a real commercial statement, not a zero, so it is kept as
    text instead of being coerced."""
    value = _cell(row, index)
    if value is None:
        return None, None
    if _is_number(value):
        return float(value), None
    text = str(value).strip()
    if not text:
        return None, None
    # Tolerate a number written as text ("1,234.50", "AED 1,234.50"),
    # but only when the whole cell is that number. Stripping letters
    # indiscriminately would turn the real cross-reference "Included in
    # BOQ item 3.3" into a unit rate of 3.3, inventing a price that the
    # vendor never quoted.
    match = _NUMERIC_TEXT_PATTERN.fullmatch(text)
    if match:
        try:
            return float(match.group(1).replace(",", "")), None
        except ValueError:
            return None, text
    return None, text


def _check_arithmetic(line: BoqLine) -> str | None:
    """Flag qty * unit rate != stated total, one of the manual checks
    this tool exists to replace."""
    for rate, total, label in (
        (line.unit_rate, line.line_total, "unit rate"),
        (line.cif_unit_rate, line.cif_total, "CIF"),
        (line.erection_unit_rate, line.erection_total, "erection"),
    ):
        if line.quantity is None or rate is None or total is None:
            continue
        expected = line.quantity * rate
        if abs(expected - total) > max(ARITHMETIC_TOLERANCE, abs(expected) * ARITHMETIC_TOLERANCE):
            return f"{label}: {line.quantity} x {rate} = {expected:,.2f}, sheet says {total:,.2f}"
    return None


def _parse_row(
    row_number: int,
    row: list[Any],
    cm: ColumnMap,
    section: str | None,
    role: str,
) -> BoqLine | None:
    raw_item = _cell(row, cm.item_no)
    item_no = None
    if raw_item is not None:
        text = str(raw_item).strip()
        # Float drift in the source turns item 1.002 into
        # 1.0019999999999998; trim it back to something readable.
        if _is_number(raw_item):
            text = f"{float(raw_item):.10g}"
        item_no = text or None

    description = _cell(row, cm.description)
    description = str(description).strip() if description is not None else ""

    line = BoqLine(
        row_number=row_number,
        item_no=item_no,
        description=description,
        kind="note",
        section=section,
    )

    unit = _cell(row, cm.unit)
    line.unit = str(unit).strip() if unit is not None else None

    quantity, _ = _number(row, cm.quantity)
    line.quantity = quantity

    for field, index in (
        ("unit_rate", cm.unit_rate),
        ("cif_unit_rate", cm.cif_unit_rate),
        ("cif_total", cm.cif_total),
        ("erection_unit_rate", cm.erection_unit_rate),
        ("erection_total", cm.erection_total),
        ("line_total", cm.line_total),
    ):
        number, text = _number(row, index)
        setattr(line, field, number)
        if text:
            line.non_numeric[field] = text

    has_money = any(
        value is not None
        for value in (
            line.unit_rate,
            line.cif_unit_rate,
            line.cif_total,
            line.erection_unit_rate,
            line.erection_total,
            line.line_total,
        )
    )
    if not description and not has_money and line.quantity is None:
        return None

    if _TOTAL_PATTERN.search(description):
        # A stated total restates lines already captured above it.
        line.kind = "subtotal"
    elif line.quantity is not None:
        line.kind = "item"
    elif has_money:
        # Money with no quantity to price against. On a rollup sheet
        # that is the actual data; on a priced BOQ sheet it is a section
        # subtotal, and counting it would double the sheet.
        line.kind = "item" if role == "summary" else "subtotal"
    elif (
        item_no
        and _ITEM_NO_PATTERN.match(item_no)
        and not _PLACEHOLDER_PATTERN.match(description)
        and len(description) <= MAX_SECTION_DESCRIPTION
    ):
        # Numbered, no money, short label: a section heading such as
        # "1.1 33 kV GIS Switchgear" whose children carry the prices.
        line.kind = "section"
    else:
        line.kind = "note"

    if line.kind == "item":
        # The power template states a combined A+B total; derive it when
        # only the components are present so every item has one.
        if line.line_total is None and (line.cif_total is not None or line.erection_total is not None):
            line.line_total = (line.cif_total or 0.0) + (line.erection_total or 0.0)
        line.arithmetic_error = _check_arithmetic(line)

    return line


def _title_lines(ws, header_row: int, merged: dict[tuple[int, int], Any], width: int) -> list[str]:
    titles = []
    for row in range(1, header_row):
        values = [v for v in _row_values(ws, row, merged, width) if v is not None]
        if not values:
            continue
        text = str(values[0]).strip()
        if text and text not in titles:
            titles.append(text)
    return titles


_TENDER_PATTERN = re.compile(r"\b([A-Z]-\d{4,6})")


def parse_workbook(path_or_stream: Any, source_file: str) -> BoqDocument:
    workbook = openpyxl.load_workbook(path_or_stream, data_only=True, read_only=False)

    sheets: list[BoqSheet] = []
    skipped: list[SkippedSheet] = []
    tender_ref: str | None = None

    for ws in workbook.worksheets:
        if ws.sheet_state != "visible":
            skipped.append(SkippedSheet(ws.title, "hidden sheet"))
            continue
        if ws.max_row is None or ws.max_row < 2:
            skipped.append(SkippedSheet(ws.title, "empty sheet"))
            continue

        # Vendor sheets carry long tails of empty formatted columns (one
        # real file reports 105); cap the scan so a wide sheet does not
        # dominate the parse.
        width = min(ws.max_column or 1, 40)
        merged = _resolve_merged(ws)

        header_row = find_header_row(ws, merged, width)
        if header_row is None:
            skipped.append(SkippedSheet(ws.title, "no header row found"))
            continue

        labels, band_top, band_bottom = _combined_headers(ws, header_row, merged, width)
        column_map, layout, role = build_column_map(labels)
        if not column_map.is_usable():
            skipped.append(SkippedSheet(ws.title, "no description + money columns"))
            continue

        titles = _title_lines(ws, band_top, merged, width)
        if tender_ref is None:
            for text in titles:
                match = _TENDER_PATTERN.search(text)
                if match:
                    tender_ref = match.group(1)
                    break

        # Everything through the band bottom is header, not data.
        first_data_row = band_bottom + 1

        lines: list[BoqLine] = []
        section: str | None = None
        # A vertically merged item-number cell repeats down its rows, so
        # without this the spec paragraph under a heading would register
        # as a second section carrying the same number.
        last_section_item_no: str | None = None
        for row_number in range(first_data_row, ws.max_row + 1):
            parsed = _parse_row(
                row_number, _row_values(ws, row_number, merged, width), column_map, section, role
            )
            if parsed is None:
                continue
            if parsed.kind == "section" and parsed.item_no != last_section_item_no:
                section = (
                    f"{parsed.item_no} {parsed.description}".strip()
                    if parsed.item_no
                    else parsed.description
                )
                last_section_item_no = parsed.item_no
            lines.append(parsed)

        if not any(line.kind == "item" for line in lines):
            skipped.append(SkippedSheet(ws.title, "no priced line items"))
            continue

        sheets.append(
            BoqSheet(
                sheet_name=ws.title,
                header_row=header_row,
                layout=layout,
                role=role,
                column_map=column_map,
                title_lines=titles,
                lines=lines,
            )
        )

    workbook.close()

    # Water workbooks put the tender reference in the filename rather
    # than in any sheet's title block, so fall back to it.
    if tender_ref is None:
        match = _TENDER_PATTERN.search(source_file.upper())
        if match:
            tender_ref = match.group(1)

    return BoqDocument(
        source_file=source_file, tender_ref=tender_ref, sheets=sheets, skipped=skipped
    )
