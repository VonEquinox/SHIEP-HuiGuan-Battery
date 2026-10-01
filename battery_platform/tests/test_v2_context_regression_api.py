"""Real context check publication routes, with explicit offline scoring fixtures."""
from __future__ import annotations

import copy

import pytest

from app import api_evolution
from app.agent import run_agent
from app.db import execute, obj, one, tx
from app.jobs import extension_handler
from test_v2_gepa_service import Client, cases
from test_v2_workflow import work_job
from conftest import sign_in


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)


def revision(*, bad_permission=False):
    with tx() as c:
        base = api_evolution.ensure_context(c)
        snapshot = copy.deepcopy(obj(base["content"]))
        snapshot["skills"]["data-quality"] = {"instructions": "test-only degraded check selection"}
        if bad_permission:
            snapshot["skills"]["data-quality"]["allowed_tools"] = ["approve"]
        snapshot["context_snapshot_id"] = "test-only-new-context"
        actor = one(c, "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")["id"]
        identifier = api_evolution.publish_snapshot(c, base, snapshot, [{"operation": "SKILL_REVISE"}], {"passed": True}, actor)
        job = one(c, "SELECT * FROM jobs WHERE kind='context_regression' ORDER BY id DESC LIMIT 1")
    return base, identifier, job


def inject_scorer(monkeypatch, *, cancel_job=None, fail=False):
    import app.agent.regression as regression
    client = Client()
    factory = regression.ContextRegressionService
    def runner(payload, *, llm, skill_library, context_store):
        client.account()
        if cancel_job:
            with tx() as c:
                execute(c, "UPDATE jobs SET cancel_requested=1 WHERE id=:i", {"i": cancel_job})
        if fail:
            client.failed_request_count += 1
            raise RuntimeError("test-only failed dev report")
        result = run_agent(payload, llm=False, skill_library=skill_library, context_store=context_store)
        if context_store.snapshot()["skills"].get("data-quality", {}).get("instructions") == "test-only degraded check selection":
            result["report"]["suggested_tests"] = []
        result["run"].update(cloud_report_valid=True, execution_mode="test_only_regression_fixture")
        return result
    def service(root, **kwargs):
        return factory(root, **{**kwargs, "selection_count": 2, "rollout_budget": 4}, llm=client, runner=runner, selection_cases=cases())
    monkeypatch.setattr(regression, "ContextRegressionService", service)
    return client


def test_context_publication_automatically_checks_and_without_cloud_is_no_check(admin):
    base, identifier, job = revision()
    assert job["kind"] == "context_regression"
    result = work_job(job["id"])
    assert result["status"] == "succeeded", result["error"]
    assert obj(result["result"])["state"] == "no_check"
    with tx() as c:
        assert api_evolution.ensure_context(c)["id"] == identifier
        run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
        metrics = obj(run["metrics"])
        assert metrics["rollouts"] == metrics["provider_requests"] == 0
        assert not metrics.get("current_metrics") and not metrics.get("previous_metrics")
    detail = admin.get(f"/api/v2/context-snapshots/{identifier}")
    assert detail.status_code == 200 and detail.json()["validation"]["regression_check"]["state"] == "no_check"


def test_context_check_route_is_versioned_and_deduplicated(admin):
    with tx() as c:
        base = api_evolution.ensure_context(c)
    body = {"base_version": base["context_version"], "selection_count": 2, "max_rollouts": 4}
    headers = {"Idempotency-Key": "handmade-check"}
    first = admin.post("/api/v2/context-snapshots/check", json=body, headers=headers)
    again = admin.post("/api/v2/context-snapshots/check", json=body, headers=headers)
    assert first.status_code == again.status_code == 202 and first.json()["job_id"] == again.json()["job_id"]
    assert admin.post("/api/v2/context-snapshots/check", json={**body, "base_version": 99}, headers={"Idempotency-Key": "stale-check"}).status_code == 409
    job = work_job(first.json()["job_id"])
    assert obj(job["result"])["state"] == "no_check"
    sign_in(admin, "viewer")
    assert admin.post("/api/v2/context-snapshots/check", json=body, headers=headers).status_code == 403


@pytest.mark.parametrize("publication", ["rollback", "cancel", "cas"])
def test_independent_dev_regression_rollback_obeys_cancellation_and_cas(admin, monkeypatch, publication):
    base, identifier, job = revision()
    client = inject_scorer(monkeypatch)
    if publication == "cas":
        original = extension_handler("context_regression")["compute"]
        def concurrent_context(request, cancelled):
            result = original(request, cancelled)
            with tx() as c:
                current = api_evolution.ensure_context(c)
                new = copy.deepcopy(obj(current["content"]))
                new["skills"]["data-quality"]["instructions"] = "test-only newer independent feedback"
                new["context_snapshot_id"] = "test-only-concurrent-context"
                api_evolution.publish_snapshot(c, current, new, [{"operation": "REVISE"}], {"passed": True}, job["created_by"])
            return result
        monkeypatch.setitem(extension_handler("context_regression"), "compute", concurrent_context)
    completed = work_job(job["id"], cancel_after_compute=publication == "cancel")
    assert client.request_count == 4 and client.total_usage["total_tokens"] == 60
    with tx() as c:
        current = api_evolution.ensure_context(c)
        run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
        metrics = obj(run["metrics"])
        assert metrics["rollouts"] == 4 and metrics["provider_requests"] == 4
        if publication == "cancel":
            assert completed["status"] == run["status"] == "cancelled" and current["id"] == identifier
            assert metrics["accounting_only"] and run["result_snapshot_id"] is None
            assert obj(current["validation"])["regression_check"]["state"] == "cancelled"
        elif publication == "cas":
            assert completed["status"] == "succeeded" and obj(completed["result"])["state"] == "conflicted"
            assert obj(current["content"])["skills"]["data-quality"]["instructions"] == "test-only newer independent feedback"
        else:
            assert completed["status"] == "succeeded" and obj(completed["result"])["state"] == "rolled_back"
            assert current["id"] != identifier and obj(current["content"])["skills"]["data-quality"] == {}
            assert one(c, "SELECT state FROM context_snapshots WHERE id=:i", {"i": identifier})["state"] == "quarantined"
            # The restoration must not recursively enqueue another regression.
            assert one(c, "SELECT count(*) n FROM jobs WHERE kind='context_regression'")["n"] == 1
            assert one(c, "SELECT split FROM evaluation_runs WHERE evolution_run_id=:i", {"i": run["id"]})["split"] == "dev"


