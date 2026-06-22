"""Compare bidders and generate analysis insights."""

from dataclasses import dataclass
from ..extraction.excel_parser import BOQExtraction, BOQLot


@dataclass(frozen=True)
class ComparisonItem:
    item_no: str
    description: str
    unit: str | None
    qty: float | None
    bidder_prices: dict[str, dict]  # bidder_name -> {cif_total, erection_total, total}


@dataclass(frozen=True)
class Flag:
    severity: str  # "critical", "warning", "info"
    category: str  # "unquoted", "arithmetic", "unbalanced", "outlier", "missing"
    bidder: str
    lot: str
    item_no: str
    description: str
    detail: str


@dataclass(frozen=True)
class LotComparison:
    lot_name: str
    lot_number: int
    items: tuple[ComparisonItem, ...]
    bidder_totals: dict[str, dict]  # bidder -> {cif, erection, total}


@dataclass(frozen=True)
class ComparisonResult:
    tender_no: str
    round_name: str
    lots: tuple[LotComparison, ...]
    flags: tuple[Flag, ...]
    bidder_grand_totals: dict[str, float | None]


def _build_item_map(lot: BOQLot) -> dict[str, dict]:
    """Build a map of item_no -> item data from a lot."""
    item_map = {}
    for sheet in lot.sheets:
        for item in sheet.items:
            if item.item_no and not item.is_section_header:
                item_map[item.item_no] = {
                    "description": item.description,
                    "unit": item.unit,
                    "qty": item.qty,
                    "cif_total": item.cif_total,
                    "erection_total": item.erection_total,
                    "total": item.total,
                    "cif_unit_rate": item.cif_unit_rate,
                    "erection_unit_rate": item.erection_unit_rate,
                    "raw_cif": item.raw_cif,
                    "raw_erection": item.raw_erection,
                }
    return item_map


def _detect_flags(
    bidder_name: str,
    lot: BOQLot,
    item_map: dict[str, dict],
    all_bidder_items: dict[str, dict[str, dict]],
) -> list[Flag]:
    """Detect issues in a bidder's pricing."""
    flags = []

    for sheet in lot.sheets:
        for item in sheet.items:
            if item.is_section_header or not item.item_no:
                continue

            # Unquoted items — only flag if qty exists but no pricing at all
            if (
                item.qty is not None
                and item.qty > 0
                and item.total is None
                and item.cif_total is None
                and item.erection_total is None
            ):
                raw = item.raw_cif or ""
                if "included" not in raw.lower() and "bundled" not in raw.lower():
                    flags.append(Flag(
                        severity="warning",
                        category="unquoted",
                        bidder=bidder_name,
                        lot=lot.lot_name,
                        item_no=item.item_no,
                        description=item.description[:100],
                        detail="Item has no pricing — may be unquoted",
                    ))

            # Arithmetic check: unit_rate * qty should equal total
            if item.qty and item.cif_unit_rate and item.cif_total:
                expected = round(item.qty * item.cif_unit_rate, 2)
                actual = round(item.cif_total, 2)
                if abs(expected - actual) > 1.0:
                    flags.append(Flag(
                        severity="critical",
                        category="arithmetic",
                        bidder=bidder_name,
                        lot=lot.lot_name,
                        item_no=item.item_no,
                        description=item.description[:100],
                        detail=f"CIF: qty({item.qty}) x rate({item.cif_unit_rate}) = {expected}, but total is {actual}",
                    ))

            # Outlier detection: compare with other bidders
            for other_bidder, other_items in all_bidder_items.items():
                if other_bidder == bidder_name:
                    continue
                if item.item_no in other_items:
                    other = other_items[item.item_no]
                    if item.total and other.get("total") and other["total"] > 0:
                        ratio = item.total / other["total"]
                        if ratio > 3.0:
                            flags.append(Flag(
                                severity="warning",
                                category="outlier",
                                bidder=bidder_name,
                                lot=lot.lot_name,
                                item_no=item.item_no,
                                description=item.description[:100],
                                detail=f"{ratio:.1f}x higher than {other_bidder}",
                            ))
                        elif ratio < 0.33:
                            flags.append(Flag(
                                severity="info",
                                category="outlier",
                                bidder=bidder_name,
                                lot=lot.lot_name,
                                item_no=item.item_no,
                                description=item.description[:100],
                                detail=f"{ratio:.1f}x lower than {other_bidder} — potential underpricing",
                            ))

    # Unbalanced bidding: check CIF vs Erection ratio
    if lot.total_cif and lot.total_erection:
        ratio = lot.total_cif / (lot.total_cif + lot.total_erection)
        if ratio > 0.9:
            flags.append(Flag(
                severity="warning",
                category="unbalanced",
                bidder=bidder_name,
                lot=lot.lot_name,
                item_no="ALL",
                description="Overall lot pricing",
                detail=f"CIF is {ratio:.0%} of total — heavily front-loaded on supply costs",
            ))

    return flags


