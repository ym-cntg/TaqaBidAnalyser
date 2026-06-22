from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class FileFormat(Enum):
    EXCEL = "excel"
    PDF = "pdf"


class ExtractionMethod(Enum):
    OPENPYXL = "openpyxl"
    PYMUPDF = "pymupdf"
    AZURE = "azure"


class FindingCategory(Enum):
    UNQUOTED = "unquoted"
    ARITHMETIC_ERROR = "arithmetic_error"
    UNBALANCED = "unbalanced"
    OUTLIER = "outlier"
    DESCRIPTION_CHANGE = "description_change"


class Severity(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class SourceFile:
    path: Path
    format: FileFormat
    bidder: str
    round: str
    lot: str | None  # None for summary files


@dataclass(frozen=True)
class LineItem:
    item_no: str
    description: str
    unit: str | None = None
    qty: float | None = None
    cif_unit_rate: float | None = None
    cif_total: float | None = None
    erection_unit_rate: float | None = None
    erection_total: float | None = None
    total_price: float | None = None


@dataclass(frozen=True)
class SectionData:
    name: str
    line_items: tuple[LineItem, ...]


@dataclass(frozen=True)
class ExtractedBOQ:
    bidder: str
    round: str
    lot: str
    source_file: Path
    extraction_method: ExtractionMethod
    sections: tuple[SectionData, ...]

    @property
    def all_line_items(self) -> tuple[LineItem, ...]:
        items = []
        for section in self.sections:
            items.extend(section.line_items)
        return tuple(items)

    @property
    def total_price(self) -> float | None:
        prices = [
            item.total_price
            for item in self.all_line_items
            if item.total_price is not None
        ]
        return sum(prices) if prices else None


@dataclass(frozen=True)
class SummaryEntry:
    item_no: str | float
    description: str
    cif_total: float | None = None
    erection_total: float | None = None
    total_price: float | None = None


@dataclass(frozen=True)
class ExtractedSummary:
    bidder: str
    round: str
    source_file: Path
    extraction_method: ExtractionMethod
    lots: dict[str, tuple[SummaryEntry, ...]] = field(default_factory=dict)
    lot_totals: dict[str, float] = field(default_factory=dict)
    contract_total: float | None = None


@dataclass(frozen=True)
class Finding:
    category: FindingCategory
    severity: Severity
    bidder: str
    round: str
    lot: str
    item_no: str | None
    message: str
    value: float | None = None
    reference_value: float | None = None


@dataclass
class TenderData:
    tender_id: str
    name: str
    source_files: list[SourceFile] = field(default_factory=list)
    extractions: list[ExtractedBOQ] = field(default_factory=list)
    summaries: list[ExtractedSummary] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def bidders(self) -> list[str]:
        return sorted({e.bidder for e in self.extractions})

    @property
    def rounds(self) -> list[str]:
        round_order = {"original": 0, "round1": 1, "round2": 2, "round3": 3, "round4": 4}
        rounds = {e.round for e in self.extractions}
        return sorted(rounds, key=lambda r: round_order.get(r, 99))

    @property
    def lots(self) -> list[str]:
        """Return base lots only (exclude option variants like 'Lot 1 (Option1)')."""
        lots = {e.lot for e in self.extractions}
        # Filter to base lots — those without parenthetical suffixes
        base_lots = {lot for lot in lots if "(" not in lot}
        return sorted(base_lots) if base_lots else sorted(lots)

    def get_extraction(
        self, bidder: str, round_name: str, lot: str
    ) -> ExtractedBOQ | None:
        for e in self.extractions:
            if e.bidder == bidder and e.round == round_name and e.lot == lot:
                return e
        return None