def test_hard_permission_regression_rolls_back_without_cloud(admin):
    base, identifier, job = revision(bad_permission=True)
    result = work_job(job["id"])
    assert result["status"] == "succeeded", result["error"]
    assert obj(result["result"])["state"] == "rolled_back"
    with tx() as c:
        current = api_evolution.ensure_context(c)
        assert current["id"] != identifier and obj(current["content"])["skills"]["data-quality"] == {}
        metrics = obj(one(c, "SELECT metrics FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})["metrics"])
        assert metrics["provider_requests"] == metrics["rollouts"] == 0 and metrics["permission_violations"] > 0


def test_mid_dev_cancel_preserves_cost_and_never_restores_snapshot(admin, monkeypatch):
    base, identifier, job = revision()
    client = inject_scorer(monkeypatch, cancel_job=job["id"])
    result = work_job(job["id"])
    assert result["status"] == "cancelled"
    with tx() as c:
        assert api_evolution.ensure_context(c)["id"] == identifier
        run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
        metrics = obj(run["metrics"])
        assert metrics["provider_requests"] == 1 and metrics["provider_usage"]["total_tokens"] == 15
        assert metrics["rollouts"] == 2 and metrics["accounting_only"] and run["result_snapshot_id"] is None
        assert obj(api_evolution.ensure_context(c)["validation"])["regression_check"]["state"] == "cancelled"


def test_terminal_old_check_does_not_overwrite_a_new_check_marker(admin):
    from app.v2_jobs import lifecycle
    _, identifier, job = revision()
    with tx() as c:
        current = api_evolution.ensure_context(c)
        second = api_evolution.schedule_context_regression(c, current, job["created_by"], key="test-only-new-check")
        lifecycle(c, job, "interrupted", "test-only worker interruption")
        marker = obj(api_evolution.ensure_context(c)["validation"])["regression_check"]
        assert marker["job_id"] == second and marker["state"] == "queued"
        latest = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": second})
        lifecycle(c, latest, "failed", "test-only provider failure")
        marker = obj(api_evolution.ensure_context(c)["validation"])["regression_check"]
        assert marker["job_id"] == second and marker["state"] == "failed"
        assert api_evolution.ensure_context(c)["id"] == identifier


def test_context_revision_preserves_real_retrieval_timestamp_in_mirror(admin):
    from app.agent import ContextStore
    from app.db import rows
    with tx() as c:
        base = api_evolution.ensure_context(c)
        store = ContextStore(initial_snapshot=obj(base["content"]))
        source = {"memory_id": "test-only-memory", "version": 1, "scope": {}, "trigger": "inspection", "insight": "Retain uncertainty.",
                  "supporting_case_ids": ["test-only-operational"], "source_scope": "operational", "source_trust": "reported", "state": "active",
                  "available_at": "2026-09-01T00:00:00Z", "last_used": None, "helpful_count": 0, "harmful_count": 0}
        initial = store.snapshot()
        initial["memories"] = [source]
        actor = one(c, "SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")["id"]
        api_evolution.publish_snapshot(c, base, initial, [{"operation": "ADD"}], {"passed": True}, actor)
        execute(c, "UPDATE memory_items SET last_used=:t WHERE memory_key=:k", {"t": "2026-09-02T00:00:00Z", "k": source["memory_id"]})
        current = api_evolution.ensure_context(c)
        revised = obj(current["content"])
        revised["memories"][0]["insight"] = "Retain uncertainty and a competing explanation."
        revised["context_snapshot_id"] = "test-only-memory-revision"
        api_evolution.publish_snapshot(c, current, revised, [{"operation": "REVISE"}], {"passed": True}, actor)
        mirrors = rows(c, "SELECT * FROM memory_items WHERE memory_key=:k ORDER BY version", {"k": source["memory_id"]})
        assert len(mirrors) == 2 and mirrors[-1]["last_used"] == "2026-09-02T00:00:00Z"
        assert mirrors[-1]["helpful_count"] == mirrors[-1]["harmful_count"] == 0
        assert obj(api_evolution.ensure_context(c)["content"])["memories"][0]["last_used"] is None


def test_failed_dev_evidence_does_not_invent_regression_or_erase_cost(admin, monkeypatch):
    base, identifier, job = revision()
    client = inject_scorer(monkeypatch, fail=True)
    result = work_job(job["id"])
    assert result["status"] == "succeeded", result["error"]
    assert obj(result["result"])["state"] == "no_check"
    with tx() as c:
        assert api_evolution.ensure_context(c)["id"] == identifier
        metrics = obj(one(c, "SELECT metrics FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})["metrics"])
        assert metrics["provider_requests"] == metrics["provider_failed_requests"] == 1
        assert metrics["provider_usage"]["total_tokens"] == 15 and metrics["rollouts"] == 2
