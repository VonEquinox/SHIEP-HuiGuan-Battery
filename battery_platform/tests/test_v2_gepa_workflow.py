"""Automatic GEPA publication and accounting with explicitly test-only clients."""
from __future__ import annotations

import copy
import json

import pytest

from app import api_evolution
from app.agent import run_agent
from app.db import execute, now, obj, one, tx
from app.jobs import extension_handler
from test_platform import seed
from test_v2_workflow import work_job
from test_v2_gepa_service import Client, cases


@pytest.fixture(autouse=True)
def offline_provider(monkeypatch):
    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)
    monkeypatch.delenv("BATTERY_GEPA_BATCH_SIZE", raising=False)


def feedback_roots(admin):
    asset = seed(admin)
    response = admin.post("/api/demo/events", json={"asset_id": asset["id"], "scenario": "sensor-temperature"})
    assert response.status_code == 200, response.text
    for index in range(2):
        response = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()},
                              headers={"Idempotency-Key": f"gepa-root-{index}"})
        assert response.status_code == 202, response.text
        run = response.json()
        assert work_job(run["job_id"])["status"] == "succeeded"
        report = admin.get(f"/api/v2/agent/runs/{run['run_id']}").json()["report"]
        response = admin.post(f"/api/v2/diagnostic-sessions/{run['session_id']}/feedback", json={"report_id": report["id"],
                              "free_text": f"第{index + 1}个独立回放：仪表条件仍不明确，不能确认物理根因。", "provenance": "synthetic",
                              "client_submission_id": f"gepa-feedback-{index}"})
        assert response.status_code == 201, response.text
        job = work_job(response.json()["job_id"])
        assert job["status"] == "succeeded", job["error"]


def admit_batch(admin, monkeypatch):
    feedback_roots(admin)
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) is None  # default is 50 distinct roots
    monkeypatch.setenv("BATTERY_GEPA_BATCH_SIZE", "2")
    with tx() as c:
        identifier = api_evolution.schedule_context_gepa(c)
        assert identifier and api_evolution.schedule_context_gepa(c) is None
        base = api_evolution.ensure_context(c)
    return identifier, base


class CandidateClient(Client):
    """A deterministic contractual fixture, never an actual cloud provider."""
    def generate_json(self, messages, schema=None):
        self.account()
        inputs = json.loads(messages[-1]["content"])
        assert "EVAL_SECRET" not in json.dumps(inputs)
        return {"candidates": [
            {"candidate_id": "unsafe-fixture", "skill_id": inputs["skill_id"], "fields": {"allowed_tools": ["approve"]}},
            {"candidate_id": "safe-fixture", "skill_id": inputs["skill_id"],
             "fields": {"instructions": "Test-only revision: preserve uncertain observations and competing explanations."},
             "supporting_root_ids": [event["root_scenario_id"] for event in inputs["feedback_events"]]}]}


