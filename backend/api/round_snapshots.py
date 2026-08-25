"""Shared round-snapshot construction: forward-fills DISCOUNTHISTORYLINE's
per-revision price changes over quotationline's original quote into a
full per-vendor per-line map at every round. If a given (vendor, line)
was never revised at some round, it simply carries forward its last
known value -- exactly the semantics both rounds.py's trend chart and
comparison.py's round-scoped BOQ comparison need.

Lives in its own module, not inside either of theirs, specifically to
avoid a circular import: rounds.py already imports comparison.py's
_fetch_vendor_roster, so comparison.py can't also import from rounds.py.
"""

from fastapi import HTTPException

from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

ORIGINAL = "original"


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


def build_round_snapshots(rfqnum: str) -> dict:
    """Returns {"rounds_present": ["original", "1.0", ...], "snapshots":
    {vendor: {round_label: {rfqlinenum: line_cost}}}, "vendors": [...],
    "revisions": [float, ...]}.

    "snapshots[v]" has no entry at all for a round before v's first real
    price appears (never seeded, never revised yet) -- callers treat that
    as "no data for this vendor at this round", not zero.
    """
    original_lines = _fetch_original_lines(rfqnum)
    history_rows = _fetch_discount_history_lines(rfqnum)

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

    return {
        "rounds_present": rounds_present,
        "snapshots": snapshots,
        "vendors": vendors,
        "revisions": revisions,
    }
