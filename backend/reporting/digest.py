"""Build a compact, LLM-ready digest from a ComparisonResult.

The recommendation report (see `llm_report.py`) must never be fed the raw
per-item tables — for 7+ bidders across ~9 items groups that's thousands of
rows, most of it irrelevant to a negotiation narrative and expensive to
send on every regenerate. This module distills a `ComparisonResult` down to
the handful of facts an analyst actually reasons from: ranked totals, flag
counts, and the most severe flags per bidder.
"""

from ..analysis.comparator import ComparisonResult, Flag

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
TOP_FLAGS_PER_BIDDER = 6


def _data_gap_bidders(flags: tuple[Flag, ...]) -> dict[str, str]:
    """bidder -> reason, derived from the one 'missing' flag per lot that
    compare_round() emits for a data-gap bidder (see BOQExtraction.data_gap).
    Deduped since a bidder gets one such flag per lot, same detail text."""
    reasons: dict[str, str] = {}
    for f in flags:
        if f.category == "missing":
            reasons.setdefault(f.bidder, f.detail)
    return reasons


def _ranked_totals(
    grand_totals: dict[str, float | None], data_gap_bidders: dict[str, str]
) -> list[dict]:
    eligible = [
        (bidder, total)
        for bidder, total in grand_totals.items()
        if bidder not in data_gap_bidders and total is not None
    ]
    eligible.sort(key=lambda bt: bt[1])

    ranked = [
        {"bidder": bidder, "grand_total": total, "rank": i + 1}
        for i, (bidder, total) in enumerate(eligible)
    ]
    for bidder in grand_totals:
        if bidder in data_gap_bidders:
            ranked.append({
                "bidder": bidder,
                "grand_total": grand_totals[bidder],
                "rank": None,
            })
    return ranked


def _lot_totals(result: ComparisonResult) -> list[dict]:
    return [
        {
            "lot_name": lot.lot_name,
            "lot_number": lot.lot_number,
            "bidder_totals": lot.bidder_totals,
        }
        for lot in result.lots
    ]


def _flag_counts(flags: tuple[Flag, ...]) -> dict[str, dict]:
    counts: dict[str, dict] = {}
    for f in flags:
        bidder_counts = counts.setdefault(
            f.bidder, {"by_severity": {}, "by_category": {}}
        )
        bidder_counts["by_severity"][f.severity] = (
            bidder_counts["by_severity"].get(f.severity, 0) + 1
        )
        bidder_counts["by_category"][f.category] = (
            bidder_counts["by_category"].get(f.category, 0) + 1
        )
    return counts


def _top_flags(flags: tuple[Flag, ...]) -> dict[str, list[dict]]:
    """Top N per bidder — one pass per category first (so a lone
    'arithmetic' flag isn't crowded out by six 'outlier' flags), then
    backfill by severity if there's room left."""
    by_bidder: dict[str, list[Flag]] = {}
    for f in flags:
        by_bidder.setdefault(f.bidder, []).append(f)

    result: dict[str, list[dict]] = {}
    for bidder, bidder_flags in by_bidder.items():
        bidder_flags.sort(key=lambda f: SEVERITY_RANK.get(f.severity, 99))

        seen_categories: set[str] = set()
        picked: list[Flag] = []
        for f in bidder_flags:
            if f.category not in seen_categories:
                picked.append(f)
                seen_categories.add(f.category)
            if len(picked) >= TOP_FLAGS_PER_BIDDER:
                break

        if len(picked) < TOP_FLAGS_PER_BIDDER:
            for f in bidder_flags:
                if f in picked:
                    continue
                picked.append(f)
                if len(picked) >= TOP_FLAGS_PER_BIDDER:
                    break

        result[bidder] = [
            {
                "category": f.category,
                "severity": f.severity,
                "lot": f.lot,
                "item_no": f.item_no,
                "description": f.description,
                "detail": f.detail,
            }
            for f in picked
        ]
    return result


def build_report_digest(result: ComparisonResult) -> dict:
    data_gap_bidders = _data_gap_bidders(result.flags)
    return {
        "tender_no": result.tender_no,
        "round_name": result.round_name,
        "data_gap_bidders": data_gap_bidders,
        "ranked_totals": _ranked_totals(result.bidder_grand_totals, data_gap_bidders),
        "lot_totals": _lot_totals(result),
        "flag_counts": _flag_counts(result.flags),
        "top_flags": _top_flags(result.flags),
    }