def contractual_runner(payload, *, llm, skill_library, context_store):
    llm.account()
    result = run_agent(payload, llm=False, skill_library=skill_library, context_store=context_store)
    # Explicitly injected contract marker allows scorer-path testing without
    # pretending these deterministic reports are evidence of cloud quality.
    result["run"].update(cloud_report_valid=True, execution_mode="test_only_contract_stub", llm_request_count=1,
                         llm_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
    return result


def inject_search(monkeypatch):
    import app.agent.gepa_service as service_module
    client = CandidateClient()
    factory = service_module.GEPAService
    def deterministic_service(content_root, **kwargs):
        return factory(content_root, **{**kwargs, "selection_count": 2, "candidate_budget": 2}, llm=client,
                       runner=contractual_runner, selection_cases=cases())
    monkeypatch.setattr(service_module, "GEPAService", deterministic_service)
    return client


def test_automatic_distinct_feedback_batch_without_cloud_is_explicit_no_update(admin, monkeypatch):
    identifier, base = admit_batch(admin, monkeypatch)
    job = work_job(identifier)
    assert job["status"] == "succeeded", job["error"]
    result = obj(job["result"])
    assert result["state"] == "no_update"
    assert result["validation"]["reason"] == "cloud_candidate_client_not_configured"
    assert result["metrics"]["rollouts"] == result["metrics"]["provider_requests"] == 0
    assert result["context_snapshot_id"] is None
    with tx() as c:
        assert api_evolution.ensure_context(c)["id"] == base["id"]
        assert api_evolution.schedule_context_gepa(c) is None


@pytest.mark.parametrize("publication", ["activate", "cancel", "conflict"])
def test_gepa_stages_candidate_and_checks_final_cancel_and_context_cas(admin, monkeypatch, publication):
    identifier, base = admit_batch(admin, monkeypatch)
    client = inject_search(monkeypatch)
    if publication == "conflict":
        original = extension_handler("context_gepa")["compute"]
        def concurrent_context(request, cancelled):
            result = original(request, cancelled)
            with tx() as c:
                current = api_evolution.ensure_context(c)
                snapshot = copy.deepcopy(obj(current["content"]))
                snapshot["context_snapshot_id"] = "test-only-concurrent-context"
                api_evolution.publish_snapshot(c, current, snapshot, [], {"passed": True, "test_only": True}, request["run"]["created_by"])
            return result
        monkeypatch.setitem(extension_handler("context_gepa"), "compute", concurrent_context)
    job = work_job(identifier, cancel_after_compute=publication == "cancel")
    assert client.request_count == 5 and client.total_usage["total_tokens"] == 75
    with tx() as c:
        current = api_evolution.ensure_context(c)
        fields = obj(current["content"])["skills"]["data-quality"]
        if publication == "cancel":
            assert job["status"] == "cancelled" and current["id"] == base["id"] and not fields
            run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": identifier})
            assert run["status"] == "cancelled" and run["result_snapshot_id"] is None
            metrics = obj(run["metrics"])
            assert metrics["provider_requests"] == 5 and metrics["provider_usage"]["total_tokens"] == 75
            assert metrics["rollouts"] == 6 and metrics["accounting_only"] is True
            return
        assert job["status"] == "succeeded", job["error"]
        result = obj(job["result"])
        metrics = result["metrics"]
        # One rejected schema candidate still consumes two reserved rollouts.
        assert metrics["rollouts"] == 6 and metrics["provider_requests"] == 5
        assert metrics["provider_usage"]["total_tokens"] == 75
        assert metrics["provider_failed_requests"] == 0
        assert any(candidate["state"] == "rejected" for candidate in metrics["candidate_evaluation"])
        assert len(metrics["selection_root_ids"]) == 2
        if publication == "activate":
            assert result["state"] == "active" and current["id"] != base["id"]
            assert fields["instructions"].startswith("Test-only revision")
        else:
            assert result["state"] == "conflicted" and not fields
            assert obj(current["content"])["context_snapshot_id"] == "test-only-concurrent-context"


@pytest.mark.parametrize("cancel", [False, True])
def test_experiment_preserves_total_candidate_budget_and_provider_accounting(admin, monkeypatch, cancel):
    from app.agent import ReplayEvaluator
    # Exercise the real aggregation and publication adapter with bounded scorer
    # fixtures; this is neither a quality experiment nor a sealed evaluation.
    visible_cases = [{**case, "case_id": f"evo-{index}", "root_scenario_id": f"evo-{index}", "split": "evolution",
                      "feedback": {"free_text": "Retain competing explanations", "evidence_ids": ["e"]}} for index, case in enumerate(cases())]
    monkeypatch.setattr(api_evolution, "_evaluation_cases", lambda ids, split: visible_cases)
    client = inject_search(monkeypatch)
    original = ReplayEvaluator.evaluate
    def fixture_replay(self, *args, **kwargs):
        kwargs.update(replay_environment=None, replay_authorized_test_ids=[], llm=False, runner=contractual_runner)
        # The direct reports use the same marked fixture client so the API's
        # direct-vs-search accounting can be distinguished and checked.
        kwargs["llm"] = client
        return original(self, *args, **kwargs)
    monkeypatch.setattr(ReplayEvaluator, "evaluate", fixture_replay)
    with tx() as c:
        base = api_evolution.ensure_context(c)
    payload = {"method": "gepa", "base_version": base["context_version"], "case_ids": ["evo-0", "evo-1"], "split": "evolution", "max_rollouts": 20, "activate": False}
    response = admin.post("/api/v2/evolution/experiments", json=payload, headers={"Idempotency-Key": "test-only-budget"})
    assert response.status_code == 202, response.text
    job = work_job(response.json()["job_id"], cancel_after_compute=cancel)
    if cancel:
        assert job["status"] == "cancelled"
        with tx() as c:
            run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
            assert run["status"] == "cancelled" and run["result_snapshot_id"] is None
            metrics = obj(run["metrics"])
            assert metrics["rollouts"] == 8 and metrics["provider_requests"] == 7 and metrics["provider_usage"]["total_tokens"] == 105
            assert metrics["budget"]["gepa_rollouts_used"] == 6 and metrics["accounting_only"] is True
            assert api_evolution.ensure_context(c)["id"] == base["id"]
        return
    assert job["status"] == "succeeded", job["error"]
    result = obj(job["result"])
    assert result["budget"]["rollouts"] == 8  # two direct roots plus six reserved dev comparisons
    assert result["budget"]["direct_root_count"] == 2 and result["budget"]["gepa_rollouts_used"] == 6
    assert result["metrics"]["gepa_status"] == "candidate_selection_executed"
    assert result["metrics"]["provider_requests"] == 7 and client.request_count == 7
    assert result["metrics"]["provider_usage"]["total_tokens"] == 105
    assert len(result["metrics"]["gepa_telemetry"]["selection_root_ids"]) == 2
    with tx() as c:
        evaluation = one(c, "SELECT * FROM evaluation_runs WHERE evolution_run_id=:i", {"i": response.json()["evolution_run_id"]})
        assert obj(evaluation["budget"]) == result["budget"]
        assert obj(evaluation["metrics"])["provider_requests"] == 7
        assert api_evolution.ensure_context(c)["id"] == base["id"]


def test_failed_dev_comparisons_still_consume_budget_and_report_failure_costs(admin, monkeypatch):
    identifier, base = admit_batch(admin, monkeypatch)
    import app.agent.gepa_service as service_module
    client = CandidateClient()
    factory = service_module.GEPAService
    def failing_runner(*args, **kwargs):
        client.account()
        client.failed_request_count += 1
        raise RuntimeError("test-only provider failure")
    def failure_service(content_root, **kwargs):
        return factory(content_root, **{**kwargs, "selection_count": 2, "candidate_budget": 2}, llm=client,
                       runner=failing_runner, selection_cases=cases())
    monkeypatch.setattr(service_module, "GEPAService", failure_service)
    job = work_job(identifier)
    assert job["status"] == "succeeded", job["error"]
    result = obj(job["result"])
    assert result["state"] == "no_update"
    metrics = result["metrics"]
    assert metrics["rollouts"] == 6  # first failed case does not make a comparison falsely cheap
    assert metrics["provider_requests"] == 3 and metrics["provider_failed_requests"] == 2
    assert metrics["provider_usage"]["total_tokens"] == 45
    assert all(candidate["state"] == "rejected" for candidate in metrics["candidate_evaluation"])
    with tx() as c:
        assert api_evolution.ensure_context(c)["id"] == base["id"]


def test_mid_comparison_cancel_retains_spent_cost_without_activation(admin, monkeypatch):
    identifier, base = admit_batch(admin, monkeypatch)
    import app.agent.gepa_service as service_module
    client = CandidateClient()
    factory = service_module.GEPAService
    def cancel_runner(*args, **kwargs):
        result = contractual_runner(*args, **kwargs)
        with tx() as c:
            execute(c, "UPDATE jobs SET cancel_requested=1 WHERE id=:i", {"i": identifier})
        return result
    def cancelling_service(content_root, **kwargs):
        return factory(content_root, **{**kwargs, "selection_count": 2, "candidate_budget": 2}, llm=client,
                       runner=cancel_runner, selection_cases=cases())
    monkeypatch.setattr(service_module, "GEPAService", cancelling_service)
    job = work_job(identifier)
    assert job["status"] == "cancelled", job["error"]
    with tx() as c:
        run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:i", {"i": identifier})
        metrics = obj(run["metrics"])
        assert metrics["accounting_only"] is True
        assert metrics["provider_requests"] == 2 and metrics["provider_usage"]["total_tokens"] == 30
        assert metrics["rollouts"] == 2 and metrics["budget"]["gepa_rollouts_used"] == 2
        assert run["result_snapshot_id"] is None and api_evolution.ensure_context(c)["id"] == base["id"]
