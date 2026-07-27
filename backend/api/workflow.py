"""BOQ template lifecycle — requisition pull, template build/review/lock/issue,
and close-out, i.e. features 1-4 and 19 of the full feature list, scoped to
one project at a time (see `projects.py`).

Maximo integration (pulling a requisition, issuing a template back for a
market request) is explicitly simulated here — this demo has no access to
TAQA's actual Maximo instance. Every simulated step is labeled as such in
its response payload so the UI can be honest about what's real (the BOQ
template structure, which is derived from an actual bidder's real submitted
item structure with pricing stripped) versus staged (the requisition pull
and the "issued to market" handoff, which are canned/simulated).

State is a single persisted JSON file, same pattern as `documents.py`'s
selections store — deliberately durable (survives a restart) since a lock
or an issue decision is a real workflow commitment, not throwaway UI state.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..extraction.router import parse_bidder_folder_pdf
from .projects import get_project, get_project_root

router = APIRouter()

STATE_DIR = Path(__file__).parent.parent.parent / "backend" / "state"
WORKFLOW_FILE = STATE_DIR / "workflow.json"

STAGE_ORDER = [
    "not_started",
    "requisition_pulled",
    "template_built",
    "template_locked",
    "issued",
    "closed",
]

# Canned Maximo requisitions for the two seed projects — represents the
# header info + high-level work categories a real PR pull would return for
# these specific tenders. Standing in for an integration we don't have
# credentials or a sandbox for. Any other (user-created) project falls back
# to `_generic_requisition()` below, built from the project's own name/
# tender number rather than needing a hand-authored entry per project.
_SEED_REQUISITIONS = {
    "power-d111808": {
        "pr_number": "PR-2026-04471",
        "title": "Construction of 3 Primary Substations — Eastern Region",
        "requested_by": "Mohammed Al Katheri",
        "department": "Procurement (Power)",
        "categories": [
            {"category": "Construction Works (Items 1-3)", "lots": 3, "note": "Per-substation civil, structural, electrical works"},
            {"category": "Load Diversion Works (Item 4)", "lots": 3, "note": "Temporary supply during changeover"},
            {"category": "Dismantling Works (Items 5-8)", "lots": 3, "note": "Removal of existing equipment"},
            {"category": "Spare Parts (Item 9)", "lots": 3, "note": "Mandatory spares per substation"},
        ],
    },
    "water-a20669": {
        "pr_number": "PR-2026-05108",
        "title": "Water Network Bid — A-20669",
        "requested_by": "ADDC Procurement (Water)",
        "department": "Procurement (Water)",
        "categories": [
            {"category": "Priced BOQ", "lots": 1, "note": "Single-lot water works BOQ"},
        ],
    },
}


def _generic_requisition(project: dict) -> dict:
    """Simulated requisition for any project without a hand-authored entry
    above — built from the project's own fields so a newly-created project
    still gets a plausible Maximo-shaped payload instead of a 404."""
    return {
        "pr_number": f"PR-2026-{abs(hash(project['id'])) % 90000 + 10000}",
        "title": project["name"],
        "requested_by": project.get("created_by") or "ADDC Procurement",
        "department": "Procurement",
        "categories": [
            {
                "category": "Priced BOQ",
                "lots": 1,
                "note": project.get("description") or "Bid package",
            }
        ],
    }


def _load_state() -> dict:
    if not WORKFLOW_FILE.exists():
        return {}
    try:
        return json.loads(WORKFLOW_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOW_FILE.write_text(json.dumps(state, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_project_state(state: dict, project_id: str) -> dict:
    return state.setdefault(project_id, {"stage": "not_started"})


def _require_root(project_id: str) -> Path:
    root = get_project_root(project_id)
    if root is None:
        raise HTTPException(404, f"Unknown project '{project_id}'")
    return root


def _build_template_from_reference(project_id: str) -> dict | None:
    """Derive a blank BOQ template (item_no/description/unit/qty, no
    pricing) from the first bidder folder we can actually extract a real
    structure from. Returns None if no bidder in this project yields a
    parseable per-item BOQ (e.g. the water tender, whose folder layout and
    schema aren't wired into extraction yet — see PROGRESS.md 2026-07-20)."""
    root = _require_root(project_id)
    if not root.exists():
        return None

    for bidder_dir in sorted(d for d in root.iterdir() if d.is_dir()):
        extractions = parse_bidder_folder_pdf(bidder_dir, bidder_dir.name)
        if not extractions:
            continue
        reference = extractions[0]
        lots = []
        for lot in reference.lots:
            sheets = []
            for sheet in lot.sheets:
                rows = [
                    {
                        "item_no": item.item_no,
                        "description": item.description,
                        "unit": item.unit,
                        "qty": item.qty,
                        "is_section_header": item.is_section_header,
                    }
                    for item in sheet.items
                ]
                sheets.append({"name": sheet.name, "items": rows})
            lots.append({"lot_name": lot.lot_name, "lot_number": lot.lot_number, "sheets": sheets})
        return {
            "tender_no": reference.tender_no,
            "reference_bidder": bidder_dir.name,
            "lots": lots,
        }
    return None


@router.get("/workflow/{project_id}/status")
async def get_workflow_status(project_id: str):
    _require_root(project_id)
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    return {
        "project_id": project_id,
        "stage": project_state["stage"],
        "requisition": project_state.get("requisition"),
        "has_template": "template" in project_state,
        "locked_at": project_state.get("locked_at"),
        "locked_by": project_state.get("locked_by"),
        "issued_at": project_state.get("issued_at"),
        "maximo_reference": project_state.get("maximo_reference"),
        "closed_at": project_state.get("closed_at"),
        "award_decision": project_state.get("award_decision"),
    }


@router.post("/workflow/{project_id}/pull-requisition")
async def pull_requisition(project_id: str):
    """Simulated Maximo pull — feature 1."""
    project = get_project(project_id)
    _require_root(project_id)
    requisition = _SEED_REQUISITIONS.get(project_id) or _generic_requisition(project)

    state = _load_state()
    project_state = _get_project_state(state, project_id)
    project_state["requisition"] = requisition
    project_state["stage"] = "requisition_pulled"
    _save_state(state)
    return {"simulated": True, "requisition": requisition, "stage": project_state["stage"]}


@router.get("/workflow/{project_id}/template")
async def get_template(project_id: str):
    """Read-only fetch of the stored template, whatever stage it's in —
    used to render the template view after a page refresh without
    re-triggering build-template's stage-reset side effects."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    template = project_state.get("template")
    if template is None:
        raise HTTPException(404, "No template built yet")
    return {"template": template, "stage": project_state["stage"]}


@router.post("/workflow/{project_id}/build-template")
async def build_template(project_id: str):
    """Build the BOQ template from the requisition — feature 2. The
    structure is real (a bidder's actual item numbering/description/unit/qty
    with pricing stripped), not simulated."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    if project_state["stage"] == "not_started":
        raise HTTPException(400, "Pull the requisition before building a template")

    template = _build_template_from_reference(project_id)
    if template is None:
        raise HTTPException(
            404,
            f"No parseable BOQ structure available for '{project_id}' yet — "
            f"extraction for this project's BOQ format isn't wired up",
        )

    project_state["template"] = template
    project_state["stage"] = "template_built"
    project_state.pop("locked_at", None)
    project_state.pop("locked_by", None)
    _save_state(state)
    return {"template": template, "stage": project_state["stage"]}


class TemplateRowEdit(BaseModel):
    lot_number: int
    sheet_name: str
    item_no: str
    fields: dict


@router.post("/workflow/{project_id}/template/edit")
async def edit_template_row(project_id: str, body: TemplateRowEdit):
    """Buyer review/edit of the built template — feature 3, pre-lock half."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    if project_state["stage"] != "template_built":
        raise HTTPException(409, f"Template isn't editable in stage '{project_state['stage']}'")

    allowed = {"description", "unit", "qty"}
    unknown = set(body.fields) - allowed
    if unknown:
        raise HTTPException(400, f"Unknown field(s): {', '.join(sorted(unknown))}")

    template = project_state.get("template")
    if not template:
        raise HTTPException(404, "No template built yet")

    found = False
    for lot in template["lots"]:
        if lot["lot_number"] != body.lot_number:
            continue
        for sheet in lot["sheets"]:
            if sheet["name"] != body.sheet_name:
                continue
            for row in sheet["items"]:
                if row["item_no"] == body.item_no:
                    row.update(body.fields)
                    found = True
    if not found:
        raise HTTPException(404, "Template row not found")

    _save_state(state)
    return {"template": template, "stage": project_state["stage"]}


class LockRequest(BaseModel):
    locked_by: str


@router.post("/workflow/{project_id}/template/lock")
async def lock_template(project_id: str, body: LockRequest):
    """Human-in-the-loop lock — feature 3, review-complete half."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    if project_state["stage"] != "template_built":
        raise HTTPException(409, f"Cannot lock from stage '{project_state['stage']}'")

    project_state["stage"] = "template_locked"
    project_state["locked_by"] = body.locked_by
    project_state["locked_at"] = _now()
    _save_state(state)
    return {"stage": project_state["stage"], "locked_by": body.locked_by, "locked_at": project_state["locked_at"]}


@router.post("/workflow/{project_id}/template/unlock")
async def unlock_template(project_id: str):
    """Revert a lock to make further edits — not in the source feature list,
    but without it a reviewer who locked too early has no way back in a demo
    session, which isn't realistic for a 'review and edit' step."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    if project_state["stage"] != "template_locked":
        raise HTTPException(409, f"Cannot unlock from stage '{project_state['stage']}'")

    project_state["stage"] = "template_built"
    project_state.pop("locked_at", None)
    project_state.pop("locked_by", None)
    _save_state(state)
    return {"stage": project_state["stage"]}


@router.post("/workflow/{project_id}/template/issue")
async def issue_template(project_id: str):
    """Simulated hand-off to the market request — feature 4."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    if project_state["stage"] != "template_locked":
        raise HTTPException(409, f"Cannot issue from stage '{project_state['stage']}'")

    maximo_reference = f"MR-{project_id.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    project_state["stage"] = "issued"
    project_state["issued_at"] = _now()
    project_state["maximo_reference"] = maximo_reference
    _save_state(state)
    return {
        "simulated": True,
        "stage": project_state["stage"],
        "issued_at": project_state["issued_at"],
        "maximo_reference": maximo_reference,
    }


class CloseRequest(BaseModel):
    primary_award: str | None = None
    shortlist: list[str] = []
    reasoning: str = ""
    notes: str = ""


@router.post("/workflow/{project_id}/close")
async def close_procurement(project_id: str, body: CloseRequest):
    """Mark the procurement finished and store the award decision as a
    historical record — feature 19."""
    state = _load_state()
    project_state = _get_project_state(state, project_id)
    if project_state["stage"] not in ("issued", "closed"):
        raise HTTPException(409, f"Cannot close from stage '{project_state['stage']}' — issue the template first")

    project_state["stage"] = "closed"
    project_state["closed_at"] = _now()
    project_state["award_decision"] = {
        "primary_award": body.primary_award,
        "shortlist": body.shortlist,
        "reasoning": body.reasoning,
        "notes": body.notes,
    }
    _save_state(state)
    return {
        "stage": project_state["stage"],
        "closed_at": project_state["closed_at"],
        "award_decision": project_state["award_decision"],
    }


@router.post("/workflow/{project_id}/reset")
async def reset_workflow(project_id: str):
    """Reset back to not_started — demo convenience so the full lifecycle
    can be replayed without editing the state file by hand."""
    _require_root(project_id)
    state = _load_state()
    state[project_id] = {"stage": "not_started"}
    _save_state(state)
    return {"stage": "not_started"}
