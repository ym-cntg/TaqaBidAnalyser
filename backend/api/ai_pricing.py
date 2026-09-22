"""POST /api/rfqs/{rfqnum}/comparison/ai-pricing -- an AI-estimated price
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
- This feature does the opposite on purpose: the model is asked to
  estimate a fair unit price using its own general knowledge of
  construction/material/service costs, with the real vendor quotes given
  only as context, not as a formula to average or anchor to. This means
  an AI estimate is, by construction, an invented number with no
  verifiable grounding -- the LLM equivalent of an experienced
  estimator's gut-check figure, not a market-rate lookup.

Given that, every other guardrail from the narrative feature still
applies and is arguably more important here: always advisory, always
opt-in (never computed on page load or persisted anywhere -- see
build_ai_pricing()'s docstring), always visually distinct from real
vendor prices in the UI, and the model must self-report a confidence
level so "low confidence, unverified" is visible on every single
estimate, not just in a disclaimer banner.

**Fallback behaviour**: a timeout, a Model Serving outage, a missing
endpoint or an unparseable response no longer fails the request. Each
affected line falls back to a peer-median heuristic so the feature
always renders something. That heuristic is NOT an AI estimate and is
never presented as one: it is the median of the vendor quotes already on
that line, which is precisely the anchoring the AI prompt is written to
avoid. Every estimate therefore carries a `source` of "ai" or
"heuristic", and the response reports `degraded` plus the real reason,
so the UI can say which is which rather than silently passing a median
off as a model estimate.

Uses Databricks Model Serving via backend/api/llm_client.py, same as the
narrative feature -- no external LLM API, no new credential plumbing.
"""

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import median

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
# output in one call, and a per-line cost estimate + rationale is the
# same shape of risk at BOQ scale (up to 500 returned lines), so this
# splits the work into small batches instead of raising the budget
# further.
AI_LINES_CAP = 60
AI_BATCH_SIZE = 20
MAX_TOKENS = 2048
TEMPERATURE = 0.3
# The SDK's query() takes no timeout of its own, so each batch runs in a
# worker thread and is abandoned after this long. Without it a hung
# endpoint hangs the whole request with no way back.
BATCH_TIMEOUT_SECONDS = 30

# Deliberately a long-lived module-level pool rather than a `with
# ThreadPoolExecutor(...)` per batch. The context manager shuts down
# with wait=True, which blocks until the worker finishes, so a hung
# Model Serving call would still hold the request for its full duration
# even though the timeout had already fired. Abandoning the future on a
# shared pool is what actually makes the timeout bound the response.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ai-pricing")

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
    '"unit_cost": <positive number, your estimated fair unit price>, '
    '"confidence": "low" | "medium" | "high", '
    '"rationale": "1 short sentence, plain language"}]}'
)


@dataclass
class AiLineEstimate:
    rfqlinenum: float
    unit_cost: float
    line_cost: float
    confidence: str
    rationale: str
    # "ai" for a model estimate, "heuristic" for the peer-median
    # fallback. The UI must keep these visually distinct; they are not
    # the same kind of number.
    source: str


def _quoted_unit_costs(line: dict) -> list[float]:
    return [
        p["unit_cost"]
        for p in line["prices"].values()
        if not p["unquoted"] and not p["zero_price"] and p["unit_cost"] is not None
    ]


def _build_batch_prompt(lines: list[dict]) -> str:
    rows = []
    for line in lines:
        quotes = _quoted_unit_costs(line)
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
            unit_cost = float(est.get("unit_cost"))
        except (TypeError, ValueError):
            continue
        if not (unit_cost > 0):
            continue
        confidence = est.get("confidence")
        if confidence not in _VALID_CONFIDENCE:
            confidence = "low"
        qty = qty_by_line.get(linenum)
        out.append(
            dict(
                rfqlinenum=linenum,
                unit_cost=unit_cost,
                line_cost=unit_cost * qty if qty is not None else unit_cost,
                confidence=confidence,
                rationale=str(est.get("rationale") or ""),
                source="ai",
            )
        )
    return out


def _heuristic_estimates(lines: list[dict], qty_by_line: dict[float, float | None]) -> list[dict]:
    """The fallback when the model is unavailable.

    Median of the vendor unit costs already quoted on the line. It is
    deliberately the median rather than the mean so one outlier bid
    cannot drag the figure, and it is deliberately labelled a heuristic
    rather than an estimate: anchoring to peer quotes is exactly what
    the AI prompt forbids, so this answers a different question and must
    never be displayed as though the model produced it.

    A line nobody has quoted gets nothing at all. There is no honest way
    to derive a number for it here.
    """
    out = []
    for line in lines:
        quotes = _quoted_unit_costs(line)
        if not quotes:
            continue
        unit_cost = float(median(quotes))
        if not (unit_cost > 0):
            continue
        linenum = line["rfqlinenum"]
        qty = qty_by_line.get(linenum)
        out.append(
            dict(
                rfqlinenum=linenum,
                unit_cost=unit_cost,
                line_cost=unit_cost * qty if qty is not None else unit_cost,
                confidence="low",
                rationale=(
                    f"Median of {len(quotes)} vendor "
                    f"{'quote' if len(quotes) == 1 else 'quotes'} on this line. "
                    "Fallback only, not a model estimate."
                ),
                source="heuristic",
            )
        )
    return out


