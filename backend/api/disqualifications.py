"""POST /api/rfqs/{rfqnum}/disqualifications -- lets an analyst manually
mark a vendor's BOQ line as disqualified from commercial evaluation,
without ever writing back into quotationline or overriding Maximo's own
QL2 technical-acceptance status (backend/api/comparison.py's
DISQUALIFYING_QL2_VALUES). Add-only relative to Maximo: an analyst can
flag a line QL2 never caught, and can undo their own entry (POST again
with disqualified=false), but can never re-qualify a real QL2='TNA'
rejection -- comparison.py merges the two with an OR, so Maximo's status
always wins regardless of what's written here.

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
    / "bid_analyzer_line_disqualifications.sql"
).read_text()


@dataclass
class DisqualificationRequest:
    rfqlinenum: float
    vendor: str
    disqualified: bool
    user_id: str
    reason: str | None = None


@dataclass
class DisqualificationSummary:
    rfqlinenum: float
    vendor: str
    disqualified: bool
    reason: str | None
    disqualified_by_label: str | None
    disqualified_at: str


def _iso(dt) -> str:
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


@router.post("/rfqs/{rfqnum}/disqualifications", status_code=201)
async def create_disqualification(rfqnum: str, body: DisqualificationRequest):
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

                # Confirms this vendor actually has a real quoted line here
                # -- catches typos rather than creating an orphan entry for
                # a line/vendor combination that was never even quoted.
                cursor.execute(
                    f"SELECT 1 FROM {CATALOG}.{SCHEMA}.quotationline "
                    f"WHERE RFQNUM = '{escape_sql_literal(rfqnum)}' "
                    f"AND RFQLINENUM = {body.rfqlinenum} "
                    f"AND VENDOR = '{escape_sql_literal(vendor)}' "
                    f"AND (ORDERUNIT IS NULL OR ORDERUNIT <> 'HEADER') LIMIT 1"
                )
                if cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown line {body.rfqlinenum!r} for vendor {vendor!r} on RFQNUM {rfqnum!r}",
                    )

                disqualification_id = uuid.uuid4().hex
                disqualified_at = datetime.now(timezone.utc)
                disqualified_at_literal = disqualified_at.strftime("%Y-%m-%d %H:%M:%S.%f")
                reason_sql = f"'{escape_sql_literal(body.reason)}'" if body.reason else "NULL"

                cursor.execute(_CREATE_TABLE_SQL)
                cursor.execute(
                    f"""
                    INSERT INTO {CATALOG}.{SCHEMA}.bid_analyzer_line_disqualifications
                        (disqualification_id, rfqnum, rfqlinenum, vendor, disqualified, reason, disqualified_by, disqualified_at)
                    VALUES (
                        '{escape_sql_literal(disqualification_id)}',
                        '{escape_sql_literal(rfqnum)}',
                        {body.rfqlinenum},
                        '{escape_sql_literal(vendor)}',
                        {str(body.disqualified).upper()},
                        {reason_sql},
                        '{escape_sql_literal(user_id)}',
                        TIMESTAMP '{disqualified_at_literal}'
                    )
                    """
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not save disqualification: {exc}") from exc

    return asdict(
        DisqualificationSummary(
            rfqlinenum=body.rfqlinenum,
            vendor=vendor,
            disqualified=body.disqualified,
            reason=body.reason,
            disqualified_by_label=user_row.display_name,
            disqualified_at=_iso(disqualified_at),
        )
    )
