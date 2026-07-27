"""Manual overrides for item-matching mistakes.

The 4-tier matcher (exact -> normalized -> fuzzy -> LLM, see
`item_matcher.py`) gets most items right, but not all — a fuzzy/LLM tier
can pair the wrong two items, or leave a real match as "unmatched" because
the wording drifted too far. A reviewer needs a manual fail-safe here, the
same way `corrections.py` is the fail-safe for a bad extracted value.

In-memory only, same known scope limit as `corrections.py` (lost on
restart) — deliberately consistent with that precedent rather than adding
a new persisted store for what's conceptually the same kind of review
action.
"""

# (lot_number, bidder, original_item_no) -> canonical_item_no
_overrides: dict[tuple[int, str, str], str] = {}


def record_match_override(lot_number: int, bidder: str, original_item_no: str, canonical_item_no: str) -> None:
    _overrides[(lot_number, bidder, original_item_no)] = canonical_item_no


def clear_match_override(lot_number: int, bidder: str, original_item_no: str) -> None:
    _overrides.pop((lot_number, bidder, original_item_no), None)


def get_overrides_for_lot(lot_number: int) -> dict[tuple[str, str], str]:
    """(bidder, original_item_no) -> canonical_item_no, for one lot."""
    return {
        (bidder, item_no): canonical
        for (lot, bidder, item_no), canonical in _overrides.items()
        if lot == lot_number
    }


def list_match_overrides() -> list[dict]:
    return [
        {
            "lot_number": lot,
            "bidder": bidder,
            "original_item_no": item_no,
            "canonical_item_no": canonical,
        }
        for (lot, bidder, item_no), canonical in _overrides.items()
    ]
