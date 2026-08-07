"""POST /api/users/identify -- resolves "who is this" using a two-tier
strategy: a forwarded Databricks Apps identity header if one exists
(UNVERIFIED whether this platform actually sends one -- never checked in
this codebase), else a self-reported display name the frontend caches
client-side. This is NOT real authentication -- the real access gate is
already being an authorized user in TAQA's Databricks workspace, which is
required to reach this app at all.

Storage is a Unity Catalog Delta table (see
databricks/schema/bid_analyzer_users.sql) -- NOT yet writable in
production; the app's service principal has only USE CATALOG/USE
SCHEMA/SELECT today. Every call here is expected to 503 with a permission
error until that grant lands -- see databricks/FINDINGS.md.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

router = APIRouter()

_DDL_PATH = (
    Path(__file__).resolve().parent.parent.parent / "databricks" / "schema" / "bid_analyzer_users.sql"
)
_CREATE_TABLE_SQL = _DDL_PATH.read_text()

# Guessed candidates for how Databricks Apps might forward a signed-in
# user's identity -- unverified, checked live only after deploy.
_IDENTITY_HEADERS = ("X-Forwarded-Email", "X-Forwarded-Preferred-Username", "X-Forwarded-User")


def _forwarded_identity(request: Request) -> str | None:
    for header in _IDENTITY_HEADERS:
        value = request.headers.get(header)
        if value:
            return value
    return None


@dataclass
class IdentifyRequest:
    display_name: str | None = None  # self-reported fallback, from localStorage


@dataclass
class UserSummary:
    user_id: str
    display_name: str
    source: str  # "forwarded_header" | "self_reported"


def _find_user_by_email(cursor, email: str):
    cursor.execute(
        f"SELECT user_id, display_name FROM {CATALOG}.{SCHEMA}.bid_analyzer_users "
        f"WHERE email = '{escape_sql_literal(email)}' LIMIT 1"
    )
    return cursor.fetchone()


def _find_user_by_display_name(cursor, display_name: str):
    # email IS NULL keeps this namespace separate from forwarded-identity
    # users, so a self-reported name can never collide with a real one.
    cursor.execute(
        f"SELECT user_id, display_name FROM {CATALOG}.{SCHEMA}.bid_analyzer_users "
        f"WHERE LOWER(display_name) = LOWER('{escape_sql_literal(display_name)}') "
        f"AND email IS NULL LIMIT 1"
    )
    return cursor.fetchone()


def _insert_user(cursor, user_id: str, display_name: str, email: str | None, created_at: datetime) -> None:
    created_at_literal = created_at.strftime("%Y-%m-%d %H:%M:%S.%f")
    email_sql = f"'{escape_sql_literal(email)}'" if email else "NULL"
    cursor.execute(
        f"""
        INSERT INTO {CATALOG}.{SCHEMA}.bid_analyzer_users (user_id, display_name, email, created_at)
        VALUES (
            '{escape_sql_literal(user_id)}',
            '{escape_sql_literal(display_name)}',
            {email_sql},
            TIMESTAMP '{created_at_literal}'
        )
        """
    )


@router.post("/users/identify")
async def identify(body: IdentifyRequest, request: Request):
    forwarded = _forwarded_identity(request)

    if forwarded is None and (not body.display_name or not body.display_name.strip()):
        raise HTTPException(
            status_code=400,
            detail="display_name is required -- no forwarded platform identity was found on this request.",
        )

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(_CREATE_TABLE_SQL)

                if forwarded is not None:
                    existing = _find_user_by_email(cursor, forwarded)
                    if existing is not None:
                        return asdict(
                            UserSummary(
                                user_id=existing.user_id,
                                display_name=existing.display_name,
                                source="forwarded_header",
                            )
                        )
                    user_id = uuid.uuid4().hex
                    _insert_user(cursor, user_id, forwarded, forwarded, datetime.now(timezone.utc))
                    return asdict(UserSummary(user_id=user_id, display_name=forwarded, source="forwarded_header"))

                display_name = body.display_name.strip()
                existing = _find_user_by_display_name(cursor, display_name)
                if existing is not None:
                    return asdict(
                        UserSummary(
                            user_id=existing.user_id,
                            display_name=existing.display_name,
                            source="self_reported",
                        )
                    )
                user_id = uuid.uuid4().hex
                _insert_user(cursor, user_id, display_name, None, datetime.now(timezone.utc))
                return asdict(UserSummary(user_id=user_id, display_name=display_name, source="self_reported"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not identify user: {exc}"
        ) from exc
