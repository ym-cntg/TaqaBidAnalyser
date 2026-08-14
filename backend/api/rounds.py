"""GET /api/rfqs/{rfqnum}/rounds -- round-over-round price movement
tracking, using DISCOUNTHISTORYLINE (per-line price snapshots at each
negotiation revision) layered over quotationline's original quote.

First use of DISCOUNTHISTORY/DISCOUNTHISTORYLINE in this codebase --
their fully-qualified location is assumed to match the rest of the
schema, UNVERIFIED against a real deployment. Whether each REVISION's
rows are a full snapshot of every line the vendor has priced, or only
the lines that changed at that revision, is also unverified -- handled
by forward-fill (see the reconstruction loop below) so the result is
correct either way: each revision overlays whatever rows it has onto a
running per-vendor per-line map, seeded from quotationline.LINECOST as
the "original" baseline, and the full running map is snapshotted at each
revision. In the full-snapshot case the overlay is just a no-op replace
of already-current values.

Pure read across quotationline/DISCOUNTHISTORY/DISCOUNTHISTORYLINE/
rfqvendor/companies -- no Unity Catalog write grant needed.
"""

import statistics
from dataclasses import asdict, dataclass

from fastapi import APIRouter, HTTPException

from backend.api.comparison import _fetch_vendor_roster
from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

router = APIRouter()

ORIGINAL = "original"
INCREASE_TOLERANCE = 1.0  # AED -- ignore float/rounding noise below this
PEER_DEVIATION_THRESHOLD = 4.0
PEER_MIN_SAMPLE = 3


@dataclass
class RoundPoint:
    round: str
    contract_total: float | None
    date: str | None


@dataclass
class VendorRoundTrend:
    vendor: str
    name: str | None
    points: list[RoundPoint]


@dataclass
class RoundFlag:
    severity: str  # "critical" | "warning"
    vendor: str
    rfqlinenum: float
    description: str | None
    detail: str


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _fetch_original_lines(rfqnum: str) -> dict[tuple[str, float], float]:
    """(vendor, rfqlinenum) -> original LINECOST, excluding HEADER rows."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT VENDOR, RFQLINENUM, LINECOST
                    FROM {CATALOG}.{SCHEMA}.quotationline
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                      AND (ORDERUNIT IS NULL OR ORDERUNIT <> 'HEADER')
                      AND LINECOST IS NOT NULL
                    """
                )
                return {(row.VENDOR, float(row.RFQLINENUM)): float(row.LINECOST) for row in cursor.fetchall()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Query against quotationline failed: {exc}") from exc


def _fetch_line_descriptions(rfqnum: str) -> dict[float, str]:
    """Best-effort, for flag readability only -- fail-open."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT RFQLINENUM, MIN(DESCRIPTION) AS DESCRIPTION
                    FROM {CATALOG}.{SCHEMA}.quotationline
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                      AND (ORDERUNIT IS NULL OR ORDERUNIT <> 'HEADER')
                    GROUP BY RFQLINENUM
                    """
                )
                return {float(row.RFQLINENUM): row.DESCRIPTION for row in cursor.fetchall()}
    except Exception:
        return {}


