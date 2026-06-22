from __future__ import annotations

import math

from src.models import (
    ExtractedBOQ,
    Finding,
    FindingCategory,
    Severity,
    TenderData,
)

ARITHMETIC_TOLERANCE = 0.01  # 1% tolerance for rounding


def validate_all(tender: TenderData) -> list[Finding]:
    findings: list[Finding] = []
    for extraction in tender.extractions:
        findings.extend(check_unquoted_items(extraction))
        findings.extend(check_arithmetic_errors(extraction))
    return findings


def check_unquoted_items(extraction: ExtractedBOQ) -> list[Finding]:
    """Flag line items where quantity exists but no price is given.

    Only flags when ALL price fields are None (not zero).
    An explicit zero is a valid price — only truly missing prices are flagged.
    """
    findings: list[Finding] = []

    for section in extraction.sections:
        for item in section.line_items:
            if not item.item_no:
                continue
            # Skip category headers (items like "1", "1.1" without qty)
            if item.qty is None or item.qty <= 0:
                continue

            # Check if ANY price field has a value (including explicit zero)
            price_fields = (
                item.cif_unit_rate, item.cif_total,
                item.erection_unit_rate, item.erection_total,
                item.total_price,
            )
            has_any_price = any(v is not None for v in price_fields)

            if not has_any_price:
                findings.append(Finding(
                    category=FindingCategory.UNQUOTED,
                    severity=Severity.HIGH,
                    bidder=extraction.bidder,
                    round=extraction.round,
                    lot=extraction.lot,
                    item_no=item.item_no,
                    message=(
                        f"Item {item.item_no} has qty={item.qty} "
                        f"but no price quoted. "
                        f"Description: {item.description[:80]}"
                    ),
                ))

    return findings


def check_arithmetic_errors(extraction: ExtractedBOQ) -> list[Finding]:
    """Check that qty * unit_rate = total for each line item."""
    findings: list[Finding] = []

    for section in extraction.sections:
        for item in section.line_items:
            if not item.item_no:
                continue

            # CIF check: qty * cif_unit_rate should = cif_total
            findings.extend(_check_product(
                extraction, item.item_no, item.description,
                item.qty, item.cif_unit_rate, item.cif_total,
                "CIF",
            ))

            # Erection check: qty * erection_unit_rate should = erection_total
            findings.extend(_check_product(
                extraction, item.item_no, item.description,
                item.qty, item.erection_unit_rate, item.erection_total,
                "Erection",
            ))

            # Total check: cif_total + erection_total should = total_price
            if (
                item.cif_total is not None
                and item.erection_total is not None
                and item.total_price is not None
            ):
                expected = item.cif_total + item.erection_total
                if expected != 0 and not math.isclose(
                    expected, item.total_price, rel_tol=ARITHMETIC_TOLERANCE
                ):
                    diff = item.total_price - expected
                    findings.append(Finding(
                        category=FindingCategory.ARITHMETIC_ERROR,
                        severity=Severity.MEDIUM,
                        bidder=extraction.bidder,
                        round=extraction.round,
                        lot=extraction.lot,
                        item_no=item.item_no,
                        message=(
                            f"Item {item.item_no}: CIF({item.cif_total:,.0f}) + "
                            f"Erection({item.erection_total:,.0f}) = "
                            f"{expected:,.0f}, but total shows "
                            f"{item.total_price:,.0f} (diff: {diff:,.0f})"
                        ),
                        value=item.total_price,
                        reference_value=expected,
                    ))

    return findings


def _check_product(
    extraction: ExtractedBOQ,
    item_no: str,
    description: str,
    qty: float | None,
    unit_rate: float | None,
    total: float | None,
    label: str,
) -> list[Finding]:
    if qty is None or unit_rate is None or total is None:
        return []
    if qty == 0 or unit_rate == 0:
        return []

    expected = qty * unit_rate
    if expected != 0 and not math.isclose(expected, total, rel_tol=ARITHMETIC_TOLERANCE):
        diff = total - expected
        return [Finding(
            category=FindingCategory.ARITHMETIC_ERROR,
            severity=Severity.MEDIUM,
            bidder=extraction.bidder,
            round=extraction.round,
            lot=extraction.lot,
            item_no=item_no,
            message=(
                f"Item {item_no} {label}: "
                f"qty({qty}) x rate({unit_rate:,.2f}) = {expected:,.0f}, "
                f"but total shows {total:,.0f} (diff: {diff:,.0f}). "
                f"Description: {description[:60]}"
            ),
            value=total,
            reference_value=expected,
        )]
    return []
