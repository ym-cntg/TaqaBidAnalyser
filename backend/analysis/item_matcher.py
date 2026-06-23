"""4-tier item matching across bidders.

Tier 1: Exact item_no match
Tier 2: Normalized item_no match (strip leading zeros, fix OCR artifacts)
Tier 3: Fuzzy description match (difflib SequenceMatcher, threshold >= 0.85)
Tier 4: LLM match via Claude Haiku (opt-in, for semantically equivalent items)
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemMatch:
    """A matched pair of items across two bidders."""
    item_no_a: str
    item_no_b: str
    match_method: str  # "exact", "normalized", "fuzzy", "llm"
    confidence: float  # 0.0 - 1.0


def normalize_item_no(item_no: str) -> str:
    """Normalize an item number for comparison.

    Handles: leading zeros ("1.03" -> "1.3"), comma/semicolon as dot,
    whitespace, trailing dots.
    """
    s = item_no.strip()
    # Replace comma/semicolon with dot (common OCR errors)
    s = s.replace(",", ".").replace(";", ".")
    # Remove trailing dots
    s = s.rstrip(".")
    # Split on dots, strip leading zeros from each part, rejoin
    parts = s.split(".")
    normalized_parts = []
    for part in parts:
        stripped = part.lstrip("0") or "0"
        normalized_parts.append(stripped)
    return ".".join(normalized_parts)


def _clean_description(desc: str) -> str:
    """Clean a description for fuzzy comparison."""
    s = desc.lower().strip()
    # Remove extra whitespace
    s = re.sub(r"\s+", " ", s)
    # Remove common filler words that vary between bidders
    for word in ("supply", "and", "of", "the", "for", "&", "no.", "nr.", "number"):
        s = re.sub(rf"\b{re.escape(word)}\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def fuzzy_score(desc_a: str, desc_b: str) -> float:
    """Compare two descriptions using SequenceMatcher on cleaned text."""
    clean_a = _clean_description(desc_a)
    clean_b = _clean_description(desc_b)
    if not clean_a or not clean_b:
        return 0.0
    return SequenceMatcher(None, clean_a, clean_b).ratio()


def _llm_match_items(
    unmatched_a: list[dict],
    unmatched_b: list[dict],
) -> list[ItemMatch]:
    """Use Claude Haiku to match semantically equivalent items.

    Only called when ENABLE_LLM_MATCHING=true and ANTHROPIC_API_KEY is set.
    Sends a single batch request with all unmatched items.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping LLM matching")
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping LLM matching")
        return []

    if not unmatched_a or not unmatched_b:
        return []

    # Build compact representations
    list_a = [
        {"item_no": item["item_no"], "desc": item["description"][:150]}
        for item in unmatched_a
    ]
    list_b = [
        {"item_no": item["item_no"], "desc": item["description"][:150]}
        for item in unmatched_b
    ]

    prompt = f"""You are matching BOQ (Bill of Quantities) line items between two bidders for the same construction tender.

Bidder A items (unmatched):
{json.dumps(list_a, indent=2)}

Bidder B items (unmatched):
{json.dumps(list_b, indent=2)}

Match items that refer to the same work/material even if worded differently.
Return ONLY a JSON array of matches. Each match: {{"item_no_a": "...", "item_no_b": "...", "confidence": 0.0-1.0}}
If no matches, return [].
Return ONLY the JSON array, no other text."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Extract JSON array from response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        matches_data = json.loads(raw[start:end])

        matches = []
        for m in matches_data:
            if m.get("confidence", 0) >= 0.7:
                matches.append(ItemMatch(
                    item_no_a=m["item_no_a"],
                    item_no_b=m["item_no_b"],
                    match_method="llm",
                    confidence=m["confidence"],
                ))
        logger.info("LLM matched %d items from %d x %d unmatched", len(matches), len(unmatched_a), len(unmatched_b))
        return matches
    except Exception as e:
        logger.error("LLM matching failed: %s", e)
        return []


def match_items(
    items_a: dict[str, dict],
    items_b: dict[str, dict],
) -> tuple[list[ItemMatch], list[str], list[str]]:
    """Match items from two bidders using 4-tier strategy.

    Args:
        items_a: item_no -> item data dict for bidder A
        items_b: item_no -> item data dict for bidder B

    Returns:
        (matches, unmatched_a_keys, unmatched_b_keys)
    """
    matches: list[ItemMatch] = []
    matched_a: set[str] = set()
    matched_b: set[str] = set()

    # --- Tier 1: Exact match ---
    for key_a in items_a:
        if key_a in items_b:
            matches.append(ItemMatch(key_a, key_a, "exact", 1.0))
            matched_a.add(key_a)
            matched_b.add(key_a)

    # --- Tier 2: Normalized match ---
    remaining_a = {k: normalize_item_no(k) for k in items_a if k not in matched_a}
    remaining_b = {k: normalize_item_no(k) for k in items_b if k not in matched_b}

    # Build reverse map: normalized -> original key for B
    norm_b_map: dict[str, str] = {}
    for key_b, norm_b in remaining_b.items():
        if norm_b not in norm_b_map:
            norm_b_map[norm_b] = key_b

    for key_a, norm_a in remaining_a.items():
        if norm_a in norm_b_map:
            key_b = norm_b_map[norm_a]
            matches.append(ItemMatch(key_a, key_b, "normalized", 0.95))
            matched_a.add(key_a)
            matched_b.add(key_b)
            del norm_b_map[norm_a]

    # --- Tier 3: Fuzzy description match ---
    fuzzy_a = {k: items_a[k] for k in items_a if k not in matched_a}
    fuzzy_b = {k: items_b[k] for k in items_b if k not in matched_b}

    # Only attempt fuzzy if both sides have unmatched items and lists are manageable
    if fuzzy_a and fuzzy_b and len(fuzzy_a) * len(fuzzy_b) <= 10000:
        # Score all pairs, greedily pick best matches above threshold
        scored_pairs = []
        for key_a, data_a in fuzzy_a.items():
            for key_b, data_b in fuzzy_b.items():
                score = fuzzy_score(data_a.get("description", ""), data_b.get("description", ""))
                if score >= 0.85:
                    scored_pairs.append((score, key_a, key_b))

        # Sort by score descending, greedily assign
        scored_pairs.sort(key=lambda x: x[0], reverse=True)
        fuzzy_matched_a: set[str] = set()
        fuzzy_matched_b: set[str] = set()
        for score, key_a, key_b in scored_pairs:
            if key_a not in fuzzy_matched_a and key_b not in fuzzy_matched_b:
                matches.append(ItemMatch(key_a, key_b, "fuzzy", round(score, 3)))
                fuzzy_matched_a.add(key_a)
                fuzzy_matched_b.add(key_b)
                matched_a.add(key_a)
                matched_b.add(key_b)

    # --- Tier 4: LLM match (opt-in) ---
    llm_enabled = os.environ.get("ENABLE_LLM_MATCHING", "").lower() in ("true", "1", "yes")
    if llm_enabled:
        llm_unmatched_a = [
            {"item_no": k, "description": items_a[k].get("description", "")}
            for k in items_a if k not in matched_a
        ]
        llm_unmatched_b = [
            {"item_no": k, "description": items_b[k].get("description", "")}
            for k in items_b if k not in matched_b
        ]
        llm_matches = _llm_match_items(llm_unmatched_a, llm_unmatched_b)
        for m in llm_matches:
            if m.item_no_a in items_a and m.item_no_b in items_b:
                if m.item_no_a not in matched_a and m.item_no_b not in matched_b:
                    matches.append(m)
                    matched_a.add(m.item_no_a)
                    matched_b.add(m.item_no_b)

    unmatched_a_keys = [k for k in items_a if k not in matched_a]
    unmatched_b_keys = [k for k in items_b if k not in matched_b]

    return matches, unmatched_a_keys, unmatched_b_keys
