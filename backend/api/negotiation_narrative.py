"""POST /api/rfqs/{rfqnum}/negotiation-report/narrative -- an AI-generated
executive summary + per-vendor observations, layered on top of the
deterministic negotiation report (backend/api/negotiation_report.py).

Uses Databricks Model Serving (backend/db.py's Config()-equivalent auth,
via WorkspaceClient() -- no new credential plumbing), NOT a direct
external LLM API call -- an explicit choice made after an AI Impact
Assessment review, so vendor pricing data stays inside TAQA's governed
Databricks workspace rather than going to a third-party provider. See
databricks/FINDINGS.md for the full guardrails writeup.

Always a fresh call -- no caching, no auto-generation on page load. This
is a deliberately advisory, user-triggered addition: the deterministic
report is still the primary view, and this endpoint's output can never
make an award decision (no primary_award/recommendation field at all) or
reference a vendor that isn't actually in this RFQ's real data (see
_apply_safety_net) -- the model's output is never trusted for a hard
business rule, only checked against one.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
from fastapi import APIRouter, HTTPException

from backend.api.negotiation_report import build_negotiation_report

router = APIRouter()

MAX_TOKENS = 1200
TEMPERATURE = 0.3

_SYSTEM_PROMPT = (
    "You are assisting a procurement analyst reviewing a construction tender bid "
    "comparison for TAQA/ADDC (Abu Dhabi power distribution utility). You will be given "
    "a structured digest of vendor pricing and flagged issues, already computed by the "
    "analysis pipeline. Do not invent any vendor, number, or fact not present in the "
    "digest. Do not recommend an award decision -- only describe what the data shows. "
    "Return ONLY a single JSON object, no other text, with exactly this shape: "
    '{"executive_summary": "2-4 sentence overview of the bidding landscape", '
    '"observations": [{"vendor": "<must be one of the vendor codes given>", '
    '"note": "1-2 sentence read on this vendor", '
    '"talking_points": ["specific, factual point tied to a flag or number"]}], '
    '"caveats": ["anything the analyst should be cautious about"]}'
)


@dataclass
class NarrativeObservation:
    vendor: str
    note: str
    talking_points: list[str]


@dataclass
class NarrativeReport:
    rfqnum: str
    generated_at: str
    executive_summary: str
    observations: list[NarrativeObservation]
    caveats: list[str]


def _iso(dt) -> str:
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _get_endpoint_name() -> str:
    endpoint = os.environ.get("DATABRICKS_LLM_ENDPOINT")
    if not endpoint:
        raise HTTPException(
            status_code=503,
            detail=(
                "not_configured: DATABRICKS_LLM_ENDPOINT is not set. Find (or create) a "
                "Model Serving endpoint name under the workspace's Serving UI and set it "
                "as this env var -- the app's service principal also needs 'Can Query' "
                "permission granted on that endpoint."
            ),
        )
    return endpoint


def _build_user_prompt(report: dict) -> str:
    lines = []
    for v in report["vendors"]:
        rank_note = "lowest" if v["rank"] == 1 else f"{v['pct_above_lowest']:.1f}% above lowest"
        lines.append(
            f"- {v['vendor']} ({v['name'] or 'name unresolved'}): rank #{v['rank']}, "
            f"contract total AED {v['contract_total']:,.0f} ({rank_note}), "
            f"flags: {v['unquoted_count']} unquoted, {v['arithmetic_error_count']} arithmetic errors, "
            f"{v['outlier_count']} outliers, {v['zero_price_count']} zero-priced, "
            f"{v['round_critical_count']} round price increases, {v['round_warning_count']} steep round discounts"
        )
        for issue in v["top_issues"]:
            lines.append(f"    - line {issue['rfqlinenum']}: {issue['detail']}")

    not_submitted = ", ".join(v["vendor"] for v in report["not_submitted"]) or "none"

    return (
        f"RFQ {report['rfqnum']}. Vendors, ranked by contract total (lowest first):\n"
        + "\n".join(lines)
        + f"\n\nInvited but did not submit any pricing: {not_submitted}"
    )


def _parse_response(raw: str | None) -> dict:
    if not raw:
        raise ValueError("empty response content")
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object found in model response")
    return json.loads(raw[start:end])


def _apply_safety_net(parsed: dict, valid_vendors: set[str]) -> dict:
    """Runs after the model responds -- code the model's output can never
    override, not instructions it might not follow. Strips any observation
    referencing a vendor that isn't actually in this RFQ's real data,
    logging the correction as a caveat rather than silently dropping it."""
    caveats = [str(c) for c in (parsed.get("caveats") or [])]
    observations = []
    for obs in parsed.get("observations") or []:
        vendor = obs.get("vendor")
        if vendor not in valid_vendors:
            caveats.append(
                f"Removed an AI-generated observation referencing {vendor!r} -- "
                f"not a real vendor in this RFQ's data."
            )
            continue
        observations.append(
            dict(
                vendor=vendor,
                note=str(obs.get("note") or ""),
                talking_points=[str(p) for p in (obs.get("talking_points") or [])],
            )
        )
    parsed["observations"] = observations
    parsed["caveats"] = caveats
    return parsed


@router.post("/rfqs/{rfqnum}/negotiation-report/narrative")
async def generate_negotiation_narrative(rfqnum: str):
    endpoint = _get_endpoint_name()
    report = build_negotiation_report(rfqnum)

    submitting_vendors = {v["vendor"] for v in report["vendors"]}
    if not submitting_vendors:
        raise HTTPException(status_code=400, detail="No vendor pricing found for this RFQ yet.")

    user_prompt = _build_user_prompt(report)

    try:
        client = WorkspaceClient()
        response = client.serving_endpoints.query(
            name=endpoint,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        raw = response.choices[0].message.content
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"api_error: Model Serving call failed: {exc}. If this is a permission "
                f"error, the app's service principal likely needs 'Can Query' granted on "
                f"the {endpoint!r} endpoint."
            ),
        ) from exc

    try:
        parsed = _parse_response(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"parse_error: Could not parse the model's response as the expected JSON shape: {exc}",
        ) from exc

    parsed = _apply_safety_net(parsed, submitting_vendors)

    return asdict(
        NarrativeReport(
            rfqnum=rfqnum,
            generated_at=_iso(datetime.now(timezone.utc)),
            executive_summary=str(parsed.get("executive_summary") or ""),
            observations=[NarrativeObservation(**o) for o in parsed["observations"]],
            caveats=parsed["caveats"],
        )
    )