def _query_batch(
    client, endpoint: str, lines: list[dict], qty_by_line: dict[float, float | None]
) -> tuple[list[dict], str | None]:
    """Returns (estimates, failure_reason). Never raises: a failure here
    is handled by the caller falling back to the heuristic, because the
    feature is required to render something rather than error out."""
    valid_linenums = {line["rfqlinenum"] for line in lines}
    user_prompt = _build_batch_prompt(lines)

    def call():
        response = client.serving_endpoints.query(
            name=endpoint,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        return response.choices[0].message.content

    future = _EXECUTOR.submit(call)
    try:
        raw = future.result(timeout=BATCH_TIMEOUT_SECONDS)
    except FuturesTimeout:
        # Cancels it only if it never started; a call already in flight
        # is simply left to finish into nothing.
        future.cancel()
        return [], f"Model Serving did not respond within {BATCH_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return [], (
            f"Model Serving call failed: {exc}. If this is a permission error, the app's "
            f"service principal likely needs 'Can Query' granted on the {endpoint!r} endpoint."
        )

    try:
        parsed = _parse_response(raw)
    except Exception as exc:
        return [], f"Could not parse the model's response as the expected JSON shape: {exc}"

    return _apply_safety_net(parsed, valid_linenums, qty_by_line), None


def build_ai_pricing(rfqnum: str, round_label: str | None = None) -> dict:
    """The AI-pricing payload as a plain callable, mirroring
    negotiation_narrative.py's pattern. Always a fresh call -- no
    caching, no persistence anywhere, and never triggered by a page
    load. Capped at AI_LINES_CAP lines per call (see module docstring)
    and batched at AI_BATCH_SIZE per Model Serving request.

    Degrades rather than fails: any line the model could not price falls
    back to the peer-median heuristic, and the caller is told so.
    """
    comparison = build_comparison(rfqnum, round_label=round_label)

    all_lines = comparison["lines"]
    total_line_count = comparison["total_line_count"]
    selected_lines = all_lines[:AI_LINES_CAP]
    truncated = total_line_count > len(selected_lines)

    if not selected_lines:
        raise HTTPException(status_code=400, detail="No BOQ lines found for this RFQ yet.")

    qty_by_line = {line["rfqlinenum"]: line["qty"] for line in selected_lines}

    failures: list[str] = []
    results: list[dict] = []
    priced: set[float] = set()

    try:
        endpoint = get_llm_endpoint_name()
    except HTTPException as exc:
        # Not configured is just another reason to fall back, not a
        # reason to show the analyst nothing.
        endpoint = None
        failures.append(str(exc.detail))

    if endpoint is not None:
        client = WorkspaceClient()
        for i in range(0, len(selected_lines), AI_BATCH_SIZE):
            batch = selected_lines[i : i + AI_BATCH_SIZE]
            estimates, reason = _query_batch(client, endpoint, batch, qty_by_line)
            results.extend(estimates)
            if reason:
                failures.append(reason)
        priced = {r["rfqlinenum"] for r in results}

    # Any line the model skipped or could not be asked about, including
    # individual lines dropped by the safety net, still gets a figure.
    unpriced = [line for line in selected_lines if line["rfqlinenum"] not in priced]
    if unpriced:
        results.extend(_heuristic_estimates(unpriced, qty_by_line))

    results.sort(key=lambda r: r["rfqlinenum"])
    estimates = [AiLineEstimate(**r) for r in results]
    heuristic_count = sum(1 for e in estimates if e.source == "heuristic")

    return {
        "rfqnum": rfqnum,
        "round": comparison["round"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "truncated": truncated,
        "total_line_count": total_line_count,
        "estimated_line_count": len(selected_lines),
        "heuristic_line_count": heuristic_count,
        "degraded": heuristic_count > 0,
        # Deduplicated because every batch tends to fail the same way,
        # and the analyst needs the reason once, not twenty times.
        "fallback_reason": "; ".join(dict.fromkeys(failures)) or None,
        "lines": [asdict(e) for e in estimates],
    }


@router.post("/rfqs/{rfqnum}/comparison/ai-pricing")
async def generate_ai_pricing(rfqnum: str, round: str | None = None):
    return build_ai_pricing(rfqnum, round_label=round)
