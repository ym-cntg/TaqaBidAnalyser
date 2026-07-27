"""Project registry — the top-level unit of work in this app.

A project wraps one tender's bidder data (a folder under `data/`) plus
everything built on top of it: document selection, the BOQ template
workflow, comparison/analysis, close-out. Projects are what a user picks
from the Projects page after logging in, so more than one bid can be
worked on at a time — this replaces the two hardcoded tenders that used
to live directly in `tenders.py`.

Persisted (unlike the extraction/report caches) — creating or deleting a
project is a real, durable action, not a review-session artifact.

**Only the seeded "D-111808 — Power" project has a working extraction
pipeline.** The comparison/insights/rounds/report endpoints in `routes.py`
are still internally hardcoded to that BOQ template's shape (CIF/Erection
columns, ADDC item numbering) — `get_power_project_root()` exists so that
hardcoding at least follows the registry (rename/move the seed project and
analysis keeps working) rather than a bare path literal, but it does not
make analysis generic. Every other project — the seeded water tender and
anything created here — gets real document curation (`documents.py`) and
an honest `analysis_ready: false`, not a pretend-generic parser.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent.parent / "data"
STATE_DIR = Path(__file__).parent.parent.parent / "backend" / "state"
PROJECTS_FILE = STATE_DIR / "projects.json"
SELECTIONS_FILE = STATE_DIR / "selections.json"

SEED_PROJECTS = [
    {
        "id": "power-d111808",
        "name": "D-111808 — Power (Eastern Region Substations)",
        "tender_no": "D-111808",
        "description": "Construction of 3 primary substations in Eastern Region (SHBPRY, DRPRY, SMHPRY).",
        "root": "power",
        "analysis_ready": True,
        "created_by": "seed",
        "created_at": "2026-07-06T00:00:00+00:00",
    },
    {
        "id": "water-a20669",
        "name": "A-20669 — Water",
        "tender_no": "A-20669",
        "description": "Water network bid — BOQ format not yet mapped to the extraction pipeline.",
        "root": "water/A-20669",
        "analysis_ready": False,
        "created_by": "seed",
        "created_at": "2026-07-20T00:00:00+00:00",
    },
]


def _load_projects() -> list[dict]:
    if not PROJECTS_FILE.exists():
        _save_projects(SEED_PROJECTS)
        return [dict(p) for p in SEED_PROJECTS]
    try:
        data = json.loads(PROJECTS_FILE.read_text())
        return data.get("projects", [])
    except (json.JSONDecodeError, OSError):
        return [dict(p) for p in SEED_PROJECTS]


def _save_projects(projects: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(json.dumps({"projects": projects}, indent=2))


def get_project(project_id: str) -> dict | None:
    """Used by documents.py and workflow.py so neither needs its own copy
    of the registry."""
    for p in _load_projects():
        if p["id"] == project_id:
            return p
    return None


def get_project_root(project_id: str) -> Path | None:
    p = get_project(project_id)
    return (DATA_DIR / p["root"]) if p else None


def get_power_project_root() -> Path:
    """The one project the extraction/analysis pipeline actually
    understands — see module docstring. Falls back to the literal seed
    path if that project record was ever deleted, so /sample/* doesn't
    hard-fail."""
    for p in _load_projects():
        if p.get("analysis_ready"):
            return DATA_DIR / p["root"]
    return DATA_DIR / "power"


def _count_selected(project_id: str) -> int:
    if not SELECTIONS_FILE.exists():
        return 0
    try:
        data = json.loads(SELECTIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    return sum(len(v) for v in data.get(project_id, {}).values())


def _bidder_file_count(root: Path) -> tuple[int, int]:
    if not root.exists():
        return 0, 0
    bidder_dirs = [d for d in root.iterdir() if d.is_dir()]
    file_count = sum(
        1 for d in bidder_dirs for f in d.rglob("*") if f.is_file() and not f.name.startswith(".")
    )
    return len(bidder_dirs), file_count


def _serialize(p: dict) -> dict:
    root = DATA_DIR / p["root"]
    bidder_count, file_count = _bidder_file_count(root)
    return {
        **p,
        "bidder_count": bidder_count,
        "file_count": file_count,
        "selected_count": _count_selected(p["id"]),
        "exists": root.exists(),
    }


def _looks_like_bidder_root(path: Path) -> bool:
    """A directory qualifies as a project root if it directly contains at
    least one subdirectory that itself directly contains at least one real
    (non-hidden) file — i.e. exactly the 'root/bidder/file' shape.

    Deliberately one level of recursion, not an unbounded rglob: an
    unbounded check can't tell a genuine bidder-collection root from one
    of its own bidder folders (a bidder folder containing round
    sub-folders containing files looks structurally identical to a root
    containing bidder folders containing files — the same shape repeats).
    This also naturally excludes `data/Template Structure/`, a reference
    layout with no real files in it at all."""
    if not path.is_dir():
        return False
    return any(
        child.is_dir()
        and any(f.is_file() and not f.name.startswith(".") for f in child.iterdir())
        for child in path.iterdir()
    )


@router.get("/projects")
async def list_projects():
    return [_serialize(p) for p in _load_projects()]


@router.get("/projects/discoverable-roots")
async def discoverable_roots():
    """Folders under data/ that look like a bidder collection and aren't
    already claimed by an existing project — powers the 'pick a folder'
    step of project creation."""
    if not DATA_DIR.exists():
        return []
    claimed = {p["root"] for p in _load_projects()}
    candidates: list[str] = []
    for entry in sorted(DATA_DIR.iterdir()):
        if not entry.is_dir() or entry.name in claimed:
            continue
        if _looks_like_bidder_root(entry):
            candidates.append(entry.name)
            continue  # already a match at this level -- don't also list its children
        for sub in sorted(entry.iterdir()):
            if not sub.is_dir():
                continue
            rel = f"{entry.name}/{sub.name}"
            if rel not in claimed and _looks_like_bidder_root(sub):
                candidates.append(rel)
    return candidates


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, f"Unknown project '{project_id}'")
    return _serialize(p)


class ProjectCreateRequest(BaseModel):
    name: str
    tender_no: str
    description: str = ""
    root: str  # relative to data/
    created_by: str = ""


@router.post("/projects")
async def create_project(body: ProjectCreateRequest):
    if not body.name.strip() or not body.root.strip():
        raise HTTPException(400, "name and root are required")

    data_dir_resolved = DATA_DIR.resolve()
    root_path = (DATA_DIR / body.root).resolve()
    if root_path != data_dir_resolved and data_dir_resolved not in root_path.parents:
        raise HTTPException(400, "root must be inside the data directory")
    if not root_path.is_dir():
        raise HTTPException(400, f"'{body.root}' is not a valid directory under data/")

    projects = _load_projects()
    if any(p["root"] == body.root for p in projects):
        raise HTTPException(409, f"A project already uses root '{body.root}'")

    project = {
        "id": uuid.uuid4().hex[:8],
        "name": body.name.strip(),
        "tender_no": body.tender_no.strip(),
        "description": body.description.strip(),
        "root": body.root,
        "analysis_ready": False,
        "created_by": body.created_by.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    projects.append(project)
    _save_projects(projects)
    return _serialize(project)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Removes the project record only — never touches files under data/."""
    projects = _load_projects()
    remaining = [p for p in projects if p["id"] != project_id]
    if len(remaining) == len(projects):
        raise HTTPException(404, f"Unknown project '{project_id}'")
    _save_projects(remaining)
    return {"deleted": project_id}
