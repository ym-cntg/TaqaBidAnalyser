"""GET /api/rfqs/{rfqnum}/comparison -- side-by-side bidder pricing per
BOQ line, plus automated commercial flags.

Round-1 scope only: uses quotationline.LINECOST/UNITCOST (the original
quote). There's no queryable round-by-round history in this data (no
round-number or change-timestamp column -- see databricks/FINDINGS.md),
only an original-vs-final snapshot (LINECOST vs LINECOSTWDIS), so this is
the only round comparison the real data actually supports right now.

Vendor names resolved via `companies` (companies.company =
rfqvendor.VENDOR) -- first use of this table in this codebase; its
fully-qualified name is assumed to match the rest of the schema and is
UNVERIFIED against a real deployment.

Pure read -- no Unity Catalog write grant needed, independent of the
Projects feature's write-blocked status.
"""

import statistics
from dataclasses import asdict, dataclass

from fastapi import APIRouter, HTTPException

from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

router = APIRouter()

LINES_CAP = 500
ARITHMETIC_TOLERANCE = 0.01
OUTLIER_DEVIATION = 0.5
OUTLIER_MIN_QUOTES = 3


@dataclass
class LinePrice:
    unit_cost: float | None
    line_cost: float | None
    unquoted: bool
    is_lowest: bool
    arithmetic_error: bool
    outlier: bool


@dataclass
class ComparisonLine:
    rfqlinenum: float
    description: str | None
    qty: float | None
    unit: str | None
    prices: dict[str, LinePrice]


@dataclass
class VendorSummary:
    vendor: str
    name: str | None
    contract_total: float
    unquoted_count: int
    arithmetic_error_count: int
    outlier_count: int


@dataclass
class NotSubmittedVendor:
    vendor: str
    name: str | None


def _fetch_vendor_roster(rfqnum: str) -> dict[str, str | None]:
    """Invited vendors for this RFQ -> resolved company name (None if
    unresolved). rfqvendor, not quotationline, is the source of truth for
    "invited" -- quotationline only shows who actually priced something."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT DISTINCT rv.VENDOR, c.name
                    FROM {CATALOG}.{SCHEMA}.rfqvendor rv
                    LEFT JOIN {CATALOG}.{SCHEMA}.companies c ON c.company = rv.VENDOR
                    WHERE rv.RFQNUM = '{escape_sql_literal(rfqnum)}'
                    """
                )
                return {row.VENDOR: row.name for row in cursor.fetchall()}
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Query against rfqvendor/companies failed: {exc}"
        ) from exc


def _fetch_quotationlines(rfqnum: str) -> list:
    # ORDERUNIT = 'HEADER' rows are non-priced section-break markers, not
    # real BOQ line items -- excluded from the comparison entirely.
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT RFQLINENUM, VENDOR, DESCRIPTION, ORDERQTY, ORDERUNIT, UNITCOST, LINECOST
                    FROM {CATALOG}.{SCHEMA}.quotationline
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                      AND (ORDERUNIT IS NULL OR ORDERUNIT <> 'HEADER')
                    """
                )
                return cursor.fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Query against quotationline failed: {exc}"
        ) from exc


@router.get("/rfqs/{rfqnum}/comparison")
async def get_comparison(rfqnum: str):
    vendor_names = _fetch_vendor_roster(rfqnum)
    rows = _fetch_quotationlines(rfqnum)

    if not rows and not vendor_names:
        raise HTTPException(status_code=404, detail=f"Unknown RFQNUM {rfqnum!r}")

    lines_by_num: dict[float, list] = {}
    for row in rows:
        lines_by_num.setdefault(row.RFQLINENUM, []).append(row)

    submitting_vendors = {row.VENDOR for row in rows}
    vendor_totals = {v: 0.0 for v in submitting_vendors}
    vendor_unquoted = {v: 0 for v in submitting_vendors}
    vendor_errors = {v: 0 for v in submitting_vendors}
    vendor_outliers = {v: 0 for v in submitting_vendors}

    all_lines: list[ComparisonLine] = []
    for linenum in sorted(lines_by_num.keys()):
        line_rows = lines_by_num[linenum]
        canonical = line_rows[0]
        by_vendor = {r.VENDOR: r for r in line_rows}

        quoted_unit_costs = [float(r.UNITCOST) for r in line_rows if r.UNITCOST is not None]
        median_unit_cost = (
            statistics.median(quoted_unit_costs) if len(quoted_unit_costs) >= OUTLIER_MIN_QUOTES else None
        )
        line_costs = [float(r.LINECOST) for r in line_rows if r.LINECOST is not None]
        min_line_cost = min(line_costs) if line_costs else None

        prices: dict[str, LinePrice] = {}
        for vendor in submitting_vendors:
            r = by_vendor.get(vendor)
            unit_cost = float(r.UNITCOST) if r is not None and r.UNITCOST is not None else None
            line_cost = float(r.LINECOST) if r is not None and r.LINECOST is not None else None
            qty = float(r.ORDERQTY) if r is not None and r.ORDERQTY is not None else None

            unquoted = unit_cost is None
            is_lowest = (
                line_cost is not None and min_line_cost is not None and line_cost == min_line_cost
            )
            arithmetic_error = (
                unit_cost is not None
                and line_cost is not None
                and qty is not None
                and abs(line_cost - qty * unit_cost) > ARITHMETIC_TOLERANCE
            )
            outlier = (
                unit_cost is not None
                and median_unit_cost is not None
                and median_unit_cost != 0
                and abs(unit_cost - median_unit_cost) / median_unit_cost > OUTLIER_DEVIATION
            )

            if unquoted:
                vendor_unquoted[vendor] += 1
            if line_cost is not None:
                vendor_totals[vendor] += line_cost
            if arithmetic_error:
                vendor_errors[vendor] += 1
            if outlier:
                vendor_outliers[vendor] += 1

            prices[vendor] = LinePrice(
                unit_cost=unit_cost,
                line_cost=line_cost,
                unquoted=unquoted,
                is_lowest=is_lowest,
                arithmetic_error=arithmetic_error,
                outlier=outlier,
            )

        all_lines.append(
            ComparisonLine(
                rfqlinenum=float(canonical.RFQLINENUM),
                description=canonical.DESCRIPTION,
                qty=float(canonical.ORDERQTY) if canonical.ORDERQTY is not None else None,
                unit=canonical.ORDERUNIT,
                prices=prices,
            )
        )

    total_line_count = len(all_lines)
    truncated = total_line_count > LINES_CAP
    returned_lines = all_lines[:LINES_CAP]

    vendors = [
        VendorSummary(
            vendor=v,
            name=vendor_names.get(v),
            contract_total=vendor_totals[v],
            unquoted_count=vendor_unquoted[v],
            arithmetic_error_count=vendor_errors[v],
            outlier_count=vendor_outliers[v],
        )
        for v in sorted(submitting_vendors)
    ]
    not_submitted = [
        NotSubmittedVendor(vendor=v, name=name)
        for v, name in sorted(vendor_names.items())
        if v not in submitting_vendors
    ]

    return {
        "rfqnum": rfqnum,
        "total_line_count": total_line_count,
        "truncated": truncated,
        "vendors": [asdict(v) for v in vendors],
        "not_submitted": [asdict(v) for v in not_submitted],
        "lines": [asdict(l) for l in returned_lines],
    }
