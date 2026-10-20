"""The Excel upload path end to end, over HTTP, with no Databricks.

This is the closest thing to the real deploy: the app under test has no
warehouse connection and no grant, which is exactly the environment the
upload feature was designed to work in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import (
    POWER_V1_ORIGINAL,
    POWER_V1_ROUND1,
    POWER_V2_ORIGINAL,
    POWER_V2_ROUND1,
)

OCTET = {"Content-Type": "application/octet-stream"}


@pytest.fixture
def client():
    return TestClient(app)


def upload(client, pid, path, vendor, round_label):
    """The endpoint takes the spreadsheet as a raw body with its
    metadata in the query string, so no multipart dependency is needed
    at deploy time."""
    return client.post(
        f"/api/uploads/{pid}/files",
        params={"vendor": vendor, "round_label": round_label, "filename": path.name,
                "vendor_name": vendor.title()},
        content=path.read_bytes(),
        headers=OCTET,
    )


@pytest.fixture
def project(client):
    res = client.post("/api/uploads", json={"name": "Test tender", "user_id": "u1"})
    assert res.status_code == 201
    return res.json()["project_id"]


@pytest.fixture
def loaded(client, project):
    """Two vendors across two rounds, from real spreadsheets."""
    for path, vendor, rnd in [
        (POWER_V1_ORIGINAL, "AGPOWER", "original"),
        (POWER_V1_ROUND1, "AGPOWER", "1"),
        (POWER_V2_ORIGINAL, "GEEMI", "original"),
        (POWER_V2_ROUND1, "GEEMI", "1"),
    ]:
        assert upload(client, project, path, vendor, rnd).status_code == 201
    return project


class TestExtraction:
    def test_lines_match_across_vendors_rather_than_duplicating(self, client, loaded):
        state = client.get(f"/api/uploads/{loaded}").json()
        # Each file holds 322 priced lines; matched on item number they
        # collapse to one shared set rather than 1,288.
        assert state["line_count"] < 400

    def test_both_vendors_and_rounds_registered(self, client, loaded):
        state = client.get(f"/api/uploads/{loaded}").json()
        assert sorted(v["vendor"] for v in state["vendors"]) == ["AGPOWER", "GEEMI"]
        assert state["rounds"] == ["original", "1.0"]

    def test_round_label_is_normalised_to_the_engine_vocabulary(self, client, project):
        """"1" is stored as "1.0" so the store and the round-snapshot
        builder agree. Otherwise the round selector sends a value the
        comparison rejects."""
        upload(client, project, POWER_V1_ROUND1, "AGPOWER", "1")
        rounds = client.get(f"/api/uploads/{project}").json()["rounds"]
        # ORIGINAL always leads the list; the point is that "1" was
        # stored as "1.0" rather than "1".
        assert rounds == ["original", "1.0"]

    def test_extraction_cross_check_is_reported_per_file(self, client, loaded):
        subs = client.get(f"/api/uploads/{loaded}").json()["submissions"]
        bad = [s for s in subs if s["reconciles"] is False]
        # The second vendor's round-1 file genuinely contradicts itself.
        assert len(bad) == 1
        assert bad[0]["vendor"] == "GEEMI"


class TestConfirmGate:
    def test_analysis_refuses_an_unconfirmed_boq(self, client, loaded):
        for endpoint in ("comparison", "rounds", "negotiation-report"):
            assert client.get(f"/api/rfqs/{loaded}/{endpoint}").status_code == 409

    def test_confirmed_boq_is_locked_for_editing(self, client, loaded):
        first = client.get(f"/api/uploads/{loaded}").json()["lines"][0]["line_number"]
        assert client.post(f"/api/uploads/{loaded}/confirm").status_code == 200
        res = client.patch(f"/api/uploads/{loaded}/lines/{first}", json={"description": "no"})
        assert res.status_code == 409

    def test_reopen_allows_editing_again(self, client, loaded):
        client.post(f"/api/uploads/{loaded}/confirm")
        assert client.post(f"/api/uploads/{loaded}/reopen").status_code == 200
        first = client.get(f"/api/uploads/{loaded}").json()["lines"][0]["line_number"]
        assert client.patch(f"/api/uploads/{loaded}/lines/{first}",
                            json={"description": "ok"}).status_code == 200


class TestEditing:
    def test_changing_quantity_recomputes_every_line_total(self, client, loaded):
        first = client.get(f"/api/uploads/{loaded}").json()["lines"][0]["line_number"]
        res = client.patch(f"/api/uploads/{loaded}/lines/{first}", json={"quantity": 9})
        line = next(l for l in res.json()["lines"] if l["line_number"] == first)
        assert line["quantity"] == 9
        for p in line["prices"].values():
            if p["unit_cost"] and p["line_cost"]:
                assert abs(p["line_cost"] - p["unit_cost"] * 9) < 0.01

    def test_unknown_vendor_rejected(self, client, loaded):
        first = client.get(f"/api/uploads/{loaded}").json()["lines"][0]["line_number"]
        res = client.patch(f"/api/uploads/{loaded}/prices", json={
            "line_number": first, "vendor": "NOPE", "round_label": "original", "unit_cost": 1.0})
        assert res.status_code == 400

    def test_negative_quantity_rejected(self, client, loaded):
        first = client.get(f"/api/uploads/{loaded}").json()["lines"][0]["line_number"]
        assert client.patch(f"/api/uploads/{loaded}/lines/{first}",
                            json={"quantity": -5}).status_code == 400


class TestAnalysisFromUploads:
    @pytest.fixture
    def confirmed(self, client, loaded):
        client.post(f"/api/uploads/{loaded}/confirm")
        return loaded

    def test_all_three_tabs_return_data(self, client, confirmed, no_overlays):
        for endpoint in ("comparison", "comparison?round=1.0", "rounds", "negotiation-report"):
            res = client.get(f"/api/rfqs/{confirmed}/{endpoint}")
            assert res.status_code == 200, endpoint

    def test_excel_export_is_a_real_workbook(self, client, confirmed, no_overlays):
        import io
        import zipfile

        res = client.get(f"/api/rfqs/{confirmed}/negotiation-report.xlsx")
        assert res.status_code == 200
        assert zipfile.is_zipfile(io.BytesIO(res.content))

    def test_flags_are_computed_on_uploaded_data(self, client, confirmed, no_overlays):
        vendors = client.get(f"/api/rfqs/{confirmed}/comparison").json()["vendors"]
        assert any(v["unquoted_count"] or v["arithmetic_error_count"] for v in vendors)


class TestRejectedInput:
    @pytest.mark.parametrize(
        "filename,body,expected",
        [
            ("bid.pdf", b"%PDF-1.4", 400),
            ("empty.xlsx", b"", 400),
            ("corrupt.xlsx", b"not a zip at all", 400),
        ],
    )
    def test_bad_files_rejected_with_a_real_reason(self, client, project, filename, body, expected):
        res = client.post(f"/api/uploads/{project}/files",
                          params={"vendor": "X", "filename": filename},
                          content=body, headers=OCTET)
        assert res.status_code == expected
        assert res.json()["detail"]

    def test_missing_vendor_rejected(self, client, project):
        res = client.post(f"/api/uploads/{project}/files",
                          params={"vendor": "  ", "filename": "a.xlsx"},
                          content=b"PK\x03\x04", headers=OCTET)
        assert res.status_code == 400

    def test_non_numeric_round_rejected(self, client, project):
        res = client.post(f"/api/uploads/{project}/files",
                          params={"vendor": "X", "round_label": "later", "filename": "a.xlsx"},
                          content=b"PK\x03\x04", headers=OCTET)
        assert res.status_code == 400

    def test_unknown_project_is_404(self, client):
        assert client.get("/api/uploads/doesnotexist").status_code == 404


class TestFileRemoval:
    def test_removing_a_file_drops_only_its_round(self, client, loaded):
        subs = client.get(f"/api/uploads/{loaded}").json()["submissions"]
        target = next(s for s in subs if s["vendor"] == "GEEMI" and s["round_label"] == "1.0")
        after = client.delete(f"/api/uploads/{loaded}/files/{target['submission_id']}").json()
        assert any(v["vendor"] == "GEEMI" for v in after["vendors"])

    def test_vendor_dropped_once_all_their_files_are_gone(self, client, loaded):
        state = client.get(f"/api/uploads/{loaded}").json()
        for s in [x for x in state["submissions"] if x["vendor"] == "GEEMI"]:
            after = client.delete(f"/api/uploads/{loaded}/files/{s['submission_id']}").json()
        assert not any(v["vendor"] == "GEEMI" for v in after["vendors"])
