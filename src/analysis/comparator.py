from __future__ import annotations

from dataclasses import dataclass, field

from src.models import TenderData


@dataclass
class LineItemComparison:
    item_no: str
    description: str
    unit: str | None
    qty: float | None
    # bidder_name -> price values
    bidder_cif_total: dict[str, float | None] = field(default_factory=dict)
    bidder_erection_total: dict[str, float | None] = field(default_factory=dict)
    bidder_total_price: dict[str, float | None] = field(default_factory=dict)

    @property
    def median_total(self) -> float | None:
        prices = [v for v in self.bidder_total_price.values() if v is not None and v > 0]
        if not prices:
            return None
        sorted_prices = sorted(prices)
        mid = len(sorted_prices) // 2
        if len(sorted_prices) % 2 == 0:
            return (sorted_prices[mid - 1] + sorted_prices[mid]) / 2
        return sorted_prices[mid]

    @property
    def min_total(self) -> float | None:
        prices = [v for v in self.bidder_total_price.values() if v is not None and v > 0]
        return min(prices) if prices else None

    @property
    def max_total(self) -> float | None:
        prices = [v for v in self.bidder_total_price.values() if v is not None and v > 0]
        return max(prices) if prices else None


@dataclass
class SectionComparison:
    section_name: str
    items: list[LineItemComparison] = field(default_factory=list)


@dataclass
class LotComparison:
    lot: str
    round: str
    bidders: list[str] = field(default_factory=list)
    sections: list[SectionComparison] = field(default_factory=list)
    bidder_lot_totals: dict[str, float | None] = field(default_factory=dict)


def compare_lot(
    tender: TenderData,
    lot: str,
    round_name: str,
) -> LotComparison:
    """Build a cross-bidder comparison for a specific lot and round."""
    bidders = tender.bidders
    comparison = LotComparison(lot=lot, round=round_name, bidders=bidders)

    # Collect all section names across all bidders for this lot/round
    section_names: list[str] = []
    section_names_seen: set[str] = set()

    for bidder in bidders:
        extraction = tender.get_extraction(bidder, round_name, lot)
        if extraction is None:
            continue
        for section in extraction.sections:
            if section.name not in section_names_seen:
                section_names.append(section.name)
                section_names_seen.add(section.name)

    for section_name in section_names:
        section_comp = _compare_section(tender, bidders, round_name, lot, section_name)
        comparison.sections.append(section_comp)

    # Lot totals per bidder
    for bidder in bidders:
        extraction = tender.get_extraction(bidder, round_name, lot)
        if extraction is not None:
            comparison.bidder_lot_totals[bidder] = extraction.total_price

    return comparison


def _compare_section(
    tender: TenderData,
    bidders: list[str],
    round_name: str,
    lot: str,
    section_name: str,
) -> SectionComparison:
    """Compare a single BOQ section across all bidders."""
    # Build unified item list from all bidders
    all_items: dict[str, LineItemComparison] = {}

    for bidder in bidders:
        extraction = tender.get_extraction(bidder, round_name, lot)
        if extraction is None:
            continue

        for section in extraction.sections:
            if section.name != section_name:
                continue

            for item in section.line_items:
                if not item.item_no:
                    continue

                if item.item_no not in all_items:
                    all_items[item.item_no] = LineItemComparison(
                        item_no=item.item_no,
                        description=item.description,
                        unit=item.unit,
                        qty=item.qty,
                    )

                comp = all_items[item.item_no]
                comp.bidder_cif_total[bidder] = item.cif_total
                comp.bidder_erection_total[bidder] = item.erection_total
                comp.bidder_total_price[bidder] = item.total_price

    # Sort by item number (numeric sort)
    sorted_items = sorted(
        all_items.values(),
        key=lambda x: _sort_key(x.item_no),
    )

    return SectionComparison(section_name=section_name, items=sorted_items)


def build_tender_summary(
    tender: TenderData,
    round_name: str,
) -> dict[str, dict[str, float | None]]:
    """Build bidder -> lot -> total mapping for a given round."""
    summary: dict[str, dict[str, float | None]] = {}

    for bidder in tender.bidders:
        summary[bidder] = {}
        for lot in tender.lots:
            extraction = tender.get_extraction(bidder, round_name, lot)
            summary[bidder][lot] = extraction.total_price if extraction else None

    return summary


def _sort_key(item_no: str) -> tuple:
    """Sort item numbers like 1, 1.1, 1.2, 2, 2.1 etc."""
    parts = item_no.split(".")
    result = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            result.append(0)
    return tuple(result)
