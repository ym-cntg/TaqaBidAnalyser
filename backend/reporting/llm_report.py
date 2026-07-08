"""LLM-generated bid recommendation report.

Uses Azure OpenAI (`AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` /
`AZURE_OPENAI_API_VERSION` / `AZURE_OPENAI_MODEL` — the deployment name,
per Azure's chat-completions API) rather than the `anthropic` SDK that
`backend/analysis/item_matcher.py`'s LLM matching tier uses — this project
already has an Azure OpenAI resource provisioned for LLM features, separate
from the Azure Document Intelligence resource used for OCR. The overall
pattern still mirrors item_matcher.py: lazy SDK import, environment-driven
config check, a prompt that demands a single JSON object back, everything
wrapped so a missing key or an API/parsing failure degrades to a typed
exception rather than a crash.

Unlike item_matcher's LLM tier (a bulk, low-stakes, per-lot-pair call that
can safely no-op to an empty list on failure), this is a single high-value,
user-triggered call whose output is shown directly to a procurement
analyst — so failures are surfaced via `ReportUnavailable`, not swallowed.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Literal

from ..analysis.comparator import ComparisonResult
from .digest import build_report_digest

logger = logging.getLogger(__name__)

MAX_TOKENS = 4096

VALID_POSITIONS = {"lowest", "competitive", "highest", "excluded_data_gap", "unknown"}


@dataclass
class ReportUnavailable(Exception):
    reason: Literal["not_configured", "api_error", "parse_error"]
    message: str

    def __str__(self) -> str:
        return self.message


def _build_prompt(digest: dict) -> str:
    data_gap_bidders = digest["data_gap_bidders"]
    all_bidders = [row["bidder"] for row in digest["ranked_totals"]]

    gap_rule = ""
    if data_gap_bidders:
        gap_lines = "\n".join(
            f'- {bidder}: {reason}' for bidder, reason in data_gap_bidders.items()
        )
        gap_rule = f"""
The following bidders have NO real comparable pricing yet (a data gap
pending manual entry) and MUST NOT be shortlisted, recommended for award,
or described as cheapest/competitive under any circumstances:
{gap_lines}

For each of these bidders, set their `bidder_notes[...].position` to
exactly "excluded_data_gap", give them an empty `negotiation_points` list,
and mention the exclusion in `caveats`.
"""

    return f"""You are assisting a procurement analyst reviewing a construction \
tender bid comparison for TAQA/ADDC (Abu Dhabi power distribution utility). \
You will be given a structured digest of one round of bidding — ranked \
contract totals, per-lot totals, and the most significant flags (pricing \
issues, arithmetic errors, unbalanced bidding) already detected by the \
analysis pipeline. Do not invent any numbers not present in the digest.
{gap_rule}
Every bidder in this list must have exactly one entry in `bidder_notes`: \
{json.dumps(all_bidders)}

Digest:
{json.dumps(digest, indent=2, default=str)}

Return ONLY a single JSON object with exactly this shape, no other text:
{{
  "executive_summary": "2-4 sentence overview of the bidding landscape",
  "recommendation": {{
    "primary_award": "bidder name, or null if no clear recommendation",
    "shortlist": ["bidder name", ...],
    "reasoning": "why this bidder/shortlist, referencing price and flags"
  }},
  "bidder_notes": {{
    "<bidder name>": {{
      "position": "lowest" | "competitive" | "highest" | "excluded_data_gap",
      "summary": "1-2 sentence read on this bidder",
      "negotiation_points": ["specific, actionable talking point", ...],
      "flags_highlighted": ["short reference to a specific flag/issue", ...]
    }}
  }},
  "caveats": ["anything the analyst should be cautious about", ...]
}}"""


def _parse_response(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(raw[start:end])


def _enforce_data_gap_safety_net(report: dict, data_gap_bidders: dict[str, str]) -> dict:
    """Defensive net in case the model doesn't follow the exclusion rule —
    never trust instruction-following alone for a hard business rule."""
    corrections: list[str] = []

    recommendation = report.setdefault(
        "recommendation", {"primary_award": None, "shortlist": [], "reasoning": ""}
    )
    if recommendation.get("primary_award") in data_gap_bidders:
        corrections.append(
            f"Removed {recommendation['primary_award']} as primary award — "
            f"it has a data gap and cannot be recommended."
        )
        recommendation["primary_award"] = None

    shortlist = recommendation.get("shortlist") or []
    clean_shortlist = [b for b in shortlist if b not in data_gap_bidders]
    if len(clean_shortlist) != len(shortlist):
        corrections.append(
            "Removed data-gap bidder(s) from the shortlist — not comparable yet."
        )
    recommendation["shortlist"] = clean_shortlist

    bidder_notes = report.setdefault("bidder_notes", {})
    for bidder, reason in data_gap_bidders.items():
        note = bidder_notes.setdefault(bidder, {})
        if note.get("position") != "excluded_data_gap":
            corrections.append(f"Corrected {bidder}'s position to excluded_data_gap.")
        note["position"] = "excluded_data_gap"
        note["negotiation_points"] = []
        note.setdefault("summary", reason)
        note.setdefault("flags_highlighted", [])

    for note in bidder_notes.values():
        if note.get("position") not in VALID_POSITIONS:
            note["position"] = "unknown"
        note.setdefault("summary", "")
        note.setdefault("negotiation_points", [])
        note.setdefault("flags_highlighted", [])

    caveats = report.setdefault("caveats", [])
    caveats.extend(corrections)
    return report


def _require_config() -> tuple[str, str, str, str]:
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "")
    deployment = os.environ.get("AZURE_OPENAI_MODEL", "")

    missing = [
        name
        for name, value in [
            ("AZURE_OPENAI_API_KEY", api_key),
            ("AZURE_OPENAI_ENDPOINT", endpoint),
            ("AZURE_OPENAI_API_VERSION", api_version),
            ("AZURE_OPENAI_MODEL", deployment),
        ]
        if not value
    ]
    if missing:
        raise ReportUnavailable(
            "not_configured", f"Missing env var(s): {', '.join(missing)}"
        )
    return api_key, endpoint, api_version, deployment


def generate_recommendation_report(result: ComparisonResult) -> dict:
    """Build a digest from `result` and ask Azure OpenAI for a structured
    recommendation report. Raises ReportUnavailable on any failure —
    callers (routes.py) translate this into an HTTP error, since a
    user-triggered report generation should never fail silently."""
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise ReportUnavailable("not_configured", "openai package not installed")

    api_key, endpoint, api_version, deployment = _require_config()

    digest = build_report_digest(result)
    prompt = _build_prompt(digest)

    try:
        client = AzureOpenAI(
            api_key=api_key, azure_endpoint=endpoint, api_version=api_version
        )
        response = client.chat.completions.create(
            model=deployment,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Recommendation report LLM call failed: %s", e)
        raise ReportUnavailable("api_error", str(e))

    try:
        report = _parse_response(raw)
    except Exception as e:
        logger.error("Recommendation report parsing failed: %s", e)
        raise ReportUnavailable("parse_error", f"Could not parse LLM response: {e}")

    return _enforce_data_gap_safety_net(report, digest["data_gap_bidders"])