def _fetch_discount_history_lines(rfqnum: str) -> list:
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT VENDOR, REVISION, RFQLINENUM, LINECOSTWDIS
                    FROM {CATALOG}.{SCHEMA}.DISCOUNTHISTORYLINE
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                    ORDER BY REVISION ASC
                    """
                )
                return cursor.fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Query against DISCOUNTHISTORYLINE failed: {exc}"
        ) from exc


def _fetch_discount_history_dates(rfqnum: str) -> dict[tuple[str, float], str | None]:
    """(vendor, revision) -> a display date (DISCOUNT_APPLY_DATE if set,
    else ENTERDATE). Best-effort context only -- doesn't affect the trend
    itself, so failures here don't break the endpoint."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT VENDOR, REVISION, ENTERDATE, DISCOUNT_APPLY_DATE
                    FROM {CATALOG}.{SCHEMA}.DISCOUNTHISTORY
                    WHERE RFQNUM = '{escape_sql_literal(rfqnum)}'
                    """
                )
                rows = cursor.fetchall()
    except Exception:
        return {}
    out: dict[tuple[str, float], str | None] = {}
    for row in rows:
        date = row.DISCOUNT_APPLY_DATE or row.ENTERDATE
        out[(row.VENDOR, float(row.REVISION))] = _iso(date)
    return out


def build_round_trend(rfqnum: str) -> dict:
    """The round-trend payload as a plain callable, so other modules
    (e.g. negotiation_report.py) can reuse it via an in-process call
    rather than an HTTP round trip to our own API."""
    vendor_names = _fetch_vendor_roster(rfqnum)
    original_lines = _fetch_original_lines(rfqnum)
    history_rows = _fetch_discount_history_lines(rfqnum)
    history_dates = _fetch_discount_history_dates(rfqnum)

    if not original_lines and not history_rows and not vendor_names:
        raise HTTPException(status_code=404, detail=f"Unknown RFQNUM {rfqnum!r}")

    line_descriptions = _fetch_line_descriptions(rfqnum)

    revisions = sorted({float(row.REVISION) for row in history_rows})
    rounds_present = [ORIGINAL] + [str(r) for r in revisions]

    by_revision: dict[float, list] = {}
    for row in history_rows:
        by_revision.setdefault(float(row.REVISION), []).append(row)

    vendors = sorted({v for v, _ in original_lines} | {row.VENDOR for row in history_rows})

    # Forward-fill: running per-vendor per-line map, seeded from the
    # original quote, then overlaid revision by revision.
    running: dict[str, dict[float, float]] = {}
    for (v, linenum), cost in original_lines.items():
        running.setdefault(v, {})[linenum] = cost

    # snapshots[vendor][round_label] -> full per-line map as of that round
    # (absent entirely for a vendor with no data yet at that round).
    snapshots: dict[str, dict[str, dict[float, float]]] = {v: {} for v in vendors}
    for v in vendors:
        if v in running:
            snapshots[v][ORIGINAL] = dict(running[v])

    for revision in revisions:
        label = str(revision)
        for row in by_revision[revision]:
            if row.LINECOSTWDIS is None:
                continue
            running.setdefault(row.VENDOR, {})[float(row.RFQLINENUM)] = float(row.LINECOSTWDIS)
        for v in vendors:
            if v in running:
                snapshots[v][label] = dict(running[v])

    # Flags: compare consecutive present rounds, per vendor, per line.
    flags: list[RoundFlag] = []
    for i in range(len(rounds_present) - 1):
        r1, r2 = rounds_present[i], rounds_present[i + 1]

        vendor_ratios: dict[str, dict[float, float]] = {}
        for v in vendors:
            lines_r1 = snapshots[v].get(r1)
            lines_r2 = snapshots[v].get(r2)
            if lines_r1 is None or lines_r2 is None:
                continue
            ratios = {}
            for linenum, val1 in lines_r1.items():
                if linenum not in lines_r2 or val1 <= 0:
                    continue
                ratios[linenum] = lines_r2[linenum] / val1
            vendor_ratios[v] = ratios

        # Rule 1 (critical): any material round-over-round increase --
        # negotiation rounds should never raise a price.
        for v, ratios in vendor_ratios.items():
            lines_r1, lines_r2 = snapshots[v][r1], snapshots[v][r2]
            for linenum, ratio in ratios.items():
                val1, val2 = lines_r1[linenum], lines_r2[linenum]
                if val2 - val1 > INCREASE_TOLERANCE and ratio > 1.001:
                    flags.append(
                        RoundFlag(
                            severity="critical",
                            vendor=v,
                            rfqlinenum=linenum,
                            description=line_descriptions.get(linenum),
                            detail=(
                                f"Price increased from {r1} to {r2}: "
                                f"{val1:,.0f} -> {val2:,.0f} ({ratio:.2f}x) -- "
                                f"unexpected direction for a negotiation round"
                            ),
                        )
                    )

        # Rule 2 (warning): a discount far steeper than peers gave on the
        # same line between the same two rounds -- possible front/back-loading.
        by_line: dict[float, dict[str, float]] = {}
        for v, ratios in vendor_ratios.items():
            for linenum, ratio in ratios.items():
                by_line.setdefault(linenum, {})[v] = ratio

        for linenum, ratios_by_vendor in by_line.items():
            if len(ratios_by_vendor) < PEER_MIN_SAMPLE:
                continue
            peer_median = statistics.median(ratios_by_vendor.values())
            if peer_median <= 0:
                continue
            for v, ratio in ratios_by_vendor.items():
                if ratio >= 1.001:
                    continue  # increases already covered by rule 1
                if (ratio / peer_median) < 1 / PEER_DEVIATION_THRESHOLD:
                    val1, val2 = snapshots[v][r1][linenum], snapshots[v][r2][linenum]
                    flags.append(
                        RoundFlag(
                            severity="warning",
                            vendor=v,
                            rfqlinenum=linenum,
                            description=line_descriptions.get(linenum),
                            detail=(
                                f"Discounted {r1} -> {r2} by a much steeper margin "
                                f"({val1:,.0f} -> {val2:,.0f}, {ratio:.2f}x) than peers "
                                f"typically did on this line ({peer_median:.2f}x) -- "
                                f"possible front/back-loading rather than an even discount"
                            ),
                        )
                    )

    revision_by_label = {str(r): r for r in revisions}
    vendor_trends = []
    for v in vendors:
        points = []
        for label in rounds_present:
            line_map = snapshots[v].get(label)
            total = sum(line_map.values()) if line_map is not None else None
            date = None if label == ORIGINAL else history_dates.get((v, revision_by_label[label]))
            points.append(RoundPoint(round=label, contract_total=total, date=date))
        vendor_trends.append(VendorRoundTrend(vendor=v, name=vendor_names.get(v), points=points))

    return {
        "rfqnum": rfqnum,
        "rounds_present": rounds_present,
        "vendors": [asdict(v) for v in vendor_trends],
        "flags": [asdict(f) for f in flags],
    }


@router.get("/rfqs/{rfqnum}/rounds")
async def get_round_trend(rfqnum: str):
    return build_round_trend(rfqnum)
