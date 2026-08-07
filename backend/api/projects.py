"""GET/POST /api/projects -- the Projects registry, the app's new landing
page. Each project maps to exactly one existing RFQ (many-to-one is fine:
many projects can point at the same RFQ) and to exactly one user (see
backend/api/users.py for how "user" is resolved without real auth).

Storage is a Unity Catalog Delta table (see
databricks/schema/bid_analyzer_projects.sql) -- NOT yet writable in
production; the app's service principal has only USE CATALOG/USE
SCHEMA/SELECT today. POST /api/projects is expected to 503 with a
permission error until that grant lands -- see databricks/FINDINGS.md.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.boq_classification import MIN_BOQ_LINE_ITEMS, get_classifications
from backend.db import CATALOG, SCHEMA, escape_sql_literal, get_connection

router = APIRouter()

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "databricks" / "schema"
_CREATE_TABLE_SQL = (_SCHEMA_DIR / "bid_analyzer_projects.sql").read_text()
_USERS_CREATE_TABLE_SQL = (_SCHEMA_DIR / "bid_analyzer_users.sql").read_text()


@dataclass
class ProjectCreateRequest:
    name: str
    rfqnum: str
    user_id: str


@dataclass
class ProjectSummary:
    project_id: str
    user_id: str
    user_display_name: str | None
    name: str
    rfqnum: str
    created_at: str
    rfq_description: str | None
    rfq_status: str | None
    org_id: str | None
    boq_category: str | None
    vendor_count: int | None


def _iso(dt) -> str:
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _fetch_rfq_headers(rfqnums: set[str]) -> dict[str, object]:
    if not rfqnums:
        return {}
    quoted = ", ".join(f"'{escape_sql_literal(n)}'" for n in rfqnums)
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT RFQNUM, DESCRIPTION, STATUS, ORGID FROM {CATALOG}.{SCHEMA}.rfq "
                    f"WHERE RFQNUM IN ({quoted})"
                )
                return {row.RFQNUM: row for row in cursor.fetchall()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Query against rfq failed: {exc}") from exc


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
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Query against bid_analyzer_users failed: {exc}"
        ) from exc


def _build_summary(
    *,
    project_id: str,
    user_id: str,
    user_display_name: str | None,
    name: str,
    rfqnum: str,
    created_at,
    rfq_headers: dict,
    classifications: dict,
) -> ProjectSummary:
    rfq = rfq_headers.get(rfqnum)
    c = classifications.get(rfqnum)
    return ProjectSummary(
        project_id=project_id,
        user_id=user_id,
        user_display_name=user_display_name,
        name=name,
        rfqnum=rfqnum,
        created_at=_iso(created_at),
        rfq_description=rfq.DESCRIPTION if rfq else None,
        rfq_status=rfq.STATUS if rfq else None,
        org_id=rfq.ORGID if rfq else (c.org_id if c else None),
        boq_category=c.boq_category if c else None,
        vendor_count=c.vendor_count if c else None,
    )


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreateRequest):
    name = body.name.strip()
    rfqnum = body.rfqnum.strip()
    user_id = body.user_id.strip()

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        classifications = get_classifications()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not load BOQ classification data: {exc}"
        ) from exc

    classification = classifications.get(rfqnum)
    in_scope = (
        classification is not None
        and classification.avg_lines_per_vendor is not None
        and classification.avg_lines_per_vendor > MIN_BOQ_LINE_ITEMS
    )
    if not in_scope:
        raise HTTPException(
            status_code=400,
            detail=(
                f"rfqnum {rfqnum!r} does not exist or has no real BOQ to compare "
                f"(must have more than {MIN_BOQ_LINE_ITEMS} line items per vendor)."
            ),
        )

    project_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc)
    created_at_literal = created_at.strftime("%Y-%m-%d %H:%M:%S.%f")

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # Defensive: the users table should already exist (the
                # frontend always calls POST /api/users/identify before
                # this), but this is the write path, so it's cheap insurance.
                cursor.execute(_USERS_CREATE_TABLE_SQL)
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

                cursor.execute(_CREATE_TABLE_SQL)
                cursor.execute(
                    f"""
                    INSERT INTO {CATALOG}.{SCHEMA}.bid_analyzer_projects
                        (project_id, user_id, name, rfqnum, created_at)
                    VALUES (
                        '{escape_sql_literal(project_id)}',
                        '{escape_sql_literal(user_id)}',
                        '{escape_sql_literal(name)}',
                        '{escape_sql_literal(rfqnum)}',
                        TIMESTAMP '{created_at_literal}'
                    )
                    """
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not create project (grant may not be applied yet): {exc}"
        ) from exc

    rfq_headers = _fetch_rfq_headers({rfqnum})
    return asdict(
        _build_summary(
            project_id=project_id,
            user_id=user_id,
            user_display_name=user_row.display_name,
            name=name,
            rfqnum=rfqnum,
            created_at=created_at,
            rfq_headers=rfq_headers,
            classifications=classifications,
        )
    )


@router.get("/projects")
async def list_projects(user_id: str | None = Query(None)):
    where_sql = f"WHERE user_id = '{escape_sql_literal(user_id)}'" if user_id else ""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT project_id, user_id, name, rfqnum, created_at "
                    f"FROM {CATALOG}.{SCHEMA}.bid_analyzer_projects {where_sql} "
                    f"ORDER BY created_at DESC"
                )
                project_rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not load projects (grant may not be applied yet): {exc}"
        ) from exc

    try:
        classifications = get_classifications()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not load BOQ classification data: {exc}"
        ) from exc

    rfq_headers = _fetch_rfq_headers({p.rfqnum for p in project_rows})
    user_names = _fetch_user_names({p.user_id for p in project_rows})

    projects = [
        _build_summary(
            project_id=p.project_id,
            user_id=p.user_id,
            user_display_name=user_names.get(p.user_id),
            name=p.name,
            rfqnum=p.rfqnum,
            created_at=p.created_at,
            rfq_headers=rfq_headers,
            classifications=classifications,
        )
        for p in project_rows
    ]
    return {"projects": [asdict(p) for p in projects]}


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: str):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT project_id, user_id, name, rfqnum, created_at "
                    f"FROM {CATALOG}.{SCHEMA}.bid_analyzer_projects "
                    f"WHERE project_id = '{escape_sql_literal(project_id)}' LIMIT 1"
                )
                row = cursor.fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not load project (grant may not be applied yet): {exc}"
        ) from exc

    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown project {project_id!r}")

    try:
        classifications = get_classifications()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not load BOQ classification data: {exc}"
        ) from exc

    rfq_headers = _fetch_rfq_headers({row.rfqnum})
    user_names = _fetch_user_names({row.user_id})

    return asdict(
        _build_summary(
            project_id=row.project_id,
            user_id=row.user_id,
            user_display_name=user_names.get(row.user_id),
            name=row.name,
            rfqnum=row.rfqnum,
            created_at=row.created_at,
            rfq_headers=rfq_headers,
            classifications=classifications,
        )
    )
