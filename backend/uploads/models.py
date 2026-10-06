"""Shapes for an uploaded, analyst-confirmed BOQ.

Deliberately independent of both the Excel parser's own output and of
Maximo's column names. The parser produces whatever the vendor's
spreadsheet happened to contain; Maximo produces RFQLINENUM/UNITCOST and
friends. This sits between them: the parser's output is normalised into
these shapes at upload time, and backend/uploads/source.py presents them
back in the exact row shape the existing engines already expect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

ORIGINAL = "original"


@dataclass
class UploadedLine:
    """One BOQ line, shared across every vendor and round.

    `line_number` is the join key that stands in for Maximo's
    RFQLINENUM. It is assigned once, in upload order of the first file,
    and never recomputed, because every price in the project is keyed to
    it. `item_no` is the vendor's own numbering, which is what the
    matching is actually based on.
    """

    line_number: float
    item_no: str | None
    description: str
    unit: str | None = None
    quantity: float | None = None
    section: str | None = None


@dataclass
class UploadedPrice:
    line_number: float
    vendor: str
    round_label: str
    unit_cost: float | None = None
    line_cost: float | None = None


@dataclass
class UploadedSubmission:
    """One uploaded file: a single vendor at a single round."""

    submission_id: str
    vendor: str
    round_label: str
    filename: str
    uploaded_at: datetime
    line_count: int = 0
    # Carried through from the parser so the review screen can show the
    # extraction's own cross-check against the vendor's summary sheet.
    extracted_total: float | None = None
    stated_total: float | None = None
    reconciles: bool | None = None


@dataclass
class UploadedBoq:
    """Everything an uploaded project holds, including its own project
    metadata.

    An uploaded project is deliberately self-contained rather than
    registered in bid_analyzer_projects. That table needs a CREATE
    TABLE/INSERT grant which has not landed, so a project row cannot be
    written today. Keeping uploaded projects here means the whole Excel
    path works with no grant at all, which is the point of shipping it
    as a usable BETA rather than something blocked behind the same wait
    as everything else.

    `confirmed` gates whether the analysis tabs will read it: an
    unconfirmed BOQ is still being edited and must not drive a
    comparison.
    """

    project_id: str
    name: str
    created_by: str
    created_by_label: str | None
    created_at: datetime
    lines: dict[float, UploadedLine] = field(default_factory=dict)
    prices: dict[tuple[float, str, str], UploadedPrice] = field(default_factory=dict)
    submissions: list[UploadedSubmission] = field(default_factory=list)
    vendor_names: dict[str, str | None] = field(default_factory=dict)
    confirmed: bool = False
    confirmed_at: datetime | None = None

    @property
    def vendors(self) -> list[str]:
        return sorted(self.vendor_names)

    @property
    def rounds_present(self) -> list[str]:
        """ORIGINAL first, then numeric rounds in order. Matches the
        label vocabulary build_round_snapshots() already produces for
        Maximo, so the frontend's round selector needs no special case."""
        others = {r for (_, _, r) in self.prices} - {ORIGINAL}

        def sort_key(label: str) -> tuple[int, float, str]:
            try:
                return (0, float(label), "")
            except ValueError:
                return (1, 0.0, label)

        return [ORIGINAL] + sorted(others, key=sort_key)

    def next_line_number(self) -> float:
        return float(len(self.lines) + 1)
