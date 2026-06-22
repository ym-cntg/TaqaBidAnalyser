from __future__ import annotations

import math
import statistics

from src.models import Finding, FindingCategory, Severity, TenderData


def detect_outliers(tender: TenderData, round_name: str) -> list[Finding]:
    """Detect price outliers at both line-item and lot-total level."""
    findings: list[Finding] = []
    findings.extend(_lot_total_outliers(tender, round_name))
    findings.extend(_line_item_outliers(tender, round_name))
    return findings


def _lot_total_outliers(tender: TenderData, round_name: str) -> list[Finding]:
    """Flag bidders whose lot totals are far from the median."""
    findings: list[Finding] = []

    for lot in tender.lots:
        totals: dict[str, float] = {}
        for bidder in tender.bidders:
            ext = tender.get_extraction(bidder, round_name, lot)
            if ext and ext.total_price is not None and ext.total_price > 0:
                totals[bidder] = ext.total_price

        if len(totals) < 3:
            continue

        median = statistics.median(totals.values())
        stdev = statistics.stdev(totals.values()) if len(totals) > 2 else 0

        for bidder, total in totals.items():
            if stdev == 0:
                continue
            z_score = (total - median) / stdev
            pct_from_median = ((total - median) / median) * 100

            if abs(z_score) > 1.5:
                direction = "above" if z_score > 0 else "below"
                severity = Severity.HIGH if abs(z_score) > 2.0 else Severity.MEDIUM

                findings.append(Finding(
                    category=FindingCategory.OUTLIER,
                    severity=severity,
                    bidder=bidder,
                    round=round_name,
                    lot=lot,
                    item_no=None,
                    message=(
                        f"{bidder} {lot} total: {total:,.0f} AED is "
                        f"{abs(pct_from_median):.0f}% {direction} median "
                        f"({median:,.0f} AED). Z-score: {z_score:.1f}"
                    ),
                    value=total,
                    reference_value=median,
                ))

    return findings


def _line_item_outliers(tender: TenderData, round_name: str) -> list[Finding]:
    """Flag individual line items that deviate significantly from peers."""
    findings: list[Finding] = []

    for lot in tender.lots:
        # Collect all item numbers across bidders
        item_prices: dict[str, dict[str, float]] = {}

        for bidder in tender.bidders:
            ext = tender.get_extraction(bidder, round_name, lot)
            if ext is None:
                continue

            for item in ext.all_line_items:
                if not item.item_no or item.total_price is None or item.total_price <= 0:
                    continue

                if item.item_no not in item_prices:
                    item_prices[item.item_no] = {}
                item_prices[item.item_no][bidder] = item.total_price

        for item_no, bidder_prices in item_prices.items():
            if len(bidder_prices) < 3:
                continue

            values = list(bidder_prices.values())
            median = statistics.median(values)
            if median == 0:
                continue

            stdev = statistics.stdev(values) if len(values) > 2 else 0
            if stdev == 0:
                continue

            for bidder, price in bidder_prices.items():
                z_score = (price - median) / stdev
                if abs(z_score) > 2.0:
                    pct = ((price - median) / median) * 100
                    direction = "above" if z_score > 0 else "below"
                    findings.append(Finding(
                        category=FindingCategory.OUTLIER,
                        severity=Severity.MEDIUM,
                        bidder=bidder,
                        round=round_name,
                        lot=lot,
                        item_no=item_no,
                        message=(
                            f"Item {item_no}: {price:,.0f} AED is "
                            f"{abs(pct):.0f}% {direction} median "
                            f"({median:,.0f} AED)"
                        ),
                        value=price,
                        reference_value=median,
                    ))

    return findings
