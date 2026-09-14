"""POST /api/rfqs/{rfqnum}/partial-bids -- lets an analyst mark a vendor's
entire bid on this RFQ as a deliberate partial-scope submission (they only
priced part of the BOQ on purpose), without ever writing back into
rfqvendor/quotationline. This is a whole-vendor flag, not a per-line one
(unlike disqualification) -- a partial bidder didn't fail to quote lines
by oversight, they were never expected to cover the whole scope.

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
    / "bid_analyzer_partial_bids.sql"
).read_text()


@dataclass
class PartialBidRequest:
    vendor: str
    is_partial: bool
    user_id: str
    note: str | None = None


@dataclass
class PartialBidSummary:
    vendor: str
    is_partial: bool
    note: str | None
    marked_by_label: str | None
    marked_at: str


def _iso(dt) -> str:
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


@router.post("/rfqs/{rfqnum}/partial-bids", status_code=201)
async def create_partial_bid(rfqnum: str, body: PartialBidRequest):
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

                # Confirms this vendor was actually invited on this RFQ --
                # catches typos rather than creating an orphan flag for a
                # vendor code that was never even on the roster.
                cursor.execute(
                    f"SELECT 1 FROM {CATALOG}.{SCHEMA}.rfqvendor "
                    f"WHERE RFQNUM = '{escape_sql_literal(rfqnum)}' "
                    f"AND VENDOR = '{escape_sql_literal(vendor)}' LIMIT 1"
                )
                if cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown vendor {vendor!r} on RFQNUM {rfqnum!r}",
                    )

                partial_bid_id = uuid.uuid4().hex
                marked_at = datetime.now(timezone.utc)
                marked_at_literal = marked_at.strftime("%Y-%m-%d %H:%M:%S.%f")
                note_sql = f"'{escape_sql_literal(body.note)}'" if body.note else "NULL"

                cursor.execute(_CREATE_TABLE_SQL)
                cursor.execute(
                    f"""
                    INSERT INTO {CATALOG}.{SCHEMA}.bid_analyzer_partial_bids
                        (partial_bid_id, rfqnum, vendor, is_partial, note, marked_by, marked_at)
                    VALUES (
                        '{escape_sql_literal(partial_bid_id)}',
                        '{escape_sql_literal(rfqnum)}',
                        '{escape_sql_literal(vendor)}',
                        {str(body.is_partial).upper()},
                        {note_sql},
                        '{escape_sql_literal(user_id)}',
                        TIMESTAMP '{marked_at_literal}'
                    )
                    """
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not save partial-bid flag: {exc}") from exc

    return asdict(
        PartialBidSummary(
            vendor=vendor,
            is_partial=body.is_partial,
            note=body.note,
            marked_by_label=user_row.display_name,
            marked_at=_iso(marked_at),
        )
    )
