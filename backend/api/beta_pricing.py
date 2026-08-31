"""POST /api/rfqs/{rfqnum}/comparison/beta -- an AI-estimated "Beta" price
per BOQ line, layered on top of the deterministic BOQ comparison
(backend/api/comparison.py).

**This is a materially different, higher-risk AI feature than the
negotiation narrative** (backend/api/negotiation_narrative.py), and that
difference is deliberate, not an oversight -- flagged clearly to the user
before this was built, who explicitly chose this design after being told
the tradeoff:

- The narrative feature is forbidden from inventing any number not
  already present in the digest it's given -- it only describes real,
  computed facts.
- Beta does the opposite on purpose: the model is asked to estimate a
  fair unit price using its own general knowledge of construction/
  material/service costs, with the real vendor quotes given only as
  context, not as a formula to average or anchor to. This means Beta is,
  by construction, an invented number with no verifiable grounding --
  the LLM equivalent of an experienced estimator's gut-check figure, not
  a market-rate lookup.

Given that, every other guardrail from the narrative feature still
applies and is arguably more important here: always advisory, always
opt-in (never computed on page load or persisted anywhere -- see
build_beta_pricing()'s docstring), always visually distinct from real
vendor prices in the UI, and the model must self-report a confidence
level so "low confidence, unverified" is visible on every single
estimate, not just in a disclaimer banner. See databricks/FINDINGS.md for
the full discussion and the user's explicit choice among the alternatives
that were offered.

Uses Databricks Model Serving via backend/api/llm_client.py, same as the
narrative feature -- no external LLM API, no new credential plumbing.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
from fastapi import APIRouter, HTTPException

from backend.api.comparison import build_comparison
from backend.api.llm_client import get_llm_endpoint_name

router = APIRouter()

# First-pass values, all tunable. Batching keeps every single call's
# output small and well within any model's token budget regardless of
# how many lines a BOQ has -- the narrative feature's real truncation
# bug (databricks/FINDINGS.md) came from asking for too much structured
# output in one call, and Beta's per-line cost estimate + rationale is
# the same shape of risk at BOQ scale (up to 500 returned lines), so this
# splits the work into small batches instead of raising the budget
# further.
BETA_LINES_CAP = 60
BETA_BATCH_SIZE = 20
MAX_TOKENS = 2048
TEMPERATURE = 0.3

_SYSTEM_PROMPT = (
    "You are assisting a procurement analyst reviewing a construction tender bid "
    "comparison for TAQA/ADDC (Abu Dhabi power distribution utility). For each BOQ line "
    "item below, estimate a fair UNIT price using your own general knowledge of typical "
    "construction, material, and service costs. The real vendor quotes given for each line "
    "are context only -- do not simply average, copy, or anchor to them; give your own "
    "independent estimate. This is a rough, unverified estimate, not a market-rate lookup "
    "or a benchmark -- report an honest confidence level for every single line, and default "
    "to \"low\" whenever you are not genuinely confident. Return ONLY a single JSON object, "
    "no other text, no markdown code fences, with exactly this shape: "
    '{"estimates": [{"rfqlinenum": <int, must be one of the line numbers given>, '
    '"beta_unit_cost": <positive number, your estimated fair unit price>, '
    '"confidence": "low" | "medium" | "high", '
    '"rationale": "1 short sentence, plain language"}]}'
)


@dataclass
class BetaLineEstimate:
    rfqlinenum: float
    beta_unit_cost: float
    beta_line_cost: float
    confidence: str
    rationale: str


def _build_batch_prompt(lines: list[dict]) -> str:
    rows = []
    for line in lines:
        quotes = [
            p["unit_cost"]
            for p in line["prices"].values()
            if not p["unquoted"] and not p["zero_price"] and p["unit_cost"] is not None
        ]
        quotes_text = ", ".join(f"AED {q:,.2f}" for q in sorted(quotes)) if quotes else "none submitted"
        rows.append(
            f"- Line {line['rfqlinenum']}: {line['description'] or '(no description)'} "
            f"(qty {line['qty']} {line['unit'] or ''}). Vendor unit-cost quotes: {quotes_text}"
        )
    return "BOQ lines:\n" + "\n".join(rows)


def _parse_response(raw: str | None) -> dict:
    if not raw:
        raise ValueError("empty response content")
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object found in model response")
    return json.loads(raw[start:end])


_VALID_CONFIDENCE = {"low", "medium", "high"}


def _apply_safety_net(parsed: dict, valid_linenums: set[float], qty_by_line: dict[float, float | None]) -> list[dict]:
    """Runs after every model response -- code the model's output can
    never override. Drops any estimate for a line number that isn't
    actually in the batch it was given (blocks a hallucinated line
    reference), drops anything that isn't a real positive number (a
    non-numeric or non-positive "price" is not a usable estimate,
    corrected or not), and defaults an invalid/missing confidence down
    to "low" rather than silently upgrading it -- if the model didn't
    clearly say how sure it is, treat it as unsure."""
    out = []
    for est in parsed.get("estimates") or []:
        try:
            linenum = float(est.get("rfqlinenum"))
        except (TypeError, ValueError):
            continue
        if linenum not in valid_linenums:
            continue
        try:
            unit_cost = float(est.get("beta_unit_cost"))
        except (TypeError, ValueError):
            continue
        if not (unit_cost > 0):
            continue
        confidence = est.get("confidence")
        if confidence not in _VALID_CONFIDENCE:
            confidence = "low"
        qty = qty_by_line.get(linenum)
        line_cost = unit_cost * qty if qty is not None else unit_cost
        out.append(
            dict(
                rfqlinenum=linenum,
                beta_unit_cost=unit_cost,
                beta_line_cost=line_cost,
                confidence=confidence,
                rationale=str(est.get("rationale") or ""),
            )
        )
    return out


def _query_batch(client, endpoint: str, lines: list[dict], qty_by_line: dict[float, float | None]) -> list[dict]:
    valid_linenums = {line["rfqlinenum"] for line in lines}
    user_prompt = _build_batch_prompt(lines)
    try:
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

    return _apply_safety_net(parsed, valid_linenums, qty_by_line)


def build_beta_pricing(rfqnum: str, round_label: str | None = None) -> dict:
    """The Beta-pricing payload as a plain callable, mirroring
    negotiation_narrative.py's pattern. Always a fresh call -- no
    caching, no persistence anywhere, and never triggered by a page
    load. Capped at BETA_LINES_CAP lines per call (see module docstring)
    and batched at BETA_BATCH_SIZE per Model Serving request.
    """
    endpoint = get_llm_endpoint_name()
    comparison = build_comparison(rfqnum, round_label=round_label)

    all_lines = comparison["lines"]
    total_line_count = comparison["total_line_count"]
    selected_lines = all_lines[:BETA_LINES_CAP]
    truncated = total_line_count > len(selected_lines)

    if not selected_lines:
        raise HTTPException(status_code=400, detail="No BOQ lines found for this RFQ yet.")

    qty_by_line = {line["rfqlinenum"]: line["qty"] for line in selected_lines}

    client = WorkspaceClient()
    results: list[dict] = []
    for i in range(0, len(selected_lines), BETA_BATCH_SIZE):
        batch = selected_lines[i : i + BETA_BATCH_SIZE]
        results.extend(_query_batch(client, endpoint, batch, qty_by_line))

    estimates = [BetaLineEstimate(**r) for r in results]

    return {
        "rfqnum": rfqnum,
        "round": comparison["round"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "truncated": truncated,
        "total_line_count": total_line_count,
        "estimated_line_count": len(selected_lines),
        "lines": [asdict(e) for e in estimates],
    }


@router.post("/rfqs/{rfqnum}/comparison/beta")
async def generate_beta_pricing(rfqnum: str, round: str | None = None):
    return build_beta_pricing(rfqnum, round_label=round)
