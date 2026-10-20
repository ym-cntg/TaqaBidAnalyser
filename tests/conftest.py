"""Shared test fixtures.

The guiding constraint: every test here must run with no Databricks
connection and no Unity Catalog grant. CI has neither, and a suite that
needs them is a suite that does not run.

That is achievable because the overlay reads in comparison.py are all
fail-open and the engines accept an injected source, so the whole
comparison, round-tracking and report stack can be driven from
in-memory data.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Real vendor spreadsheets, trimmed to the smallest set that still covers
# both templates, two vendors, two rounds and one genuinely inconsistent
# file. The full 105-file corpus lives in data/, which is too large to
# commit; tests that want it skip when it is absent.
POWER_V1_ORIGINAL = FIXTURES / "power-original.xlsx"
POWER_V1_ROUND1 = FIXTURES / "power-round1.xlsx"
POWER_V2_ORIGINAL = FIXTURES / "power-vendor2-original.xlsx"
POWER_V2_ROUND1 = FIXTURES / "power-vendor2-round1-inconsistent.xlsx"
WATER_ORIGINAL = FIXTURES / "water-A-20669-original.xlsx"

DATA_DIR = Path(__file__).parent.parent / "data"
needs_full_corpus = pytest.mark.skipif(
    not DATA_DIR.exists(), reason="full sample corpus (data/) is not committed"
)


@pytest.fixture
def no_overlays(monkeypatch):
    """Neutralise every grant-dependent overlay read.

    These are the five lookups that hit app-owned tables. In production
    they fail open to {} when the grant is missing, so returning {} here
    is the same state the deployed app is in today, not an artificial
    one.
    """
    import backend.api.comparison as cmp

    for name in (
        "_fetch_corrections",
        "_fetch_technical_status",
        "_fetch_manual_disqualifications",
        "_fetch_partial_bids",
        "_fetch_user_names",
    ):
        monkeypatch.setattr(cmp, name, lambda *a, **k: {})
    return cmp


class Row:
    """Stands in for a warehouse row, which the engines consume by
    attribute access."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture
def maximo(monkeypatch, no_overlays):
    """A minimal Maximo-shaped RFQ: two vendors, one line, one revision.

    Returns the list of fetch names that were actually called, so a test
    can assert the Maximo path still reads Maximo rather than quietly
    going through the upload adapter.
    """
    import backend.api.comparison as cmp
    import backend.api.round_snapshots as rs
    import backend.api.rounds as rnd

    called: list[str] = []
    rows = [
        Row(RFQLINENUM=1.0, VENDOR="A", DESCRIPTION="Panel", ORDERQTY=2.0,
            ORDERUNIT="Nos", UNITCOST=100.0, LINECOST=200.0),
        Row(RFQLINENUM=1.0, VENDOR="B", DESCRIPTION="Panel", ORDERQTY=2.0,
            ORDERUNIT="Nos", UNITCOST=130.0, LINECOST=260.0),
    ]
    history = [
        Row(VENDOR="A", REVISION=1.0, RFQLINENUM=1.0, LINECOSTWDIS=150.0),
        Row(VENDOR="B", REVISION=1.0, RFQLINENUM=1.0, LINECOSTWDIS=120.0),
    ]
    roster = {"A": "Alpha", "B": "Beta"}

    monkeypatch.setattr(cmp, "_fetch_vendor_roster",
                        lambda r: (called.append("roster"), roster)[1])
    monkeypatch.setattr(cmp, "_fetch_quotationlines",
                        lambda r: (called.append("lines"), rows)[1])
    monkeypatch.setattr(rs, "_fetch_original_lines",
                        lambda r: {("A", 1.0): 200.0, ("B", 1.0): 260.0})
    monkeypatch.setattr(rs, "_fetch_discount_history_lines", lambda r: history)
    # rounds.py imports the roster function by name, so it holds its own
    # reference and has to be patched separately.
    monkeypatch.setattr(rnd, "_fetch_vendor_roster", lambda r: roster)
    monkeypatch.setattr(rnd, "_fetch_discount_history_dates", lambda r: {})
    monkeypatch.setattr(rnd, "_fetch_line_descriptions", lambda r: {1.0: "Panel"})
    return called


def make_uploaded(rounds: dict[str, dict[str, float]], qty: float = 10.0, lines: int = 2):
    """An uploaded BOQ driven straight from numbers.

    `rounds` maps a round label to {vendor: unit_cost}, applied to every
    line, which keeps the arithmetic in a test obvious.
    """
    from backend.uploads.models import UploadedBoq, UploadedLine, UploadedPrice
    from backend.uploads.source import UploadedSource

    boq = UploadedBoq(project_id="p", name="P", created_by="u", created_by_label=None,
                      created_at=dt.datetime.now(dt.timezone.utc))
    boq.vendor_names = {v: v.title() for per in rounds.values() for v in per}
    for n in range(1, lines + 1):
        boq.lines[float(n)] = UploadedLine(line_number=float(n), item_no=f"1.{n}",
                                           description=f"Item {n}", unit="Nos", quantity=qty)
    for label, per_vendor in rounds.items():
        for vendor, unit_cost in per_vendor.items():
            for n in range(1, lines + 1):
                boq.prices[(float(n), vendor, label)] = UploadedPrice(
                    line_number=float(n), vendor=vendor, round_label=label,
                    unit_cost=unit_cost, line_cost=unit_cost * qty,
                )
    return UploadedSource(boq)
