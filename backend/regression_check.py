"""Regression check for extraction correctness.

Run this before merging or deploying:

    uv run python -m backend.regression_check

Exits 0 on pass, 1 on failure — suitable as a CI gate. This is a floor,
not a ceiling: it won't catch new *kinds* of bugs, but it makes sure the
three specific failure modes already found once (see BUG_TRACKER.md:
BUG-001, BUG-002, BUG-003) can never silently come back without the build
noticing:

1. A leaked subtotal/recap row parsed as a real line item (BUG-001).
2. A bidder's contract total silently missing (BUG-003), unless it's a
   documented data gap (see `BOQExtraction.data_gap`, e.g. ELMEC).
3. A lot's CIF/Erection split wildly asymmetric vs. peer bidders for the
   same lot, with no flag already explaining why (BUG-002's symptom —
   AL Geemi's misattributed lots showed exactly this shape).

Checks run against whatever's under data/power/ — the same sample data
the app itself serves.
"""

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from .analysis.comparator import compare_round
from .extraction.excel_parser import BOQExtraction
from .extraction.router import parse_bidder_folder_pdf

DATA_DIR = Path(__file__).parent.parent / "data"

# Mirrors the exact patterns pdf_parser.py / ocr_parser.py already filter
# out during parsing (BUG-001) — this check exists to catch a regression
# in that filtering, not to duplicate it as the primary guard. Real BOQ
# item numbers can legitimately look like "Item - 4.5", so the item_no
# pattern below is anchored ($) to only match a *bare* "item N" with
# nothing after it — the actual recap-row shape — not a real line item.
DESC_KEYWORDS = (
    "total price", "sub total", "subtotal", "total lot",
    "total contract", "grand total", "u.a.e. dirhams",
)
ITEM_NO_KEYWORDS = ("sub total", "grand total", "total")
ITEM_RECAP_RE = re.compile(r"^item\s*-?\s*\d+$", re.IGNORECASE)

# A lot is "wildly asymmetric" if CIF is this much of the total...
UNBALANCED_SHARE = 0.9
# ...*and* it diverges from what peer bidders show for that same lot by
# more than this — a uniformly front-loaded lot (everyone's CIF-heavy,
# e.g. supply-dominated scope) isn't a red flag; one bidder alone being
# far outside the peer pattern is.
PEER_DIVERGENCE = 0.15


def check_subtotal_leaks(extractions: dict[str, BOQExtraction]) -> list[str]:
    problems = []
    for bidder, ext in extractions.items():
        for lot in ext.lots:
            for sheet in lot.sheets:
                for item in sheet.items:
                    if item.is_section_header:
                        continue
                    desc_lower = (item.description or "").lower()
                    item_lower = (item.item_no or "").lower().strip()
                    is_recap = (
                        any(kw in desc_lower for kw in DESC_KEYWORDS)
                        or any(kw in item_lower for kw in ITEM_NO_KEYWORDS)
                        or ITEM_RECAP_RE.match(item_lower)
                    )
                    if is_recap:
                        problems.append(
                            f"{bidder} / {lot.lot_name} / sheet '{sheet.name}': "
                            f"item '{item.item_no}' looks like a subtotal/recap row "
                            f"parsed as a real line item: {item.description!r}"
                        )
    return problems


def check_missing_contract_totals(extractions: dict[str, BOQExtraction]) -> list[str]:
    problems = []
    for bidder, ext in extractions.items():
        if ext.data_gap:
            continue  # documented gap (e.g. ELMEC) — not a silent failure
        if ext.total_contract_price is None:
            problems.append(
                f"{bidder}: total_contract_price is None and no data_gap is set "
                f"— either a real extraction failure or an undocumented gap"
            )
    return problems


def check_unflagged_unbalanced_lots(
    extractions: dict[str, BOQExtraction], flags
) -> list[str]:
    problems = []
    already_flagged = {
        (f.bidder, f.lot) for f in flags if f.category in ("unbalanced", "cross_lot", "missing")
    }

    peer_ratios: dict[int, list[float]] = defaultdict(list)
    per_bidder_ratio: dict[tuple[str, int, str], float] = {}

    for bidder, ext in extractions.items():
        if ext.data_gap:
            continue
        for lot in ext.lots:
            if lot.total_cif is None or lot.total_erection is None:
                continue
            total = lot.total_cif + lot.total_erection
            if total <= 0:
                continue
            ratio = lot.total_cif / total
            peer_ratios[lot.lot_number].append(ratio)
            per_bidder_ratio[(bidder, lot.lot_number, lot.lot_name)] = ratio

    for (bidder, lot_number, lot_name), ratio in per_bidder_ratio.items():
        peers = peer_ratios[lot_number]
        if len(peers) < 2:
            continue
        peer_median = statistics.median(peers)
        if ratio > UNBALANCED_SHARE and abs(ratio - peer_median) > PEER_DIVERGENCE:
            if (bidder, lot_name) not in already_flagged:
                problems.append(
                    f"{bidder} / {lot_name}: CIF is {ratio:.0%} of the lot total "
                    f"(peer median {peer_median:.0%}) — wildly asymmetric vs. peers "
                    f"with no 'unbalanced'/'cross_lot' flag explaining it"
                )
    return problems


def run() -> int:
    power_dir = DATA_DIR / "power"
    extractions: dict[str, BOQExtraction] = {}
    for bidder_dir in sorted(power_dir.iterdir()):
        if not bidder_dir.is_dir():
            continue
        exts = parse_bidder_folder_pdf(bidder_dir, bidder_dir.name)
        if exts:
            extractions[bidder_dir.name] = exts[0]

    if not extractions:
        print("REGRESSION CHECK FAILED — no bidder data extracted at all.")
        return 1

    comparison = compare_round(extractions, "original")

    problems: list[str] = []
    problems += check_subtotal_leaks(extractions)
    problems += check_missing_contract_totals(extractions)
    problems += check_unflagged_unbalanced_lots(extractions, comparison.flags)

    if problems:
        print(f"REGRESSION CHECK FAILED — {len(problems)} issue(s):\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(
        f"Regression check passed — {len(extractions)} bidders, "
        f"{sum(len(e.lots) for e in extractions.values())} lots, "
        f"{len(comparison.flags)} flags, no unresolved data-quality issues."
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
