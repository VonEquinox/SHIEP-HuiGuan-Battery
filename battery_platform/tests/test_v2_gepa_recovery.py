"""Versioned GEPA admission and bounded recovery, using offline contract clients."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app import api_evolution
from app.agent import LLMError
from app.db import execute, js, now, obj, one, tx
from app.jobs import extension_handler
from test_v2_gepa_service import Client, cases
from test_v2_gepa_workflow import admit_batch, inject_search
from test_v2_workflow import work_job


@pytest.fixture(autouse=True)
def offline_provider(monkeypatch):
    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)
    monkeypatch.delenv("BATTERY_GEPA_BATCH_SIZE", raising=False)


def age_terminal(identifier):
    with tx() as c:
        execute(c, "UPDATE jobs SET finished_at=:t WHERE id=:i", {
            "t": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(), "i": identifier})


def run_id(identifier):
    with tx() as c:
        return one(c, "SELECT id FROM evolution_runs WHERE job_id=:j", {"j": identifier})["id"]


def test_transient_proposal_failure_releases_reservation_but_caps_attempts(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    import app.agent.gepa_service as module
    factory = module.GEPAService
    clients = []
    class Failed(Client):
        def generate_json(self, messages, schema=None):
            self.account()
            self.failed_request_count += 1
            raise LLMError("test-only temporary provider failure")
    def service(content_root, **kwargs):
        client = Failed()
        clients.append(client)
        return factory(content_root, **kwargs, llm=client, selection_cases=cases())
    monkeypatch.setattr(module, "GEPAService", service)
    for attempt in range(3):
        job = work_job(identifier)
        result = obj(job["result"])
        assert job["status"] == "succeeded" and result["state"] == "no_update"
        assert result["validation"]["source_consumption"] == "retryable"
        assert result["metrics"]["provider_requests"] == result["metrics"]["provider_failed_requests"] == 1
        assert result["metrics"]["provider_usage"]["total_tokens"] == 15
        with tx() as c:
            assert api_evolution.schedule_context_gepa(c) is None  # persisted backoff
        age_terminal(identifier)
        with tx() as c:
            next_identifier = api_evolution.schedule_context_gepa(c)
            if attempt < 2:
                assert next_identifier and next_identifier != identifier
                assert api_evolution.schedule_context_gepa(c) is None  # reservation
                identifier = next_identifier
            else:
                assert next_identifier is None  # bounded automatic attempts
    assert len(clients) == 3


def test_no_key_deferred_batch_unblocks_only_on_config_change(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    result = obj(work_job(identifier)["result"])
    assert result["validation"]["source_consumption"] == "deferred"
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) is None
    response = admin.post(f"/api/v2/evolution/runs/{run_id(identifier)}/retry", headers={"Idempotency-Key": "no-key-resume"})
    assert response.status_code == 503
    monkeypatch.setenv("BATTERY_LLM_API_KEY", "test-only-no-network-key")
    with tx() as c:
        resumed = api_evolution.schedule_context_gepa(c)
        assert resumed and resumed != identifier
        payload = obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": resumed})["payload"])
        assert payload["retry_of_job_ids"] == [identifier]
        assert "test-only-no-network-key" not in js(payload)


def test_context_cas_conflict_is_retryable_and_preserves_spent_costs(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    inject_search(monkeypatch)
    original = extension_handler("context_gepa")["compute"]
    def conflict(request, cancelled):
        result = original(request, cancelled)
        with tx() as c:
            current = api_evolution.ensure_context(c)
            snapshot = copy.deepcopy(obj(current["content"]))
            snapshot["context_snapshot_id"] = "test-only-cas-revision"
            api_evolution.publish_snapshot(c, current, snapshot, [], {"passed": True}, request["run"]["created_by"], automatic_regression=False)
        return result
    monkeypatch.setitem(extension_handler("context_gepa"), "compute", conflict)
    result = obj(work_job(identifier)["result"])
    assert result["state"] == "conflicted"
    assert result["validation"]["reason"] == "context_version_changed"
    assert result["validation"]["source_consumption"] == "retryable"
    assert result["metrics"]["provider_requests"] == 5
    age_terminal(identifier)
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) not in (None, identifier)


def test_feedback_revision_creates_new_source_reservation_and_old_job_cannot_read_it(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    with tx() as c:
        payload = obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": identifier})["payload"])
        for source in payload["sources"]:
            table, number = source["feedback_id"].split(":")
            execute(c, f"UPDATE {table} SET version=version+1,extraction_status='corrected' WHERE id=:i", {"i": int(number)})
        revised_identifier = api_evolution.schedule_context_gepa(c)
        assert revised_identifier and revised_identifier != identifier
        revised = obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": revised_identifier})["payload"])
        assert [source["feedback_version"] for source in revised["sources"]] == [source["feedback_version"] + 1 for source in payload["sources"]]
    old = work_job(identifier)
    assert old["status"] == "failed" and "预留来源版本已变化" in old["error"]
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) is None  # new version reserved


@pytest.mark.parametrize("terminal", ["cancelled", "interrupted"])
def test_cancel_and_restart_require_explicit_idempotent_recovery(admin, monkeypatch, terminal):
    identifier, _ = admit_batch(admin, monkeypatch)
    if terminal == "cancelled":
        response = admin.post(f"/api/jobs/{identifier}/cancel")
        assert response.status_code == 200
    else:
        # This is the same persisted transition as JobSupervisor.start(), without
        # launching a thread or provider call in the isolated database test.
        with tx() as c:
            job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": identifier})
            execute(c, "UPDATE jobs SET status='interrupted',finished_at=:t,error='test restart' WHERE id=:i", {"t": now(), "i": identifier})
            extension_handler("context_gepa")["lifecycle"](c, job, "interrupted", "test restart")
    age_terminal(identifier)
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) is None
    monkeypatch.setenv("BATTERY_LLM_API_KEY", "test-only-no-network-key")
    endpoint = f"/api/v2/evolution/runs/{run_id(identifier)}/retry"
    first = admin.post(endpoint, headers={"Idempotency-Key": "explicit-resume"})
    assert first.status_code == 202, first.text
    second = admin.post(endpoint, headers={"Idempotency-Key": "explicit-resume"})
    assert second.status_code == 202 and first.json()["job_id"] == second.json()["job_id"]
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) is None
        resumed = obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": first.json()["job_id"]})["payload"])
        assert resumed["retry_generation"] == 1 and resumed["explicit_retry"] is True
        assert all(source["retry_generation"] == 1 for source in resumed["sources"])


def test_old_failed_job_cannot_resume_a_new_revision_already_consumed(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    with tx() as c:
        payload = obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": identifier})["payload"])
        execute(c, "UPDATE jobs SET status='failed',error='test transient',finished_at=:t WHERE id=:i", {"t": now(), "i": identifier})
        for source in payload["sources"]:
            table, number = source["feedback_id"].split(":")
            execute(c, f"UPDATE {table} SET version=version+1,extraction_status='corrected' WHERE id=:i", {"i": int(number)})
        revised = api_evolution.schedule_context_gepa(c)
        assert revised and revised != identifier
    inject_search(monkeypatch)
    consumed = obj(work_job(revised)["result"])
    assert consumed["validation"]["source_consumption"] == "consumed"
    monkeypatch.setenv("BATTERY_LLM_API_KEY", "test-only-no-network-key")
    response = admin.post(f"/api/v2/evolution/runs/{run_id(identifier)}/retry", headers={"Idempotency-Key": "old-failure-new-source"})
    assert response.status_code == 409 and "已经完成" in response.text
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) is None


def test_completed_no_update_checks_feedback_cas_even_without_activation(admin, monkeypatch):
    identifier, base = admit_batch(admin, monkeypatch)
    original = extension_handler("context_gepa")["compute"]
    def revision(request, cancelled):
        result = original(request, cancelled)  # offline no_update, no activation_update
        with tx() as c:
            source = request["feedback_events"][0]["feedback"]
            table, number = source["feedback_id"].split(":")
            execute(c, f"UPDATE {table} SET version=version+1,extraction_status='corrected' WHERE id=:i", {"i": int(number)})
        return result
    monkeypatch.setitem(extension_handler("context_gepa"), "compute", revision)
    result = obj(work_job(identifier)["result"])
    assert result["state"] == "conflicted"
    assert result["validation"]["reason"] == "source_feedback_version_changed"
    assert result["metrics"]["provider_requests"] == 0
    with tx() as c:
        assert api_evolution.ensure_context(c)["id"] == base["id"]


def test_legacy_failed_root_reservation_is_retryable_after_backoff(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    with tx() as c:
        payload = obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": identifier})["payload"])
        # Pre-fix payloads had only root IDs and no pinned feedback versions.
        execute(c, "UPDATE jobs SET payload=:p,status='failed',error='test legacy failure',finished_at=:t WHERE id=:i", {
            "p": js({"root_ids": payload["root_ids"], "batch_size": 2, "max_rollouts": 200, "selection_count": 5}), "t": now(), "i": identifier})
        assert api_evolution.schedule_context_gepa(c) is None
    age_terminal(identifier)
    with tx() as c:
        retry = api_evolution.schedule_context_gepa(c)
        assert retry and retry != identifier
        assert obj(one(c, "SELECT payload FROM jobs WHERE id=:i", {"i": retry})["payload"])["retry_of_job_ids"] == [identifier]


@pytest.mark.parametrize("terminal, consumption", [("failed", "retryable"), ("cancelled", "cancelled"), ("interrupted", "interrupted")])
def test_gepa_terminal_lifecycle_preserves_sources_validation_and_accounting(admin, monkeypatch, terminal, consumption):
    identifier, _ = admit_batch(admin, monkeypatch)
    with tx() as c:
        job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": identifier})
        record = one(c, "SELECT * FROM evolution_runs WHERE job_id=:i", {"i": identifier})
        accounting = {"provider_requests": 3, "rollouts": 2, "provider_usage": {"total_tokens": 45}, "accounting_only": True}
        execute(c, "UPDATE evolution_runs SET metrics=:m WHERE id=:i", {"m": js(accounting), "i": record["id"]})
        extension_handler("context_gepa")["lifecycle"](c, job, terminal, "test-only terminal reason")
        revised = one(c, "SELECT * FROM evolution_runs WHERE id=:i", {"i": record["id"]})
        validation = obj(revised["validation"])
        assert validation["source_consumption"] == consumption
        assert validation["sources"] == obj(job["payload"])["sources"]
        assert validation["distinct_root_count"] == 2 and validation["automatic_attempt_limit"] == 3
        assert validation["reason"] == "test-only terminal reason" and validation["passed"] is False
        assert obj(revised["metrics"]) == accounting


def test_executor_caught_provider_failure_does_not_create_a_consumed_comparison_floor(admin, monkeypatch):
    identifier, _ = admit_batch(admin, monkeypatch)
    import app.agent.gepa_service as module
    from app.agent import run_agent
    from test_v2_gepa_workflow import CandidateClient
    factory, client = module.GEPAService, CandidateClient()
    class FailedReport:
        def generate_json(self, messages, schema=None):
            client.account()
            client.failed_request_count += 1
            raise LLMError("test-only temporary report outage")
    def invalid_cloud_runner(payload, *, llm, skill_library, context_store):
        # Exercise executor's real catch-and-fallback path rather than throwing
        # from the scorer. Its metrics still exist, but the cloud floor is invalid.
        result = run_agent(payload, llm=FailedReport(), skill_library=skill_library, context_store=context_store)
        assert result["run"]["cloud_report_valid"] is False
        return result
    def service(content_root, **kwargs):
        return factory(content_root, **{**kwargs, "selection_count": 2, "candidate_budget": 2}, llm=client,
                       runner=invalid_cloud_runner, selection_cases=cases())
    monkeypatch.setattr(module, "GEPAService", service)
    result = obj(work_job(identifier)["result"])
    assert result["state"] == "no_update" and result["validation"]["source_consumption"] == "retryable"
    baseline = result["metrics"]["candidate_evaluation"][0]
    assert baseline["metrics"] and any(f["reason"] == "cloud_report_not_strictly_valid" for f in baseline["metrics"]["hard_failures"])
    assert result["metrics"]["provider_requests"] == 5 and result["metrics"]["provider_failed_requests"] == 4
    assert result["metrics"]["provider_usage"]["total_tokens"] == 75
    age_terminal(identifier)
    with tx() as c:
        assert api_evolution.schedule_context_gepa(c) not in (None, identifier)


def test_safety_failure_stays_terminal_despite_provider_failure_count():
    baseline = {"candidate": {"candidate_id": "baseline"}, "metrics": {"hard_failures": [
        {"reason": "cloud_report_not_strictly_valid"}, {"reason": "safety_infeasible_test_recommended"}]}}
    job = {"status": "succeeded", "result": js({"state": "no_update", "metrics": {
        "provider_failed_requests": 1, "candidate_evaluation": [baseline]}})}
    assert api_evolution._gepa_disposition(job) == "consumed"
