"""Compare bidders and generate analysis insights."""

from dataclasses import dataclass
from ..extraction.excel_parser import BOQExtraction, BOQLot
from .item_matcher import match_items


@dataclass(frozen=True)
class ComparisonItem:
    item_no: str
    description: str
    unit: str | None
    qty: float | None
    bidder_prices: dict[str, dict]  # bidder_name -> {cif_total, erection_total, total}
    match_method: str = "exact"  # "exact", "normalized", "fuzzy", "llm", "unmatched"
    match_confidence: float = 1.0


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


def _sort_key(item_no: str) -> list[float]:
    """Sort item numbers numerically (e.g., 1.2.3 before 1.10.1)."""
    return [float(p) if p.replace(".", "").isdigit() else 0 for p in item_no.split(".")]


def _match_bidders_for_lot(
    bidder_items: dict[str, dict[str, dict]],
) -> tuple[list[ComparisonItem], dict[str, str]]:
    """Match items across all bidders for a single lot using 4-tier matching.

    For >2 bidders, we pick the first bidder as reference and match each
    other bidder against it. Items only in non-reference bidders are added
    as unmatched.

    Returns:
        (comparison_items, canonical_map) where canonical_map maps
        bidder-specific item_no -> canonical item_no used in comparison.
    """
    bidder_names = list(bidder_items.keys())
    if not bidder_names:
        return [], {}

    reference_bidder = bidder_names[0]
    ref_items = bidder_items[reference_bidder]

    # Maps: canonical_item_no -> {bidder_name -> original_item_no}
    # Canonical = the reference bidder's item_no
    item_mapping: dict[str, dict[str, str]] = {}
    match_info: dict[str, tuple[str, float]] = {}  # canonical -> (method, confidence)

    # Initialize with reference bidder (all exact by definition)
    for item_no in ref_items:
        item_mapping[item_no] = {reference_bidder: item_no}
        match_info[item_no] = ("exact", 1.0)

    # Match each other bidder against the reference
    for bidder_name in bidder_names[1:]:
        other_items = bidder_items[bidder_name]
        matches, unmatched_a_keys, unmatched_b_keys = match_items(ref_items, other_items)

        for m in matches:
            canonical = m.item_no_a  # reference bidder's item_no
            if canonical not in item_mapping:
                item_mapping[canonical] = {reference_bidder: canonical}
            item_mapping[canonical][bidder_name] = m.item_no_b

            # Track the lowest-confidence match method for this canonical item
            existing_method, existing_conf = match_info.get(canonical, ("exact", 1.0))
            if m.confidence < existing_conf:
                match_info[canonical] = (m.match_method, m.confidence)

        # Items only in this bidder (no match in reference)
        for key_b in unmatched_b_keys:
            item_mapping[key_b] = {bidder_name: key_b}
            match_info[key_b] = ("unmatched", 0.0)

    # Build ComparisonItems
    comparison_items = []
    for canonical in sorted(item_mapping.keys(), key=_sort_key):
        bidder_map = item_mapping[canonical]
        method, confidence = match_info.get(canonical, ("exact", 1.0))

        # Get description/unit/qty from first bidder that has it
        desc, unit, qty = "", None, None
        for bn, orig_key in bidder_map.items():
            data = bidder_items[bn].get(orig_key, {})
            if data:
                desc = data.get("description", "")
                unit = data.get("unit")
                qty = data.get("qty")
                break

        # Build prices from each bidder using their original item_no
        prices = {}
        for bidder_name in bidder_names:
            orig_key = bidder_map.get(bidder_name)
            if orig_key and orig_key in bidder_items[bidder_name]:
                d = bidder_items[bidder_name][orig_key]
                prices[bidder_name] = {
                    "cif_total": d["cif_total"],
                    "erection_total": d["erection_total"],
                    "total": d["total"],
                }
            else:
                prices[bidder_name] = {
                    "cif_total": None,
                    "erection_total": None,
                    "total": None,
                }

        # Skip section headers: items where no bidder has any pricing
        has_any_price = any(
            p.get("total") is not None or p.get("cif_total") is not None
            for p in prices.values()
        )
        if not has_any_price:
            continue

        comparison_items.append(ComparisonItem(
            item_no=canonical,
            description=desc,
            unit=unit,
            qty=qty,
            bidder_prices=prices,
            match_method=method,
            match_confidence=confidence,
        ))

    return comparison_items


def compare_round(
    extractions: dict[str, BOQExtraction],
    round_name: str,
) -> ComparisonResult:
    """Compare all bidders for a given round."""
    # Collect item maps per bidder per lot
    bidder_lot_items: dict[int, dict[str, dict[str, dict]]] = {}

    for bidder_name, extraction in extractions.items():
        for lot in extraction.lots:
            if lot.lot_number not in bidder_lot_items:
                bidder_lot_items[lot.lot_number] = {}
            bidder_lot_items[lot.lot_number][bidder_name] = _build_item_map(lot)

    lot_comparisons = []
    all_flags = []

    for lot_num in sorted(bidder_lot_items.keys()):
        bidder_items = bidder_lot_items[lot_num]

        # Use 4-tier matching
        comparison_items = _match_bidders_for_lot(bidder_items)

        # Lot-level totals and flags
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
                    all_flags.extend(
                        _detect_flags(bidder_name, lot, bidder_items.get(bidder_name, {}), bidder_items)
                    )

        lot_comparisons.append(LotComparison(
            lot_name=lot_name,
            lot_number=lot_num,
            items=tuple(comparison_items),
            bidder_totals=bidder_totals,
        ))

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
