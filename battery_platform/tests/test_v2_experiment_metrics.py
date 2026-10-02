"""Actual scorer → job publication → list/detail metric contract regressions."""
from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.agent import ReplayEvaluator
from app.agent.experiment_metrics import ExperimentMetrics, aggregate_experiment_metrics, public_metrics
from app import api_evolution
from app.db import tx, one, obj, execute, js


def cases():
    return [{"case_id": f"metrics-{i}", "root_scenario_id": f"metrics-{i}", "split": "dev", "synthetic": True,
             "initial_visible": {"asset_id": "metrics-asset", "installation_id": "metrics-installation",
                "visible_cutoff": "2026-09-01T12:00:00Z", "asset": {"chemistry": "LFP"},
                "observations": [{"evidence_id": f"ev-{i}", "summary": "Unresolved observed channel"}], "test_catalog": []},
             "hidden_truth": {"unresolved": True, "independently_labeled": True, "requires_inspection": i == 0}}
            for i in range(2)]


def test_rates_use_distinct_positive_negative_denominators_and_zero_is_valid():
    metrics = aggregate_experiment_metrics([
        {"metrics": {"diagnosis_correct": 1, "fact_count": 0, "grounded_fact_count": 0, "test_count": 0,
                     "unsafe_test_count": 0, "missed": 1, "false_alarm": 0}},
        {"metrics": {"diagnosis_correct": 0, "fact_count": 2, "grounded_fact_count": 1, "test_count": 2,
                     "unsafe_test_count": 0, "missed": 0, "false_alarm": 0}},
    ], cases())
    assert metrics["misses"] == 1 and metrics["miss_rate"] == 1.0
    assert metrics["false_alarms"] == 0 and metrics["false_positive_rate"] == 0.0
    assert metrics["denominators"] == {"diagnosis_roots": 2, "facts": 2, "independently_labeled_roots": 2,
                                      "inspection_positive_roots": 1, "inspection_negative_roots": 1}
    with pytest.raises(ValidationError):
        ExperimentMetrics.model_validate({**metrics, "false_positive_rate": 0.5})
    with pytest.raises(ValidationError):
        ExperimentMetrics.model_validate({**metrics, "diagnostic_accuracy": 0.5})
    legacy = public_metrics({"diagnosis_accuracy": 0.5, "false_alarms": 1, "misses": 1})
    assert legacy["values"]["false_alarms"] == 1
    assert legacy["values"]["false_positive_rate"] is None
    assert "false_positive_rate" in legacy["unsupported"]


def test_actual_replay_completion_publishes_metrics_protocol_and_unsupported(admin, monkeypatch):
    monkeypatch.setattr(api_evolution, "_evaluation_cases", lambda requested, split: cases())
    base = admin.get("/api/v2/overview").json()["context_version"]
    submitted = admin.post("/api/v2/evolution/experiments", json={"method": "fixed", "base_version": base,
        "case_ids": [case["case_id"] for case in cases()], "split": "dev", "max_rollouts": 2, "activate": False},
        headers={"Idempotency-Key": "metrics-completion"})
    assert submitted.status_code == 202, submitted.text
    with tx() as c:
        job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": submitted.json()["job_id"]})
        request = api_evolution.evolution_snapshot(c, job)
    # Actual evaluator and executor run locally. No cloud or label-field mock.
    result = api_evolution.evolution_compute(request, lambda: False)
    with tx() as c:
        completed = api_evolution.evolution_complete(c, job, result, request)
        execute(c, "UPDATE jobs SET status='succeeded',result=:r WHERE id=:i", {"r": js(completed), "i": job["id"]})
    listed = admin.get("/api/v2/evolution/runs").json()
    run = next(item for item in listed["items"] if item["id"] == submitted.json()["id"])
    assert {definition["key"] for definition in listed["metrics_contract"]["definitions"]} >= {
        "diagnosis_accuracy", "grounded_assertion_ratio", "misses", "false_alarms", "miss_rate", "false_positive_rate"}
    measured = run["experiment_metrics"]
    assert measured["values"]["diagnosis_accuracy"] == result["metrics"]["diagnosis_accuracy"]
    assert measured["values"]["false_alarms"] == result["metrics"]["false_alarms"]
    assert measured["values"]["denominators"]["inspection_negative_roots"] == 1
    assert "score" in measured["unsupported"]
    assert run["experiment_protocol"]["method"] == "fixed"
    assert run["experiment_protocol"]["split"] == "dev"
    assert run["experiment_protocol"]["protocol_version"] == "root-replay.v1"
    assert run["experiment_protocol"]["execution_modes"] == ["rule_baseline"]
    assert run["experiment_protocol"]["llm_models"] == []
    assert len(run["experiment_protocol"]["protocol_id"]) == 64
    detail = admin.get(f"/api/v2/evolution/runs/{run['id']}").json()
    assert detail["experiment_metrics"] == measured
    assert detail["experiment_protocol"] == run["experiment_protocol"]
    assert detail["evaluations"][0]["protocol"]["metric_schema_version"] == "experiment-metrics.v1"
    assert "hidden_truth" not in str(detail)
