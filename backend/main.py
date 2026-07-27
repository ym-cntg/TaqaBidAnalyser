"""FastAPI application entry point."""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .api.projects import router as projects_router
from .api.documents import router as documents_router
from .api.workflow import router as workflow_router

app = FastAPI(
    title="TAQA Bid Analyzer",
    description="AI-driven commercial bid analysis for TAQA/ADDC procurement",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(workflow_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
