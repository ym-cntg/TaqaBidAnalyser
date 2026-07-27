"""Document curation — deciding which submitted files count as a bidder's
official bid, for any project (see `projects.py`).

Real bidder submissions rarely arrive as a clean "one BOQ per bidder"
folder — see `data/water/A-20669/`, where each bidder folder has cover
letters, compliance certificates, discount letters, and multiple
near-duplicate BOQ exports mixed together. This module lets a reviewer
look at everything a bidder actually submitted and mark which files count
as "the bid" before any extraction is attempted, rather than the pipeline
silently guessing (or, for `data/power/`, relying on a folder convention
that only works because that sample data happens to be clean).

Deliberately generic across any project's folder shape: it only lists and
tags files, it doesn't parse them. Wiring a project's *selected* files
into actual extraction is separate work — power's existing convention-based
discovery (`_get_sample_comparison` in routes.py) doesn't consume this at
all yet, and no other project has a working BOQ parser regardless of what
gets selected here (see PROGRESS.md, 2026-07-20).

Was `tenders.py` when there were exactly two hardcoded tenders; renamed
once `projects.py` made "project" the general concept and this became
generic file curation for any of them.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .projects import get_project, get_project_root

router = APIRouter()

STATE_DIR = Path(__file__).parent.parent.parent / "backend" / "state"
SELECTIONS_FILE = STATE_DIR / "selections.json"


def _load_selections() -> dict:
    if not SELECTIONS_FILE.exists():
        return {}
    try:
        return json.loads(SELECTIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_selections(selections: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SELECTIONS_FILE.write_text(json.dumps(selections, indent=2, sort_keys=True))


def _list_bidder_files(root: Path, project_selections: dict[str, list[str]]) -> list[dict]:
    """One entry per bidder directory under `root`, each with every file
    beneath it (paths relative to the bidder's own directory, since
    different projects nest differently and a bidder-relative path is
    stable either way) flagged against that bidder's persisted selection."""
    bidders = []
    for bidder_dir in sorted(root.iterdir()):
        if not bidder_dir.is_dir():
            continue
        selected_paths = set(project_selections.get(bidder_dir.name, []))
        files = []
        for f in sorted(bidder_dir.rglob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            rel_path = str(f.relative_to(bidder_dir))
            files.append({
                "path": rel_path,
                "name": f.name,
                "ext": f.suffix.lower(),
                "size": f.stat().st_size,
                "selected": rel_path in selected_paths,
            })
        bidders.append({
            "bidder": bidder_dir.name,
            "files": files,
            "selected_count": sum(1 for f in files if f["selected"]),
        })
    return bidders


@router.get("/projects/{project_id}/files")
async def get_project_files(project_id: str):
    """Every file under every bidder folder for this project, flagged with
    whether it's currently selected as part of the bid."""
    project = get_project(project_id)
    root = get_project_root(project_id)
    if not project or not root or not root.exists():
        raise HTTPException(404, f"Unknown project '{project_id}'")

    project_selections = _load_selections().get(project_id, {})
    bidders = _list_bidder_files(root, project_selections)

    return {
        "id": project_id,
        "tender_no": project["tender_no"],
        "label": project["name"],
        "bidders": bidders,
    }


class SelectionToggle(BaseModel):
    bidder: str
    path: str
    selected: bool


@router.post("/projects/{project_id}/selection")
async def set_selection(project_id: str, body: SelectionToggle):
    """Mark (or unmark) one file as part of the bid for one bidder.
    Persisted to disk immediately — a curation decision like this is worth
    more to keep across restarts than a transient extraction cache."""
    root = get_project_root(project_id)
    if not root or not root.exists():
        raise HTTPException(404, f"Unknown project '{project_id}'")

    bidder_dir = (root / body.bidder).resolve()
    file_path = (bidder_dir / body.path).resolve()
    if bidder_dir not in file_path.parents or not file_path.is_file():
        raise HTTPException(404, f"File not found: {body.path}")

    selections = _load_selections()
    project_selections = selections.setdefault(project_id, {})
    bidder_selections = set(project_selections.get(body.bidder, []))

    if body.selected:
        bidder_selections.add(body.path)
    else:
        bidder_selections.discard(body.path)

    if bidder_selections:
        project_selections[body.bidder] = sorted(bidder_selections)
    else:
        project_selections.pop(body.bidder, None)

    _save_selections(selections)
    return {"bidder": body.bidder, "path": body.path, "selected": body.selected}
