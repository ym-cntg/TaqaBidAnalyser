"""Round-over-round price movement tracking and anomaly detection.

Negotiation rounds should generally move a bidder's pricing down (discounts
offered in response to ADDC's feedback). This module builds the per-bidder
trend across rounds (contract/lot/item granularity) and flags movement that
doesn't fit that pattern: a round-over-round *increase* (should never happen
in a negotiation), or a discount on one item far steeper than peer bidders
gave for the same item — usually a sign of front/back-loading the savings
rather than a genuine, evenly-applied discount.
"""

import statistics
from dataclasses import dataclass

from ..extraction.excel_parser import BOQExtraction, ROUND_DIR_NAMES
from .comparator import Flag

# Same peer-relative-deviation trick as comparator._detect_cross_lot_flags:
# a bidder's own round-over-round ratio, compared against the *median ratio
# peers showed for the same item across the same two rounds*.
PEER_DEVIATION_THRESHOLD = 4.0
# Ignore float/rounding noise below this — only material increases count.
INCREASE_TOLERANCE = 1.0


@dataclass(frozen=True)
class RoundPoint:
    round_name: str
    total_contract_price: float | None
    lot_totals: dict[int, float | None]


@dataclass(frozen=True)
class BidderRoundTrend:
    bidder: str
    points: tuple[RoundPoint, ...]


@dataclass(frozen=True)
class RoundTrendResult:
    bidders: tuple[BidderRoundTrend, ...]
    rounds_present: tuple[str, ...]
    flags: tuple[Flag, ...]


def _round_index(name: str) -> int:
    return ROUND_DIR_NAMES.index(name)


def _item_totals(ext: BOQExtraction) -> dict[tuple[int, str], tuple[float, str]]:
    """(lot_number, item_no) -> (total, description) for every priced item."""
    out = {}
    for lot in ext.lots:
        for sheet in lot.sheets:
            for item in sheet.items:
                if item.is_section_header or not item.item_no or item.total is None:
                    continue
                out[(lot.lot_number, item.item_no)] = (item.total, item.description)
    return out


def _detect_movement_flags(
    bidder_round_extractions: dict[str, dict[str, BOQExtraction]],
    rounds_present: list[str],
) -> list[Flag]:
    flags: list[Flag] = []
    lot_names: dict[int, str] = {}
    for exts in bidder_round_extractions.values():
        for ext in exts.values():
            for lot in ext.lots:
                lot_names[lot.lot_number] = lot.lot_name

    # bidder -> round -> {(lot,item): (total, desc)}
    per_bidder_totals = {
        bidder: {r: _item_totals(ext) for r, ext in exts.items()}
        for bidder, exts in bidder_round_extractions.items()
    }

    for i in range(len(rounds_present) - 1):
        r1, r2 = rounds_present[i], rounds_present[i + 1]

        # bidder -> key -> ratio, for bidders with both rounds present
        bidder_ratios: dict[str, dict[tuple[int, str], float]] = {}
        for bidder, by_round in per_bidder_totals.items():
            items_r1 = by_round.get(r1)
            items_r2 = by_round.get(r2)
            if items_r1 is None or items_r2 is None:
                continue
            ratios = {}
            for key, (val1, _) in items_r1.items():
                if key not in items_r2 or val1 <= 0:
                    continue
                val2, _ = items_r2[key]
                ratios[key] = val2 / val1
            bidder_ratios[bidder] = ratios

        # Rule 1: any material round-over-round increase is anomalous by
        # definition — negotiation rounds don't raise prices.
        for bidder, ratios in bidder_ratios.items():
            items_r1 = per_bidder_totals[bidder][r1]
            items_r2 = per_bidder_totals[bidder][r2]
            for key, ratio in ratios.items():
                val1, _ = items_r1[key]
                val2, desc = items_r2[key]
                if val2 - val1 > INCREASE_TOLERANCE and ratio > 1.001:
                    lot_num, item_no = key
                    flags.append(Flag(
                        severity="critical",
                        category="round_movement",
                        bidder=bidder,
                        lot=lot_names.get(lot_num, f"Lot {lot_num}"),
                        item_no=item_no,
                        description=desc[:100],
                        detail=(
                            f"Price increased from {r1} to {r2}: "
                            f"{val1:,.0f} -> {val2:,.0f} ({ratio:.2f}x) — "
                            f"unexpected direction for a negotiation round"
                        ),
                    ))

        # Rule 2: a decrease far steeper than peers gave on the same item —
        # normalize against peer-median ratio for that (lot, item) this round.
        by_key: dict[tuple[int, str], dict[str, float]] = {}
        for bidder, ratios in bidder_ratios.items():
            for key, ratio in ratios.items():
                by_key.setdefault(key, {})[bidder] = ratio

        for key, ratios_by_bidder in by_key.items():
            if len(ratios_by_bidder) < 3:
                continue  # need peers to judge "far steeper than usual"
            peer_median = statistics.median(ratios_by_bidder.values())
            if peer_median <= 0:
                continue
            for bidder, ratio in ratios_by_bidder.items():
                if ratio >= 1.001:
                    continue  # increases are already covered by rule 1
                deviation = ratio / peer_median
                if deviation < 1 / PEER_DEVIATION_THRESHOLD:
                    lot_num, item_no = key
                    val1, _ = per_bidder_totals[bidder][r1][key]
                    val2, desc = per_bidder_totals[bidder][r2][key]
                    flags.append(Flag(
                        severity="warning",
                        category="round_movement",
                        bidder=bidder,
                        lot=lot_names.get(lot_num, f"Lot {lot_num}"),
                        item_no=item_no,
                        description=desc[:100],
                        detail=(
                            f"Discounted {r1} -> {r2} by a much steeper margin "
                            f"({val1:,.0f} -> {val2:,.0f}, {ratio:.2f}x) than peers "
                            f"typically did on this item ({peer_median:.2f}x) — "
                            f"possible front/back-loading rather than an even discount"
                        ),
                    ))

    return flags


def build_round_trend(
    bidder_round_extractions: dict[str, dict[str, BOQExtraction]],
) -> RoundTrendResult:
    """bidder_round_extractions: bidder_name -> {round_name: BOQExtraction}"""
    rounds_present = sorted(
        {r for exts in bidder_round_extractions.values() for r in exts},
        key=_round_index,
    )

    bidder_trends = []
    for bidder, exts in bidder_round_extractions.items():
        points = []
        for round_name in rounds_present:
            ext = exts.get(round_name)
            if ext is None:
                points.append(RoundPoint(round_name, None, {}))
                continue
            lot_totals = {lot.lot_number: lot.total_price for lot in ext.lots}
            points.append(RoundPoint(round_name, ext.total_contract_price, lot_totals))
        bidder_trends.append(BidderRoundTrend(bidder, tuple(points)))

    flags = _detect_movement_flags(bidder_round_extractions, rounds_present)
    return RoundTrendResult(tuple(bidder_trends), tuple(rounds_present), tuple(flags))
