"""Canonical BOQ shapes produced by the Excel parser.

Dataclasses rather than Pydantic models, matching the convention every
other request/response shape in this codebase already follows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Every vendor BOQ seen so far is one of two column layouts: the ADDC
# power template (a CIF/Local rate pair plus an Erection rate pair) and
# the water template (a single rate pair). Both collapse into this one
# canonical row, with the power-only fields left None for water sheets.
LineKind = str  # "item" | "section" | "subtotal" | "note"

# Vendor sheets carry rounding drift between a summary and its detail;
# anything under this is agreement, not a finding.
RECONCILIATION_TOLERANCE_PCT = 0.5


@dataclass
class Reconciliation:
    extracted_total: float
    stated_total: float
    difference: float
    percent: float
    agrees: bool


@dataclass
class BoqLine:
    row_number: int
    item_no: str | None
    description: str
    kind: LineKind
    unit: str | None = None
    quantity: float | None = None
    # Single-rate layouts (the water template) fill unit_rate and leave
    # the CIF/Erection pair None; the ADDC power template does the
    # reverse. Never both, so which one is populated identifies the
    # layout on a per-row basis.
    unit_rate: float | None = None
    cif_unit_rate: float | None = None
    cif_total: float | None = None
    erection_unit_rate: float | None = None
    erection_total: float | None = None
    line_total: float | None = None
    # The nearest preceding section heading, carried down so a priced
    # row still says what it belongs to. Vendor sheets routinely leave
    # the item-number cell blank on the priced row and put the number on
    # the heading above it, so without this the row loses its context.
    section: str | None = None
    # Text found in a column the layout says should hold a number, e.g.
    # "included in BOQ item 1.1". Preserved rather than coerced to 0,
    # because a zero here and a cross-reference here mean different
    # things commercially.
    non_numeric: dict[str, str] = field(default_factory=dict)
    arithmetic_error: str | None = None


@dataclass
class ColumnMap:
    """Zero-based column indices for one sheet's detected layout."""

    item_no: int | None = None
    description: int | None = None
    unit: int | None = None
    quantity: int | None = None
    unit_rate: int | None = None
    cif_unit_rate: int | None = None
    cif_total: int | None = None
    erection_unit_rate: int | None = None
    erection_total: int | None = None
    line_total: int | None = None

    def is_usable(self) -> bool:
        """A sheet is only a BOQ if it has descriptions and at least one
        money column. Summary and cover sheets fail this and are skipped
        rather than parsed into garbage rows."""
        has_money = any(
            idx is not None
            for idx in (
                self.unit_rate,
                self.cif_unit_rate,
                self.cif_total,
                self.erection_unit_rate,
                self.erection_total,
                self.line_total,
            )
        )
        return self.description is not None and has_money


@dataclass
class BoqSheet:
    sheet_name: str
    header_row: int
    layout: str  # "power" | "water" | "generic"
    # "boq" for a priced line-item sheet, "summary" for a rollup of
    # other sheets. Both are extracted, but only "boq" sheets count
    # toward the document total, since a summary restates figures that
    # are already there and would otherwise double-count.
    role: str
    column_map: ColumnMap
    title_lines: list[str]
    lines: list[BoqLine]

    @property
    def item_count(self) -> int:
        return sum(1 for line in self.lines if line.kind == "item")

    @property
    def total(self) -> float:
        return sum(line.line_total or 0.0 for line in self.lines if line.kind == "item")


@dataclass
class SkippedSheet:
    sheet_name: str
    reason: str


@dataclass
class BoqDocument:
    source_file: str
    tender_ref: str | None
    sheets: list[BoqSheet]
    skipped: list[SkippedSheet]

    @property
    def boq_sheets(self) -> list[BoqSheet]:
        return [sheet for sheet in self.sheets if sheet.role == "boq"]

    @property
    def summary_sheets(self) -> list[BoqSheet]:
        return [sheet for sheet in self.sheets if sheet.role == "summary"]

    @property
    def item_count(self) -> int:
        return sum(sheet.item_count for sheet in self.boq_sheets)

    @property
    def grand_total(self) -> float:
        return sum(sheet.total for sheet in self.boq_sheets)

    @property
    def summary_total(self) -> float | None:
        """The vendor's own stated total, from their top-level rollup.

        Deliberately the largest single summary sheet rather than the
        sum of all of them: a water workbook carries one project-level
        summary plus a per-area summary for each bill, and the
        project-level one already contains the others, so adding them
        together would double-count.
        """
        if not self.summary_sheets:
            return None
        return max(sheet.total for sheet in self.summary_sheets)

    @property
    def reconciliation(self) -> "Reconciliation | None":
        """Cross-check the extracted line items against the vendor's own
        stated total.

        This is the highest-value output of the whole parse. A clean
        match means the extraction captured every priced line. A
        mismatch is real and worth an analyst's attention either way:
        it is either a parse that missed something, or, as seen in the
        sample data, a vendor whose own summary sheet contradicts their
        own priced detail.
        """
        stated = self.summary_total
        if stated is None or not self.boq_sheets:
            return None
        extracted = self.grand_total
        difference = extracted - stated
        pct = abs(difference) / stated * 100 if stated else 0.0
        return Reconciliation(
            extracted_total=extracted,
            stated_total=stated,
            difference=difference,
            percent=pct,
            agrees=pct <= RECONCILIATION_TOLERANCE_PCT,
        )

    @property
    def arithmetic_errors(self) -> list[tuple[str, BoqLine]]:
        return [
            (sheet.sheet_name, line)
            for sheet in self.sheets
            for line in sheet.lines
            if line.arithmetic_error
        ]
