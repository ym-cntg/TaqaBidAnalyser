"""FastAPI application entry point."""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.projects import router as projects_router
from backend.api.rfqs import router as rfqs_router
from backend.api.users import router as users_router
from backend.db import CATALOG, SCHEMA, get_connection

app = FastAPI(
    title="TAQA Maximo Integration",
    description="Bid-analysis app built against real Maximo data in Unity Catalog",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rfqs_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(projects_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/rfq-count")
async def rfq_count():
    """Kept as a lightweight, UI-independent connectivity smoke test --
    no longer linked from the frontend now that / is the Projects landing
    page (RFQ browse moved to /rfqs), but still useful for a fast health
    check distinct from either."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.rfq")
                row = cursor.fetchone()
                return {"row_count": row.row_count, "catalog": CATALOG, "schema": SCHEMA}
    except Exception as exc:
        return {"error": str(exc), "catalog": CATALOG, "schema": SCHEMA}