def compare_round(
    extractions: dict[str, BOQExtraction],
    round_name: str,
) -> ComparisonResult:
    """Compare all bidders for a given round."""
    # Collect item maps per bidder per lot
    bidder_lot_items: dict[int, dict[str, dict[str, dict]]] = {}  # lot_num -> bidder -> items

    for bidder_name, extraction in extractions.items():
        for lot in extraction.lots:
            if lot.lot_number not in bidder_lot_items:
                bidder_lot_items[lot.lot_number] = {}
            bidder_lot_items[lot.lot_number][bidder_name] = _build_item_map(lot)

    lot_comparisons = []
    all_flags = []

    for lot_num in sorted(bidder_lot_items.keys()):
        bidder_items = bidder_lot_items[lot_num]

        # Collect all unique item numbers across bidders
        all_item_nos = set()
        for items in bidder_items.values():
            all_item_nos.update(items.keys())

        # Build comparison items
        comparison_items = []
        for item_no in sorted(all_item_nos, key=lambda x: [float(p) if p.replace(".", "").isdigit() else 0 for p in x.split(".")]):
            # Get description from first bidder that has it
            desc = ""
            unit = None
            qty = None
            for items in bidder_items.values():
                if item_no in items:
                    desc = items[item_no]["description"]
                    unit = items[item_no]["unit"]
                    qty = items[item_no]["qty"]
                    break

            prices = {}
            for bidder_name, items in bidder_items.items():
                if item_no in items:
                    prices[bidder_name] = {
                        "cif_total": items[item_no]["cif_total"],
                        "erection_total": items[item_no]["erection_total"],
                        "total": items[item_no]["total"],
                    }
                else:
                    prices[bidder_name] = {
                        "cif_total": None,
                        "erection_total": None,
                        "total": None,
                    }

            comparison_items.append(ComparisonItem(
                item_no=item_no,
                description=desc,
                unit=unit,
                qty=qty,
                bidder_prices=prices,
            ))

        # Lot-level totals
        bidder_totals = {}
        lot_name = f"Lot {lot_num}"
        for bidder_name, extraction in extractions.items():
            for lot in extraction.lots:
                if lot.lot_number == lot_num:
                    lot_name = lot.lot_name
                    bidder_totals[bidder_name] = {
                        "cif": lot.total_cif,
                        "erection": lot.total_erection,
                        "total": lot.total_price,
                    }
                    # Detect flags
                    all_flags.extend(
                        _detect_flags(bidder_name, lot, bidder_items.get(bidder_name, {}), bidder_items)
                    )

        lot_comparisons.append(LotComparison(
            lot_name=lot_name,
            lot_number=lot_num,
            items=tuple(comparison_items),
            bidder_totals=bidder_totals,
        ))

    # Grand totals
    grand_totals = {}
    for bidder_name, extraction in extractions.items():
        grand_totals[bidder_name] = extraction.total_contract_price

    return ComparisonResult(
        tender_no="D-111808",
        round_name=round_name,
        lots=tuple(lot_comparisons),
        flags=tuple(all_flags),
        bidder_grand_totals=grand_totals,
    )
