"""POST /api/rfqs/{rfqnum}/corrections -- lets a user manually correct or
fill in a vendor's price for a BOQ line, without ever writing back into
the real Maximo-ingested `quotationline` table. Corrections are stored as
an append-only overlay (see
databricks/schema/bid_analyzer_price_corrections.sql) and applied at
display time by backend/api/comparison.py's overlay logic.

Storage is a Unity Catalog Delta table -- NOT yet writable in production
until the CREATE TABLE/INSERT grant lands; see databricks/FINDINGS.md.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

router = APIRouter()

_CREATE_TABLE_SQL = (
    Path(__file__).resolve().parent.parent.parent
    / "databricks"
    / "schema"
    / "bid_analyzer_price_corrections.sql"
).read_text()


@dataclass
class CorrectionCreateRequest:
    rfqlinenum: float
    vendor: str
    unit_cost: float
    user_id: str
    note: str | None = None


@dataclass
class CorrectionSummary:
    rfqlinenum: float
    vendor: str
    unit_cost: float
    line_cost: float | None
    note: str | None
    corrected_by_label: str | None
    corrected_at: str


def _iso(dt) -> str:
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


@router.post("/rfqs/{rfqnum}/corrections", status_code=201)
async def create_correction(rfqnum: str, body: CorrectionCreateRequest):
    if body.unit_cost < 0:
        raise HTTPException(status_code=400, detail="unit_cost must be >= 0")

    user_id = body.user_id.strip()
    vendor = body.vendor.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not vendor:
        raise HTTPException(status_code=400, detail="vendor is required")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT display_name FROM {CATALOG}.{SCHEMA}.bid_analyzer_users "
                    f"WHERE user_id = '{escape_sql_literal(user_id)}' LIMIT 1"
                )
                user_row = cursor.fetchone()
                if user_row is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Unknown user_id {user_id!r} -- call POST /api/users/identify first.",
                    )

                # Real, non-header line -- also gives the canonical qty
                # needed to echo back a line_cost.
                cursor.execute(
                    f"SELECT ORDERQTY FROM {CATALOG}.{SCHEMA}.quotationline "
                    f"WHERE RFQNUM = '{escape_sql_literal(rfqnum)}' "
                    f"AND RFQLINENUM = {body.rfqlinenum} "
                    f"AND (ORDERUNIT IS NULL OR ORDERUNIT <> 'HEADER') LIMIT 1"
                )
                line_row = cursor.fetchone()
                if line_row is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown line {body.rfqlinenum!r} for RFQNUM {rfqnum!r}",
                    )
                qty = float(line_row.ORDERQTY) if line_row.ORDERQTY is not None else None

                # Catches typos rather than creating an orphan correction
                # for a vendor that was never even invited.
                cursor.execute(
                    f"SELECT 1 FROM {CATALOG}.{SCHEMA}.rfqvendor "
                    f"WHERE RFQNUM = '{escape_sql_literal(rfqnum)}' "
                    f"AND VENDOR = '{escape_sql_literal(vendor)}' LIMIT 1"
                )
                if cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Vendor {vendor!r} was not invited to RFQNUM {rfqnum!r}",
                    )

                correction_id = uuid.uuid4().hex
                corrected_at = datetime.now(timezone.utc)
                corrected_at_literal = corrected_at.strftime("%Y-%m-%d %H:%M:%S.%f")
                note_sql = f"'{escape_sql_literal(body.note)}'" if body.note else "NULL"

                cursor.execute(_CREATE_TABLE_SQL)
                cursor.execute(
                    f"""
                    INSERT INTO {CATALOG}.{SCHEMA}.bid_analyzer_price_corrections
                        (correction_id, rfqnum, rfqlinenum, vendor, unit_cost, note, corrected_by, corrected_at)
                    VALUES (
                        '{escape_sql_literal(correction_id)}',
                        '{escape_sql_literal(rfqnum)}',
                        {body.rfqlinenum},
                        '{escape_sql_literal(vendor)}',
                        {body.unit_cost},
                        {note_sql},
                        '{escape_sql_literal(user_id)}',
                        TIMESTAMP '{corrected_at_literal}'
                    )
                    """
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not save correction: {exc}") from exc

    return asdict(
        CorrectionSummary(
            rfqlinenum=body.rfqlinenum,
            vendor=vendor,
            unit_cost=body.unit_cost,
            line_cost=(qty * body.unit_cost) if qty is not None else None,
            note=body.note,
            corrected_by_label=user_row.display_name,
            corrected_at=_iso(corrected_at),
        )
    )
