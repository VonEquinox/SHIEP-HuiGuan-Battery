"""Actual authorized measurement API feeds the existing MAD/correlation worker.

All readings are declared synthetic fixtures on simulated assets. They are
neither real station data nor numerical laboratory package outputs.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import api_agent
from app.db import now, obj, one, rows, tx
from app.jobs import extension_handler
from app.main import app
from conftest import sign_in
from test_v2_group_workflow import group_order
from test_v2_workflow import observation, work_job


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)


def collected_signals(admin, *, mode="valid"):
    primary, peer, order = group_order(admin)
    earlier_cutoff = now()
    ids = []
    with TestClient(app) as technician:
        sign_in(technician, "admin" if mode == "qualification_unverified" else "tech")
        roles = ("not_reference", "declared_normal") if mode == "reference_after_analysis" else ("declared_normal", "not_reference")
        for role in roles:
            for index in range(3):
                measured = datetime.now(timezone.utc)
                for ordinal, asset in enumerate((primary, peer)):
                    context = {"chemistry": "LFP", "protocol_id": "synthetic-protocol-v1", "load_condition": "declared_rest",
                               "temperature_condition": "declared_25C", "source_cohort_id": "synthetic-same-acquisition-v1", "reference_status": role}
                    if mode == "different_conditions" and ordinal:
                        context["load_condition"] = "declared_charge"
                    if mode == "unknown_chemistry":
                        context["chemistry"] = "unknown"
                    body = {**observation(asset, order, f"group-numeric-{role}-{index}-{ordinal}"), "asset_id": asset["id"],
                            "measured_at": (measured + timedelta(milliseconds=1) if mode == "misaligned" and ordinal else measured).isoformat(),
                            "comparison_context": None if mode == "missing_conditions" else context,
                            "free_text": "Synthetic reference declaration" if role == "declared_normal" else "Synthetic later anomaly-series observation"}
                    body["measurements"][0]["value"] = 1 if mode == "constant_reference" and role == "declared_normal" else index + ordinal if role == "declared_normal" else 10 + 10 * index + ordinal
                    if mode == "uncalibrated":
                        body["calibration_status"] = "unknown"
                    if mode == "experimental_replay":
                        body["provenance"] = "experimental_replay"
                    response = technician.post(f"/api/v2/orders/{order['id']}/observations", json=body)
                    assert response.status_code == 201, response.text
                    created = response.json()
                    ids.append(created["observation_id"])
                    # Drain actual extract and reassessment jobs; queue capacity
                    # cannot turn this measurement exercise into fixture SQL.
                    for key in ("extraction_job_id", "job_id"):
                        job = work_job(created[key])
                        assert job["status"] == "succeeded", job["error"]
                    with tx() as c:
                        checks = rows(c, "SELECT id FROM jobs WHERE kind='context_regression' AND status='queued'")
                    for check in checks:
                        job = work_job(check["id"])
                        assert job["status"] == "succeeded", job["error"]
    return primary, peer, ids, earlier_cutoff


def request_analysis(admin, primary, peer, *, cutoff=None, key="numeric-analyze"):
    response = admin.post("/api/v2/incidents/analyze", json={"asset_ids": [primary["id"], peer["id"]], "visible_cutoff": cutoff or now()},
                          headers={"Idempotency-Key": key})
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def test_authorized_aligned_measurements_execute_mad_outside_transaction_and_persist_association(admin, monkeypatch):
    primary, peer, ids, _ = collected_signals(admin)
    from app.diagnosis import group_adapter
    actual = group_adapter.analyze_groups
    calls = []
    def observe_real_algorithm(entities, **kwargs):
        # A second independent write transaction can be admitted while compute
        # runs, proving the actual worker did not retain its snapshot write lock.
        with tx() as c:
            assert one(c, "SELECT count(*) n FROM inspection_observations")["n"] == 12
        calls.append(entities)
        return actual(entities, **kwargs)
    monkeypatch.setattr(group_adapter, "analyze_groups", observe_real_algorithm)
    job = work_job(request_analysis(admin, primary, peer))
    assert job["status"] == "succeeded", job["error"]
    result = obj(job["result"])
    assert len(calls) == 1 and result["numeric_algorithm_executed"] is True and result["numeric_correlation_supported"] is True
    detail = admin.get(f"/api/v2/incidents/{result['group_ids'][0]}").json()
    assert detail["relation_type"] == "synchronous_association" and detail["provenance"] == "self_synthetic"
    evidence = detail["evidence"]
    assert evidence["confirmed_common_cause"] is False and evidence["numeric_support"]["causal_confirmation"] is False
    assert evidence["comparison"]["origin"] == "synthetic" and evidence["comparison"]["source_cohort_id"] == "synthetic-same-acquisition-v1"
    numeric = evidence["numeric_analysis"]
    assert numeric["threshold_version"] == "group-dev-v1"
    assert numeric["pair_evidence"][0]["correlation"] == pytest.approx(1)
    assert numeric["pair_evidence"][0]["aligned_points"] == 3
    assert set(numeric["residuals"]) == {primary["installation_id"], peer["installation_id"]}
    assert all(value > 3 for channel in numeric["residuals"].values() for value in channel.values())
    assert {source["observation_id"] for source in evidence["source_refs"]} == set(ids)
    assert {source["role"] for source in evidence["source_refs"]} == {"reference", "analysis"}


@pytest.mark.parametrize("mode,reason,executed", [
    ("missing_conditions", "comparison_conditions_missing", False),
    ("different_conditions", "no_comparable_peer_cohort", False),
    ("uncalibrated", "measurement_quality_or_calibration_unsupported", False),
    ("experimental_replay", "independent_experimental_cells_not_station_channels", False),
    ("qualification_unverified", "measurement_authorization_or_qualification_unverified", False),
    ("unknown_chemistry", "comparison_conditions_unknown", False),
    ("reference_after_analysis", "three_prior_normal_reference_and_analysis_points_required", False),
    ("constant_reference", "constant_reference_requires_separate_review", True),
    ("misaligned", "insufficient_nonconstant_aligned_residuals", True),
])
def test_ineligible_or_degenerate_signals_do_not_become_numeric_group(admin, mode, reason, executed):
    primary, peer, _, _ = collected_signals(admin, mode=mode)
    job = work_job(request_analysis(admin, primary, peer))
    assert job["status"] == "succeeded", job["error"]
    result = obj(job["result"])
    assert result["numeric_correlation_supported"] is False and result["numeric_algorithm_executed"] is executed
    detail = admin.get(f"/api/v2/incidents/{result['group_ids'][0]}").json()
    assert detail["relation_type"] == "topology_association"
    assert detail["evidence"]["numeric_support"]["status"] == "unsupported"
    assert reason in str(detail["evidence"]) and detail["evidence"]["confirmed_common_cause"] is False


def test_later_qualified_measurements_cannot_enable_earlier_group_cutoff(admin):
    primary, peer, _, earlier_cutoff = collected_signals(admin)
    job = work_job(request_analysis(admin, primary, peer, cutoff=earlier_cutoff))
    assert job["status"] == "succeeded", job["error"]
    result = obj(job["result"])
    assert result["numeric_algorithm_executed"] is False and result["numeric_correlation_supported"] is False
    assert not result["numeric_analyses"]


def test_source_correction_during_numeric_compute_rejects_stale_publication(admin, monkeypatch):
    primary, peer, ids, _ = collected_signals(admin)
    identifier = request_analysis(admin, primary, peer)
    handler = extension_handler("incident_analysis")
    compute = handler["compute"]
    def compute_then_correct(request, cancelled):
        result = compute(request, cancelled)
        assert result["numeric_correlation_supported"] is True
        with tx() as c:
            source = one(c, "SELECT * FROM inspection_observations WHERE id=:i", {"i": ids[0]})
        response = admin.post(f"/api/v2/observations/{ids[0]}/facts", json={"version": source["version"],
                              "candidate_facts": obj(source["candidate_facts"], []), "note": "实际接口并行核对来源事实"})
        assert response.status_code == 200, response.text
        return result
    monkeypatch.setitem(handler, "compute", compute_then_correct)
    with tx() as c:
        before = one(c, "SELECT count(*) n FROM incident_groups")["n"]
    job = work_job(identifier)
    assert job["status"] == "failed" and "来源观察" in job["error"]
    with tx() as c:
        assert one(c, "SELECT count(*) n FROM incident_groups")["n"] == before
