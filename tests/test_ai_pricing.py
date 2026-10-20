"""AI pricing must degrade, never error.

Every failure mode here was a real 500 at some point: an unreachable
endpoint, a client that cannot authenticate, a hang, and an unparseable
response.
"""

from __future__ import annotations

import time

import pytest

import backend.api.ai_pricing as ai

COMPARISON = {
    "round": "original",
    "total_line_count": 2,
    "lines": [
        {"rfqlinenum": 1.0, "description": "GIS", "qty": 3.0, "unit": "Nos", "prices": {
            "A": {"unit_cost": 100.0, "unquoted": False, "zero_price": False},
            "B": {"unit_cost": 140.0, "unquoted": False, "zero_price": False},
            "C": {"unit_cost": 900.0, "unquoted": False, "zero_price": False}}},
        # Nobody quoted this one, so there is no honest fallback figure.
        {"rfqlinenum": 2.0, "description": "Spare", "qty": 1.0, "unit": "Set", "prices": {
            "A": {"unit_cost": None, "unquoted": True, "zero_price": False}}},
    ],
}


class Unreachable:
    def __init__(self, *a, **k):
        self.serving_endpoints = self

    def query(self, **k):
        raise RuntimeError("PERMISSION_DENIED: no Can Query grant")


class Unauthenticated:
    def __init__(self, *a, **k):
        raise ValueError("default auth: cannot configure default credentials")


class Hangs:
    def __init__(self, *a, **k):
        self.serving_endpoints = self

    def query(self, **k):
        time.sleep(300)


class Garbage:
    def __init__(self, *a, **k):
        self.serving_endpoints = self

    def query(self, **k):
        class R:
            choices = [type("C", (), {"message": type("M", (), {"content": "I cannot help."})()})()]
        return R()


@pytest.fixture
def quick_budget(monkeypatch):
    monkeypatch.setattr(ai, "MODEL_BUDGET_SECONDS", 3)
    monkeypatch.setattr(ai, "BATCH_TIMEOUT_SECONDS", 10)
    monkeypatch.setenv("DATABRICKS_LLM_ENDPOINT", "test-endpoint")
    monkeypatch.setattr(ai, "build_comparison", lambda *a, **k: COMPARISON)


@pytest.mark.parametrize(
    "client,label",
    [(Unreachable, "endpoint rejects"), (Unauthenticated, "client cannot be built"),
     (Hangs, "endpoint hangs"), (Garbage, "response unparseable")],
)
def test_every_failure_mode_still_returns_prices(monkeypatch, quick_budget, client, label):
    monkeypatch.setattr(ai, "WorkspaceClient", client)
    result = ai.build_ai_pricing("RFQ-1")
    assert result["degraded"] is True
    assert result["fallback_reason"]
    # The unquoted line gets nothing, which is correct.
    assert len(result["lines"]) == 1
    assert all(l["source"] == "heuristic" for l in result["lines"])


def test_fallback_is_the_median_not_the_mean(monkeypatch, quick_budget):
    monkeypatch.setattr(ai, "WorkspaceClient", Unreachable)
    result = ai.build_ai_pricing("RFQ-1")
    # 100, 140, 900 -> median 140, so one extreme bid cannot drag it.
    assert result["lines"][0]["unit_cost"] == 140.0
    assert result["lines"][0]["line_cost"] == 420.0


def test_a_hang_is_bounded_by_the_total_budget(monkeypatch, quick_budget):
    """The request passes through the Next.js proxy and the Databricks
    gateway. Exceeding their limits surfaces as a 500 the app never
    produced and cannot catch."""
    monkeypatch.setattr(ai, "WorkspaceClient", Hangs)
    started = time.monotonic()
    ai.build_ai_pricing("RFQ-1")
    assert time.monotonic() - started < ai.MODEL_BUDGET_SECONDS + 4


def test_unquoted_line_gets_no_invented_figure(monkeypatch, quick_budget):
    monkeypatch.setattr(ai, "WorkspaceClient", Unreachable)
    result = ai.build_ai_pricing("RFQ-1")
    assert all(l["rfqlinenum"] != 2.0 for l in result["lines"])


def test_source_is_threaded_through_to_the_comparison(monkeypatch, quick_budget):
    sentinel = object()
    seen = {}

    def fake(rfqnum, round_label=None, source=None):
        seen["source"] = source
        return COMPARISON

    monkeypatch.setattr(ai, "build_comparison", fake)
    monkeypatch.setattr(ai, "WorkspaceClient", Unreachable)
    ai.build_ai_pricing("RFQ-1", source=sentinel)
    assert seen["source"] is sentinel
