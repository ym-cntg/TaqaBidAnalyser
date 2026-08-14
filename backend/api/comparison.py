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

Manual price corrections (backend/api/corrections.py,
bid_analyzer_price_corrections) are overlaid on top of the raw
quotationline data here at display time -- never written back into
quotationline itself. Corrections are trusted: a corrected cell is
excluded from arithmetic_error/outlier/zero_price flagging (it's already
been reviewed by a person) but still fully participates in is_lowest and
contract_total, since that's the point of correcting it.

Pure read of quotationline/rfqvendor/companies -- no Unity Catalog write
grant needed for the comparison itself, independent of the Projects
feature's write-blocked status. The corrections *overlay* fetch is a
read too; only backend/api/corrections.py writes.
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
    zero_price: bool
    corrected: bool
    corrected_by_label: str | None
    corrected_note: str | None
    corrected_at: str | None


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
    zero_price_count: int


@dataclass
class NotSubmittedVendor:
    vendor: str
    name: str | None


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


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


def _fetch_corrections(rfqnum: str) -> dict[tuple[float, str], object]:
    """Latest correction per (rfqlinenum, vendor), or {} if the
    corrections table doesn't exist yet (nobody has corrected anything,
    or the write grant isn't applied). Deliberately swallowed here --
    the read-only comparison view must keep working regardless; a broken
    write path elsewhere shouldn't take down a working read path."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT rfqlinenum, vendor, unit_cost, note, corrected_by, corrected_at
                    FROM {CATALOG}.{SCHEMA}.bid_analyzer_price_corrections
                    WHERE rfqnum = '{escape_sql_literal(rfqnum)}'
                    ORDER BY corrected_at ASC
                    """
                )
                rows = cursor.fetchall()
    except Exception:
        return {}

    latest: dict[tuple[float, str], object] = {}
    for row in rows:
        latest[(row.rfqlinenum, row.vendor)] = row  # ASC order -> last write wins
    return latest


def _fetch_user_names(user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    quoted = ", ".join(f"'{escape_sql_literal(u)}'" for u in user_ids)
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT user_id, display_name FROM {CATALOG}.{SCHEMA}.bid_analyzer_users "
                    f"WHERE user_id IN ({quoted})"
                )
                return {row.user_id: row.display_name for row in cursor.fetchall()}
    except Exception:
        return {}


def build_comparison(rfqnum: str) -> dict:
    """The comparison payload as a plain callable, so other modules (e.g.
    negotiation_report.py) can reuse it via an in-process call rather than
    an HTTP round trip to our own API."""
    vendor_names = _fetch_vendor_roster(rfqnum)
    rows = _fetch_quotationlines(rfqnum)

    if not rows and not vendor_names:
        raise HTTPException(status_code=404, detail=f"Unknown RFQNUM {rfqnum!r}")

    corrections = _fetch_corrections(rfqnum)
    corrector_names = _fetch_user_names({c.corrected_by for c in corrections.values()})

    lines_by_num: dict[float, list] = {}
    for row in rows:
        lines_by_num.setdefault(row.RFQLINENUM, []).append(row)

    submitting_vendors = {row.VENDOR for row in rows}
    vendor_totals = {v: 0.0 for v in submitting_vendors}
    vendor_unquoted = {v: 0 for v in submitting_vendors}
    vendor_errors = {v: 0 for v in submitting_vendors}
    vendor_outliers = {v: 0 for v in submitting_vendors}
    vendor_zero_price = {v: 0 for v in submitting_vendors}

    all_lines: list[ComparisonLine] = []
    for linenum in sorted(lines_by_num.keys()):
        line_rows = lines_by_num[linenum]
        canonical = line_rows[0]
        by_vendor = {r.VENDOR: r for r in line_rows}
        canonical_qty = float(canonical.ORDERQTY) if canonical.ORDERQTY is not None else None

        # Pass 1: resolve each vendor's (unit_cost, line_cost), applying a
        # correction override if one exists for this (line, vendor).
        resolved: dict[str, dict] = {}
        for vendor in submitting_vendors:
            r = by_vendor.get(vendor)
            unit_cost = float(r.UNITCOST) if r is not None and r.UNITCOST is not None else None
            line_cost = float(r.LINECOST) if r is not None and r.LINECOST is not None else None
            qty = float(r.ORDERQTY) if r is not None and r.ORDERQTY is not None else None

            correction = corrections.get((linenum, vendor))
            corrected = correction is not None
            corrected_by_label = None
            corrected_note = None
            corrected_at = None
            if correction is not None:
                unit_cost = float(correction.unit_cost)
                line_cost = unit_cost * canonical_qty if canonical_qty is not None else None
                corrected_by_label = corrector_names.get(correction.corrected_by, correction.corrected_by)
                corrected_note = correction.note
                corrected_at = _iso(correction.corrected_at)

            resolved[vendor] = dict(
                unit_cost=unit_cost,
                line_cost=line_cost,
                qty=qty,
                corrected=corrected,
                corrected_by_label=corrected_by_label,
                corrected_note=corrected_note,
                corrected_at=corrected_at,
            )

        # Pass 2: aggregates over resolved values, excluding zero-priced
        # and unquoted cells -- neither is a real basis for "lowest" or
        # a meaningful outlier median.
        real_unit_costs = [
            v["unit_cost"] for v in resolved.values() if v["unit_cost"] is not None and v["unit_cost"] != 0
        ]
        median_unit_cost = (
            statistics.median(real_unit_costs) if len(real_unit_costs) >= OUTLIER_MIN_QUOTES else None
        )
        real_line_costs = [
            v["line_cost"] for v in resolved.values() if v["line_cost"] is not None and v["line_cost"] != 0
        ]
        min_line_cost = min(real_line_costs) if real_line_costs else None

        prices: dict[str, LinePrice] = {}
        for vendor, v in resolved.items():
            unit_cost = v["unit_cost"]
            line_cost = v["line_cost"]
            qty = v["qty"]
            corrected = v["corrected"]

            unquoted = unit_cost is None
            zero_price = (not corrected) and unit_cost is not None and unit_cost == 0
            is_lowest = (
                line_cost is not None
                and line_cost != 0
                and min_line_cost is not None
                and line_cost == min_line_cost
            )
            arithmetic_error = (
                not corrected
                and unit_cost is not None
                and line_cost is not None
                and qty is not None
                and abs(line_cost - qty * unit_cost) > ARITHMETIC_TOLERANCE
            )
            outlier = (
                not corrected
                and unit_cost is not None
                and unit_cost != 0
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
            if zero_price:
                vendor_zero_price[vendor] += 1

            prices[vendor] = LinePrice(
                unit_cost=unit_cost,
                line_cost=line_cost,
                unquoted=unquoted,
                is_lowest=is_lowest,
                arithmetic_error=arithmetic_error,
                outlier=outlier,
                zero_price=zero_price,
                corrected=corrected,
                corrected_by_label=v["corrected_by_label"],
                corrected_note=v["corrected_note"],
                corrected_at=v["corrected_at"],
            )

        all_lines.append(
            ComparisonLine(
                rfqlinenum=float(canonical.RFQLINENUM),
                description=canonical.DESCRIPTION,
                qty=canonical_qty,
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
            zero_price_count=vendor_zero_price[v],
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


@router.get("/rfqs/{rfqnum}/comparison")
async def get_comparison(rfqnum: str):
    return build_comparison(rfqnum)
