"""Presents an uploaded BOQ in the exact shape the Maximo-backed engines
already consume.

The comparison engine, the round-snapshot builder and everything layered
on them were written against Maximo's row shape: attribute access for
RFQLINENUM, VENDOR, UNITCOST and so on. Rather than teach those engines
about a second data model, an uploaded BOQ is adapted to that same shape
here. The engines then need only their fetch calls swapped, so the
Maximo path stays byte-identical and the flagging, outlier detection and
round forward-fill are literally the same code for both sources.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.uploads.models import ORIGINAL, UploadedBoq


@dataclass
class _QuotationLineRow:
    """Mirrors a quotationline row. ORDERUNIT is always a real unit or
    None, never 'HEADER': section headings are dropped at upload time
    rather than carried through and filtered later."""

    RFQLINENUM: float
    VENDOR: str
    DESCRIPTION: str | None
    ORDERQTY: float | None
    ORDERUNIT: str | None
    UNITCOST: float | None
    LINECOST: float | None


@dataclass
class _DiscountHistoryLineRow:
    """Mirrors a DISCOUNTHISTORYLINE row.

    An uploaded project has no discount history, so each round after the
    original is synthesised into the revision shape the forward-fill
    already understands. Round label "1.0" becomes REVISION 1.0, and the
    uploaded price becomes LINECOSTWDIS. The resulting snapshots are
    indistinguishable from Maximo's.
    """

    VENDOR: str
    REVISION: float
    RFQLINENUM: float
    LINECOSTWDIS: float | None


class UploadedSource:
    """The uploaded-BOQ counterpart to Maximo's fetch functions."""

    def __init__(self, boq: UploadedBoq) -> None:
        self._boq = boq

    def vendor_roster(self) -> dict[str, str | None]:
        return dict(self._boq.vendor_names)

    def quotationlines(self) -> list[_QuotationLineRow]:
        """Original-round rows only, matching quotationline, which holds
        the original quote and nothing later."""
        rows: list[_QuotationLineRow] = []
        for line in self._boq.lines.values():
            for vendor in self._boq.vendors:
                price = self._boq.prices.get((line.line_number, vendor, ORIGINAL))
                # A vendor with no entry for this line did not quote it,
                # which is exactly a quotationline row with null costs,
                # not an absent row. Emitting it keeps the unquoted flag
                # working the same way it does for Maximo.
                rows.append(
                    _QuotationLineRow(
                        RFQLINENUM=line.line_number,
                        VENDOR=vendor,
                        DESCRIPTION=line.description,
                        ORDERQTY=line.quantity,
                        ORDERUNIT=line.unit,
                        UNITCOST=price.unit_cost if price else None,
                        LINECOST=price.line_cost if price else None,
                    )
                )
        return rows

    def original_lines(self) -> dict[tuple[str, float], float]:
        return {
            (vendor, line_number): price.line_cost
            for (line_number, vendor, round_label), price in self._boq.prices.items()
            if round_label == ORIGINAL and price.line_cost is not None
        }

    def discount_history_lines(self) -> list[_DiscountHistoryLineRow]:
        rows: list[_DiscountHistoryLineRow] = []
        for (line_number, vendor, round_label), price in self._boq.prices.items():
            if round_label == ORIGINAL:
                continue
            try:
                revision = float(round_label)
            except ValueError:
                # A round label that is not numeric cannot be ordered
                # against the others, so it is skipped rather than
                # silently misplaced in the sequence.
                continue
            rows.append(
                _DiscountHistoryLineRow(
                    VENDOR=vendor,
                    REVISION=revision,
                    RFQLINENUM=line_number,
                    LINECOSTWDIS=price.line_cost,
                )
            )
        rows.sort(key=lambda r: r.REVISION)
        return rows
