"""GET /api/rfqs -- searchable/filterable RFQ list, the app's landing page.

Real-schema notes (see databricks/FINDINGS.md): `rfq` spans 7 orgs across
the whole legacy group, not just ADDC, so org_id defaults to ADDCORG here.
TOTALAWVALUE is null on most rows (award totals often live at the vendor/
line level instead) -- that's expected, not a bug.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from backend.boq_classification import (
    CATEGORIES,
    NO_PRICING_DATA,
    get_cache_loaded_at,
    get_classifications,
)
from backend.db import CATALOG, SCHEMA, get_connection

router = APIRouter()

DEFAULT_ORG_ID = "ADDCORG"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _escape_sql_literal(value: str) -> str:
    """Escapes a string for safe inclusion as a single-quoted SQL literal
    (standard ANSI SQL: double up embedded single quotes)."""
    return value.replace("'", "''")


def _escape_like_pattern(value: str) -> str:
    """Escapes LIKE/ILIKE special characters. Caller wraps the result in
    '%...%' and adds ESCAPE '\\' to the query."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass
class RfqSummary:
    rfqnum: str
    description: str | None
    status: str | None
    org_id: str | None
    enter_date: str | None
    total_award_value: float | None
    boq_category: str
    vendor_count: int


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


@router.get("/rfqs")
async def list_rfqs(
    search: str | None = Query(None, min_length=1, max_length=200),
    org_id: str = Query(DEFAULT_ORG_ID),
    boq_category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    if boq_category is not None and boq_category not in CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"boq_category must be one of {list(CATEGORIES)}, got {boq_category!r}",
        )

    try:
        classifications = get_classifications()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not load BOQ classification data: {exc}"
        ) from exc

    org_scoped = org_id != "all"

    # category_counts always reflects the org filter only, never search/category,
    # so the frontend can render stable filter-option labels.
    category_counts = {c: 0 for c in CATEGORIES}
    for c in classifications.values():
        if org_scoped and c.org_id != org_id:
            continue
        category_counts[c.boq_category] += 1

    where_clauses = []
    if org_scoped:
        where_clauses.append(f"ORGID = '{_escape_sql_literal(org_id)}'")
    if search:
        escaped = _escape_sql_literal(_escape_like_pattern(search))
        where_clauses.append(
            f"(RFQNUM ILIKE '%{escaped}%' ESCAPE '\\\\' "
            f"OR DESCRIPTION ILIKE '%{escaped}%' ESCAPE '\\\\')"
        )
    if boq_category is not None:
        matching_rfqnums = [
            c.rfqnum
            for c in classifications.values()
            if c.boq_category == boq_category and (not org_scoped or c.org_id == org_id)
        ]
        if not matching_rfqnums:
            return {
                "rfqs": [],
                "total_count": 0,
                "page": page,
                "page_size": page_size,
                "category_counts": category_counts,
                "boq_stats_updated_at": _iso(
                    datetime.fromtimestamp(get_cache_loaded_at(), tz=timezone.utc)
                ),
            }
        quoted = ", ".join(f"'{_escape_sql_literal(n)}'" for n in matching_rfqnums)
        where_clauses.append(f"RFQNUM IN ({quoted})")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS n FROM {CATALOG}.{SCHEMA}.rfq {where_sql}")
                total_count = cursor.fetchone().n

                offset = (page - 1) * page_size
                cursor.execute(
                    f"""
                    SELECT RFQNUM, DESCRIPTION, STATUS, ORGID, ENTERDATE, TOTALAWVALUE
                    FROM {CATALOG}.{SCHEMA}.rfq
                    {where_sql}
                    ORDER BY ENTERDATE DESC, RFQNUM DESC
                    LIMIT {page_size} OFFSET {offset}
                    """
                )
                rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Query against rfq failed: {exc}") from exc

    rfqs = []
    for row in rows:
        classification = classifications.get(row.RFQNUM)
        rfqs.append(
            RfqSummary(
                rfqnum=row.RFQNUM,
                description=row.DESCRIPTION,
                status=row.STATUS,
                org_id=row.ORGID,
                enter_date=_iso(row.ENTERDATE),
                total_award_value=float(row.TOTALAWVALUE) if row.TOTALAWVALUE is not None else None,
                boq_category=classification.boq_category if classification else NO_PRICING_DATA,
                vendor_count=classification.vendor_count if classification else 0,
            )
        )

    return {
        "rfqs": [asdict(r) for r in rfqs],
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "category_counts": category_counts,
        "boq_stats_updated_at": _iso(datetime.fromtimestamp(get_cache_loaded_at(), tz=timezone.utc)),
    }
