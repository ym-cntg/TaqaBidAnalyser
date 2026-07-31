"""FastAPI application entry point.

Bare-bones deployment/connectivity test: does a deployed app reach the real
Maximo data in Unity Catalog? Nothing else yet -- see databricks/FINDINGS.md
for what's been learned about the underlying schema so far.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from databricks import sql
from databricks.sdk.core import Config

CATALOG = "ingestion_framework_test"
SCHEMA = "bid_data_exploration"

app = FastAPI(
    title="TAQA Maximo Integration — Deployment Test",
    description="Bare-bones connectivity check between a deployed app and the real Maximo Unity Catalog tables",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection():
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    if not http_path:
        raise RuntimeError(
            "DATABRICKS_HTTP_PATH is not set. Find it under the target SQL "
            "warehouse's 'Connection details' tab in the Databricks UI."
        )

    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        # Explicit personal access token -- simplest path for local dev.
        server_hostname = os.environ["DATABRICKS_SERVER_HOSTNAME"]
        return sql.connect(
            server_hostname=server_hostname,
            http_path=http_path,
            access_token=token,
        )

    # No token set -- fall back to the Databricks SDK's default credential
    # chain (a configured CLI profile locally, or auto-injected credentials
    # when running as a Databricks App). This is the path a real deployment
    # is expected to use.
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/rfq-count")
async def rfq_count():
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.rfq")
                row = cursor.fetchone()
                return {"row_count": row.row_count, "catalog": CATALOG, "schema": SCHEMA}
    except Exception as exc:
        return {"error": str(exc), "catalog": CATALOG, "schema": SCHEMA}
