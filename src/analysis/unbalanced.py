from __future__ import annotations

import statistics

from src.models import Finding, FindingCategory, Severity, TenderData


def detect_unbalanced_bidding(tender: TenderData, round_name: str) -> list[Finding]:
    """Detect front-loading: abnormal CIF/Erection cost split.

    Unbalanced bidding = a bidder loads cost onto early-delivery items
    (CIF/supply) while keeping erection costs low, to get paid sooner.
    """
    findings: list[Finding] = []

    for lot in tender.lots:
        bidder_ratios: dict[str, float] = {}

        for bidder in tender.bidders:
            ext = tender.get_extraction(bidder, round_name, lot)
            if ext is None:
                continue

            total_cif = 0.0
            total_erection = 0.0

            for item in ext.all_line_items:
                if item.cif_total is not None:
                    total_cif += item.cif_total
                if item.erection_total is not None:
                    total_erection += item.erection_total

            if total_erection > 0:
                bidder_ratios[bidder] = total_cif / total_erection
            elif total_cif > 0:
                # All cost in CIF, none in erection — extreme front-loading
                bidder_ratios[bidder] = float("inf")

        if len(bidder_ratios) < 3:
            continue

        # Filter out inf for stats
        finite_ratios = {b: r for b, r in bidder_ratios.items() if r != float("inf")}
        if len(finite_ratios) < 2:
            continue

        median_ratio = statistics.median(finite_ratios.values())

        for bidder, ratio in bidder_ratios.items():
            if ratio == float("inf"):
                findings.append(Finding(
                    category=FindingCategory.UNBALANCED,
                    severity=Severity.HIGH,
                    bidder=bidder,
                    round=round_name,
                    lot=lot,
                    item_no=None,
                    message=(
                        f"{bidder} {lot}: 100% CIF / 0% Erection. "
                        f"All costs front-loaded to supply. "
                        f"Peer median CIF:Erection ratio is {median_ratio:.1f}:1"
                    ),
                ))
                continue

            # Flag if ratio deviates more than 3x from median
            if median_ratio > 0 and ratio / median_ratio > 3:
                findings.append(Finding(
                    category=FindingCategory.UNBALANCED,
                    severity=Severity.HIGH,
                    bidder=bidder,
                    round=round_name,
                    lot=lot,
                    item_no=None,
                    message=(
                        f"{bidder} {lot}: CIF:Erection ratio is {ratio:.1f}:1, "
                        f"vs peer median {median_ratio:.1f}:1. "
                        f"Significantly front-loaded supply costs."
                    ),
                    value=ratio,
                    reference_value=median_ratio,
                ))
            elif median_ratio > 0 and ratio / median_ratio < 0.33:
                findings.append(Finding(
                    category=FindingCategory.UNBALANCED,
                    severity=Severity.MEDIUM,
                    bidder=bidder,
                    round=round_name,
                    lot=lot,
                    item_no=None,
                    message=(
                        f"{bidder} {lot}: CIF:Erection ratio is {ratio:.1f}:1, "
                        f"vs peer median {median_ratio:.1f}:1. "
                        f"Unusually high erection costs relative to CIF."
                    ),
                    value=ratio,
                    reference_value=median_ratio,
                ))

    return findings
