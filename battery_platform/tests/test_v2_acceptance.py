"""Cross-module acceptance. All assets/readings here are synthetic fixtures.

Cloud calls are deliberately excluded: a real deterministic rule baseline
produces fixture reports. No protected model-lab holdout is read or scored.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import tx, rows, one, execute, insert, js, obj, now
from app.jobs import JobSupervisor, extension_handler
from app.agent import run_agent, SkillLibrary, ReplayEvaluator, ContextStore
from app.config import REPO_ROOT
from app import api_agent, api_evolution, api_v2
from app.dispatch import jobs as dispatch_jobs
from app.carbon import jobs as carbon_jobs
from conftest import sign_in, PASSWORD
from test_platform import seed, dataset_fixture, fixture_prediction
from test_v2_carbon import factor, scenario
from test_v2_dispatch import prepared_plan


def execute_job(identifier, handler, *, cancel_after_compute=False):
    """Exercise the actual worker publication barrier around real computation."""
    with tx() as c:
        execute(c, "UPDATE jobs SET status='running',started_at=:t WHERE id=:i", {"t": now(), "i": identifier})
        job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": identifier})
    bound = dict(extension_handler(job["kind"]) or {})
    bound.update(handler)
    if cancel_after_compute:
        compute = bound["compute"]
        def compute_then_cancel(request, cancelled):
            result = compute(request, cancelled)
            with tx() as c:
                execute(c, "UPDATE jobs SET cancel_requested=1 WHERE id=:i", {"i": identifier})
            return result
        bound["compute"] = compute_then_cancel
    JobSupervisor().run_extension(job, bound)
    with tx() as c:
        return one(c, "SELECT * FROM jobs WHERE id=:i", {"i": identifier})


def rule_handler():
    def compute(request, cancelled):
        assert not cancelled()
        return run_agent({k: v for k, v in request.items() if not k.startswith("_")}, llm=False)
    return {"snapshot": api_agent.agent_snapshot, "compute": compute, "complete": api_agent.agent_complete}


def baseline_report(admin, asset=None):
    asset = asset or seed(admin)
    injected = admin.post("/api/demo/events", json={"asset_id": asset["id"], "scenario": "capacity-review"})
    assert injected.status_code == 200, injected.text
    r = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()}, headers={"Idempotency-Key": "acceptance-rule-run"})
    assert r.status_code == 202, r.text
    run = r.json()
    job = execute_job(run["job_id"], rule_handler())
    assert job["status"] == "succeeded", job["error"]
    with tx() as c:
        report = one(c, "SELECT * FROM agent_reports WHERE agent_run_id=:i", {"i": run["run_id"]})
    return asset, run, report


def approved_order(admin):
    asset, run, report = baseline_report(admin)
    r = admin.post("/api/v2/work-proposals", json={"report_id": report["id"], "title": "跨模块验收：采样时间核对", "allowed_tests": ["T_TIME_ALIGN"], "required_tests": ["T_TIME_ALIGN"], "required_qualifications": ["battery", "instrumentation"], "max_rounds": 2, "duration_minutes": 30}, headers={"Idempotency-Key": "acceptance-propose"})
    assert r.status_code == 201, r.text
    proposal = r.json()
    with tx() as c:
        assert one(c, "SELECT count(*) n FROM orders")["n"] == 0
    approval = {"version": proposal["version"], "note": "人工确认有界测试集合"}
    r = admin.post(f'/api/v2/work-proposals/{proposal["id"]}/approve', json=approval, headers={"Idempotency-Key": "acceptance-approve"})
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    again = admin.post(f'/api/v2/work-proposals/{proposal["id"]}/approve', json=approval, headers={"Idempotency-Key": "acceptance-approve-second-key"})
    assert again.status_code == 200 and again.json()["order_id"] == order["id"]
    users = admin.get("/api/users").json()
    tech = next(u for u in users if u["username"] == "tech")
    r = admin.post("/api/personnel", json={"user_id": tech["id"], "skills": ["battery", "instrumentation"], "on_call": True, "max_workload": 4})
    assert r.status_code == 200, r.text
    resources = admin.get("/api/v2/dispatch/resources").json()
    r = admin.put("/api/v2/dispatch/resources", json={"version": resources["version"], "payload": {"engineers": [{"id": tech["id"], "shifts": [[0, 120]], "max_minutes": 120, "home_location": asset["location"]}], "provenance": "simulated", "scenario_id": "CROSS_MODULE_ACCEPTANCE"}})
    assert r.status_code == 200, r.text
    r = admin.post("/api/v2/dispatch/plans", json={"order_ids": [order["id"]], "horizon_start": now(), "horizon_minutes": 120}, headers={"Idempotency-Key": "acceptance-plan"})
    assert r.status_code == 202, r.text
    planned = r.json()
    handler = {name: getattr(dispatch_jobs, name) for name in ("snapshot", "compute", "complete")}
    job = execute_job(planned["job_id"], handler)
    assert job["status"] == "succeeded", job["error"]
    plan = admin.get(f'/api/v2/dispatch/plans/{planned["plan_id"]}').json()
    assert plan["result"]["assignments"]
    r = admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', json={"version": plan["version"]}, headers={"Idempotency-Key": "acceptance-confirm"})
    assert r.status_code == 200, r.text
    return asset, run, report, admin.get(f'/api/orders/{order["id"]}').json(), tech


def observation_body(asset, order, *, text="已核对采样时间；仍须独立证据排除真实电芯异常。"):
    return {"asset_id": asset["id"], "installation_id": asset["installation_id"], "round": 1, "order_version": order["version"], "test_id": "T_TIME_ALIGN", "measured_at": now(), "instrument_id": "TEST_CLOCK", "calibration_status": "not_applicable", "free_text": text, "provenance": "synthetic", "client_submission_id": "acceptance-observation-uuid"}


def test_proposal_dispatch_inspection_feedback_chain_preserves_human_boundaries(admin):
    asset, run, _, order, tech = approved_order(admin)
    with TestClient(app) as technician:
        sign_in(technician, "tech")
        r = technician.post(f'/api/orders/{order["id"]}/transition', json={"version": order["version"], "action": "accept", "note": "本人接单"})
        assert r.status_code == 200, r.text
        order = r.json()
        body = observation_body(asset, order)
        r = technician.post(f'/api/v2/orders/{order["id"]}/observations', json=body)
        assert r.status_code == 201, r.text
        submitted = r.json()
        repeat = technician.post(f'/api/v2/orders/{order["id"]}/observations', json=body)
        assert repeat.status_code == 201 and repeat.json()["observation_id"] == submitted["observation_id"]
        extraction = {"snapshot": api_evolution.feedback_snapshot, "compute": api_evolution.feedback_compute, "complete": api_evolution.feedback_complete}
        job = execute_job(submitted["extraction_job_id"], extraction)
        assert job["status"] == "succeeded", job["error"]
        result = obj(job["result"])
        assert result["approval_required"] is False
        reassessment = execute_job(submitted["reassessment_job_id"], rule_handler())
        assert reassessment["status"] == "succeeded", reassessment["error"]
        with tx() as c:
            obs = one(c, "SELECT * FROM inspection_observations WHERE id=:i", {"i": submitted["observation_id"]})
            assert obs["author_id"] == tech["id"] and obs["free_text"] == body["free_text"]
            facts = obj(obs["candidate_facts"])
            assert facts and all(f["trust"] == "reported" for f in facts)
            for fact in facts:
                if fact.get("span"):
                    span = fact["span"]
                    assert fact["source_text"] == body["free_text"][span["start"]:span["end"]]
            assert one(c, "SELECT count(*) n FROM carbon_ledger")["n"] == 0
            assert one(c, "SELECT count(*) n FROM orders")["n"] == 1
        inspection = technician.get(f'/api/v2/orders/{order["id"]}/inspection').json()
        assert len(inspection["reports"]) == 2
        assert inspection["independent_acceptance_required"]


def test_mobile_token_identity_qr_and_request_body_cannot_escalate(admin, monkeypatch):
    asset, _, _, order, tech = approved_order(admin)
    monkeypatch.setenv("BATTERY_DEMO_MOBILE", "1")
    with TestClient(app) as mobile:
        r = mobile.post("/api/v2/demo-mobile/login", json={"username": "tech", "password": PASSWORD})
        assert r.status_code == 200, r.text
        mobile.headers["Authorization"] = "Bearer " + r.json()["token"]
        assert mobile.get("/api/auth/me").json()["id"] == tech["id"]
        assert mobile.get("/api/v2/carbon/ledger").status_code == 403
        assert mobile.get("/api/v2/dispatch/plans").status_code == 403
        qr = admin.get(f'/api/v2/orders/{order["id"]}/qr').json()
        valid = mobile.post(f'/api/v2/orders/{order["id"]}/qr/verify', json={"token": qr["token"]})
        assert valid.status_code == 200, valid.text
        with tx() as c:
            execute(c, "UPDATE assets SET installation_id='acceptance-replacement',version=version+1 WHERE id=:i", {"i": asset["id"]})
        assert mobile.post(f'/api/v2/orders/{order["id"]}/qr/verify', json={"token": qr["token"]}).status_code in (403, 409)
        forged = observation_body(asset, order)
        forged["author_id"] = 1
        assert mobile.post(f'/api/v2/orders/{order["id"]}/observations', json=forged).status_code == 422
        assert mobile.post("/api/v2/demo-mobile/logout").status_code == 200
        assert mobile.get("/api/orders").status_code == 401


def test_future_prediction_write_cannot_change_past_agent_snapshot(admin):
    asset = seed(admin)
    ds = dataset_fixture()
    old, model = fixture_prediction(asset, ds, ordinal=0, soh=.83)
    future, _ = fixture_prediction(asset, ds, ordinal=1, soh=.71, model_id=model)
    cutoff = "2026-09-01T12:00:00+00:00"
    with tx() as c:
        execute(c, "UPDATE predictions SET created_at=:t WHERE id=:i", {"t": "2026-09-01T11:00:00+00:00", "i": old})
        execute(c, "UPDATE predictions SET created_at=:t WHERE id=:i", {"t": "2026-09-01T13:00:00+00:00", "i": future})
    r = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": cutoff}, headers={"Idempotency-Key": "timeline-rule-run"})
    assert r.status_code == 202, r.text
    with tx() as c:
        job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": r.json()["job_id"]})
        snap = api_agent.agent_snapshot(c, job)
    assert snap["prediction"]["support"]["status"] == "supported"
    assert snap["prediction"]["prediction_id"] == old
    assert snap["prediction"]["heads"]["soh"]["value"] == .83
    assert ".71" not in js(snap["prediction"])


def test_post_cutoff_observation_availability_is_excluded_even_when_backdated(admin):
    asset, _, _, order, _ = approved_order(admin)
    with TestClient(app) as technician:
        sign_in(technician, "tech")
        accepted = technician.post(f'/api/orders/{order["id"]}/transition', json={"version": order["version"], "action": "accept", "note": "本人接单"}).json()
        r = technician.post(f'/api/v2/orders/{order["id"]}/observations', json=observation_body(asset, accepted))
        assert r.status_code == 201, r.text
        with tx() as c:
            cutoff = one(c, "SELECT visible_cutoff FROM agent_runs WHERE id=:i", {"i": r.json()["run_id"]})["visible_cutoff"]
            future = (datetime.fromisoformat(cutoff) + timedelta(hours=1)).isoformat()
            execute(c, "UPDATE inspection_observations SET available_at=:t WHERE id=:i", {"t": future, "i": r.json()["observation_id"]})
            job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": r.json()["reassessment_job_id"]})
            snap = api_agent.agent_snapshot(c, job)
    assert not any(str(o.get("evidence_id")) == f'obs-{r.json()["observation_id"]}' for o in snap["observations"])


def test_cancelled_agent_publication_does_not_create_report_or_proposal(admin):
    asset = seed(admin)
    r = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()}, headers={"Idempotency-Key": "cancel-rule-run"})
    assert r.status_code == 202, r.text
    job = execute_job(r.json()["job_id"], rule_handler(), cancel_after_compute=True)
    assert job["status"] == "cancelled"
    with tx() as c:
        assert one(c, "SELECT count(*) n FROM agent_reports")["n"] == 0
        assert one(c, "SELECT count(*) n FROM work_proposals")["n"] == 0
        assert one(c, "SELECT status FROM agent_runs WHERE job_id=:i", {"i": job["id"]})["status"] == "cancelled"


def test_cancelled_feedback_has_no_ghost_context_activation(admin):
    asset, _, report = baseline_report(admin)
    r = admin.post(f'/api/v2/diagnostic-sessions/{report["session_id"]}/feedback', json={"report_id": report["id"], "free_text": "合成回放观察：时间对齐尚未核实，先保留未知。", "provenance": "synthetic", "client_submission_id": "cancel-feedback-fixture"})
    assert r.status_code == 201, r.text
    with tx() as c:
        before = one(c, "SELECT id,context_version FROM context_snapshots WHERE state='active'")
    handler = {"snapshot": api_evolution.feedback_snapshot, "compute": api_evolution.feedback_compute, "complete": api_evolution.feedback_complete}
    job = execute_job(r.json()["job_id"], handler, cancel_after_compute=True)
    assert job["status"] == "cancelled"
    with tx() as c:
        assert one(c, "SELECT id,context_version FROM context_snapshots WHERE state='active'") == before
        assert one(c, "SELECT count(*) n FROM evolution_runs")["n"] == 0


def stored_carbon(admin, *, synthetic=False):
    extra = {"synthetic_scenario_id": "CROSS_MODULE_ACCEPTANCE"} if synthetic else {}
    payload = factor(provenance="synthetic" if synthetic else "real", **extra).model_dump(mode="json")
    r = admin.post("/api/v2/carbon/factors", json=payload)
    assert r.status_code == 201, r.text
    s = scenario(provenance="synthetic" if synthetic else "real", **extra)
    for candidate in s.candidates:
        for activity in candidate.activities:
            activity.factor_id = r.json()["id"]
            if synthetic:
                activity.provenance = "synthetic"
    r = admin.post("/api/v2/carbon/scenarios", json=s.model_dump(mode="json"))
    assert r.status_code == 201, r.text
    identifier = r.json()["id"]
    r = admin.post(f"/api/v2/carbon/scenarios/{identifier}/solve", json={"expected_version": 1}, headers={"Idempotency-Key": "acceptance-independent-carbon"})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def test_carbon_runs_when_agent_cloud_unavailable_and_demo_export_stays_excluded(admin, monkeypatch):
    def broken_agent(*args):
        raise RuntimeError("Test-only simulated cloud service unavailable")
    monkeypatch.setattr(api_agent, "agent_compute", broken_agent)
    asset = seed(admin)
    failed = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()}, headers={"Idempotency-Key": "acceptance-agent-cloud-failure"})
    assert failed.status_code == 202, failed.text
    failed_job = execute_job(failed.json()["job_id"], {"snapshot": api_agent.agent_snapshot, "compute": broken_agent, "complete": api_agent.agent_complete})
    assert failed_job["status"] == "failed"
    identifier = stored_carbon(admin, synthetic=True)
    handler = {name: getattr(carbon_jobs, name) for name in ("snapshot", "compute", "complete")}
    job = execute_job(identifier, handler)
    assert job["status"] == "succeeded", job["error"]
    result_id = obj(job["result"])["result_id"]
    result = admin.get(f"/api/v2/carbon/results/{result_id}").json()["result"]
    assert result["candidates"][1]["carbon"]["nominal"] == 40
    r = admin.post("/api/v2/carbon/ledger", json={"result_id": result_id, "candidate_id": "candidate", "claim_type": "comparative_avoided", "basis": "settled", "review_status": "reviewed", "evidence_reference": "TEST synthetic metered fixture", "accounting_period": "2026"})
    assert r.status_code == 201, r.text
    assert admin.get("/api/v2/carbon/exports?formal=true").json()["records"] == []
    demo = admin.get("/api/v2/carbon/exports?formal=false").json()
    assert demo["records"] and demo["records"][0]["provenance"] == "synthetic"
    with tx() as c:
        assert one(c, "SELECT count(*) n FROM orders")["n"] == 0


def test_cancelled_carbon_worker_has_no_partial_inventory_or_ledger(admin):
    identifier = stored_carbon(admin)
    handler = {name: getattr(carbon_jobs, name) for name in ("snapshot", "compute", "complete")}
    job = execute_job(identifier, handler, cancel_after_compute=True)
    assert job["status"] == "cancelled"
    with tx() as c:
        for table in ("carbon_results", "carbon_activities", "carbon_ledger"):
            assert one(c, f"SELECT count(*) n FROM {table}")["n"] == 0


def test_sealed_label_markers_never_enter_agent_skill_or_reflection_inputs(admin, monkeypatch):
    root = REPO_ROOT / "content_v1"
    sealed_case = json.loads((root / "evaluation/sealed/cases.jsonl").read_text().splitlines()[0])
    cases = api_evolution._evaluation_cases([sealed_case["case_id"]], "sealed_test")
    # Do not score a sealed root. This test substitutes a label-independent
    # structural metric only to exercise the evaluator's isolation control flow.
    import app.agent.evaluation as evaluator_module
    monkeypatch.setattr(evaluator_module, "score_report", lambda report, case, trace: {
        "diagnosis_correct": 0, "fact_count": 0, "grounded_fact_count": 0,
        "test_count": 0, "unsafe_test_count": 0, "missed": None, "false_alarm": None,
        "label_provenance": "unscored_boundary_test"})
    seen = []
    def inspect_visible(visible, **kwargs):
        seen.append(copy.deepcopy(visible))
        text = js(visible)
        assert all(word not in text for word in ("hidden_truth", "expected_behavior", "expected_feedback", '"branches"'))
        return run_agent(visible, llm=False, skill_library=kwargs.get("skill_library"), context_store=kwargs.get("context_store"))
    with tx() as c:
        base = api_v2.ensure_context(c)
    result = ReplayEvaluator().evaluate("A1", cases, initial_snapshot=obj(base["content"]), skill_library=SkillLibrary(root), runner=inspect_visible, milestone=True, frozen_config={"review": "one-root-sealed-boundary-only"})
    assert len(seen) == 1 and not result["selection_eligible"]
    assert result["final_context_snapshot"] == obj(base["content"])
    assert result["generalization_verified"] is False
    # Sealed scorer results stay local to this test; they are not published as
    # benchmark quality evidence, initialized memory, or optimization candidates.
    blocked = admin.post("/api/v2/evolution/experiments", json={"method": "ace", "base_version": base["context_version"], "case_ids": [sealed_case["case_id"]], "split": "sealed_test", "max_rollouts": 1, "activate": False}, headers={"Idempotency-Key": "sealed-no-reflection"})
    assert blocked.status_code == 403
    public_memories = js(obj(base["content"])["memories"])
    assert sealed_case["root_scenario_id"] not in public_memories
    with pytest.raises((ValueError, KeyError)):
        api_evolution._evaluation_cases([sealed_case["case_id"]], "evolution")


def test_sealed_root_is_not_reachable_through_runtime_retrieval_tool():
    library = SkillLibrary(REPO_ROOT / "content_v1")
    assert len(library.skill_metadata()) == 16
    skill = library.skill_metadata()[0]["skill_id"]
    with pytest.raises(ValueError):
        library.load_reference(skill, "../../../evaluation/sealed/cases.jsonl")
    assert all("carbon" not in str(item.get("source_id", "")) for item in library.search_knowledge("carbon fixtures", limit=5))


def test_registered_v2_source_coordinates_reach_agent_without_becoming_wall_clock(admin):
    asset = seed(admin)
    with tx() as c:
        actor = one(c, "SELECT id FROM users WHERE username='admin'")["id"]
        identifier = insert(c, "jobs", {"kind": "v2_inference", "status": "succeeded", "payload": "{}", "created_by": actor, "created_at": now(), "idempotency_key": "source-time-fixture", "request_hash": "explicit-test-fixture"})
        profile = {"model_version": "TEST_ONLY_MODEL_NO_REAL_SCORE", "query": {"source_id": "test-source", "physical_cell_id": "test-cell", "query_time": 24.0, "visible_cutoff": 23.0, "feature_max_time": 23.0},
                   "support": {"status": "supported", "reasons": []}, "heads": {"soh": {"support": "supported", "unit": "ratio", "distribution_kind": "quantiles", "quantiles": {"0.05": .8, "0.5": .85, "0.95": .9}}}}
        insert(c, "v2_prediction_profiles", {"job_id": identifier, "asset_id": asset["id"], "installation_id": asset["installation_id"], "physical_cell_id": "test-cell", "source_id": "test-source", "model_version": "TEST_ONLY_MODEL_NO_REAL_SCORE", "support": "supported", "profile": js(profile), "provenance": "synthetic", "available_at": now(), "source_cutoff": 23.0})
    r = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()}, headers={"Idempotency-Key": "source-time-rule-run"})
    assert r.status_code == 202, r.text
    job = execute_job(r.json()["job_id"], rule_handler())
    assert job["status"] == "succeeded", job["error"]
    with tx() as c:
        snap = api_agent.agent_snapshot(c, one(c, "SELECT * FROM jobs WHERE id=:i", {"i": job["id"]}))
    source_time = snap["prediction"]["query"]["source_time"]
    assert source_time["time_basis"] == "source_record_ordinal"
    assert source_time["visible_cutoff_ordinal"] == 23.0
    assert source_time["query_ordinal"] == 24.0
    assert snap["visible_cutoff"] != 23.0


def test_cancelled_dispatch_worker_never_publishes_draft_or_assigns_orders(admin):
    order, _, plan, _ = prepared_plan(admin)
    with tx() as c:
        execute(c, "UPDATE dispatch_plans SET status='QUEUED',result=NULL WHERE id=:i", {"i": plan["id"]})
    handler = {name: getattr(dispatch_jobs, name) for name in ("snapshot", "compute", "complete")}
    job = execute_job(plan["job_id"], handler, cancel_after_compute=True)
    assert job["status"] == "cancelled"
    with tx() as c:
        assert one(c, "SELECT result FROM dispatch_plans WHERE id=:i", {"i": plan["id"]})["result"] is None
        assert one(c, "SELECT count(*) n FROM dispatch_assignments")["n"] == 0
        assert one(c, "SELECT status FROM orders WHERE id=:i", {"i": order["id"]})["status"] == "CREATED"
    assert admin.get(f'/api/v2/dispatch/plans/{plan["id"]}').json()["status"] == "CANCELLED"


def test_approval_cannot_reduce_catalogue_qualification_requirements(admin):
    _, _, report = baseline_report(admin)
    r = admin.post("/api/v2/work-proposals", json={"report_id": report["id"], "title": "验收：不允许削弱测试资格", "allowed_tests": ["T_TIME_ALIGN"], "required_tests": ["T_TIME_ALIGN"], "required_qualifications": ["battery"]}, headers={"Idempotency-Key": "qualification-admission"})
    if r.status_code == 422:
        return
    assert r.status_code == 201, r.text
    proposal = r.json()
    r = admin.post(f'/api/v2/work-proposals/{proposal["id"]}/approve', json={"version": proposal["version"], "required_qualifications": ["battery"]}, headers={"Idempotency-Key": "qualification-approve"})
    if r.status_code == 422:
        return
    assert r.status_code == 200, r.text
    with tx() as c:
        requirement = one(c, "SELECT required_qualifications FROM dispatch_requirements WHERE order_id=:i", {"i": r.json()["order_id"]})
    assert {"battery", "instrumentation"} <= set(obj(requirement["required_qualifications"]))


def test_worker_registry_and_restart_recovery_keep_running_jobs_terminal(admin):
    expected = ("agent_run", "incident_analysis", "feedback_extract", "feedback_verified_batch", "evolution_experiment", "source_ingest", "v2_training", "v2_calibration", "v2_evaluation", "v2_export", "v2_inference", "dispatch", "carbon_solve")
    for kind in expected:
        handler = extension_handler(kind)
        assert handler and all(callable(handler.get(step)) for step in ("snapshot", "compute", "complete")), kind
    asset = seed(admin)
    r = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()}, headers={"Idempotency-Key": "restart-rule-run"})
    assert r.status_code == 202
    with tx() as c:
        execute(c, "UPDATE jobs SET status='running' WHERE id=:i", {"i": r.json()["job_id"]})
        execute(c, "UPDATE agent_runs SET status='running' WHERE id=:i", {"i": r.json()["run_id"]})
    supervisor = JobSupervisor()
    supervisor.stop_event.set()  # Run recovery, without starting cloud/queued work.
    supervisor.start()
    supervisor.stop()
    with tx() as c:
        assert one(c, "SELECT status FROM jobs WHERE id=:i", {"i": r.json()["job_id"]})["status"] == "interrupted"
        assert one(c, "SELECT status FROM agent_runs WHERE id=:i", {"i": r.json()["run_id"]})["status"] == "interrupted"
        assert one(c, "SELECT count(*) n FROM agent_reports")["n"] == 0


def test_later_fact_correction_is_not_visible_to_earlier_reassessment_cutoff(admin):
    asset, _, _, order, _ = approved_order(admin)
    with TestClient(app) as technician:
        sign_in(technician, "tech")
        order = technician.post(f'/api/orders/{order["id"]}/transition', json={"version": order["version"], "action": "accept", "note": "本人接单"}).json()
        body = observation_body(asset, order)
        submitted = technician.post(f'/api/v2/orders/{order["id"]}/observations', json=body)
        assert submitted.status_code == 201, submitted.text
        observed = submitted.json()
        corrected = technician.post(f'/api/v2/observations/{observed["observation_id"]}/facts', json={
            "version": 1, "note": "截止时间之后才完成的人工抽取修正", "candidate_facts": [{
                "fact_id": "AFTER_CUTOFF_CORRECTION", "claim": "LATER_DERIVED_INTERPRETATION",
                "trust": "reported", "span": {"start": 0, "end": len(body["free_text"])},
                "source_text": body["free_text"]}]})
        assert corrected.status_code == 200, corrected.text
        with tx() as c:
            job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": observed["reassessment_job_id"]})
            cutoff = one(c, "SELECT visible_cutoff FROM agent_runs WHERE job_id=:i", {"i": job["id"]})["visible_cutoff"]
            version = one(c, "SELECT created_at FROM inspection_observation_versions WHERE observation_id=:i AND version=2", {"i": observed["observation_id"]})
            assert datetime.fromisoformat(version["created_at"]) > datetime.fromisoformat(cutoff)
            snapshot = api_agent.agent_snapshot(c, job)
        assert "AFTER_CUTOFF_CORRECTION" not in js(snapshot["observations"])


def test_later_memory_revision_keeps_its_own_availability_cutoff(admin):
    asset, _, report = baseline_report(admin)
    handler = {"snapshot": api_evolution.feedback_snapshot, "compute": api_evolution.feedback_compute, "complete": api_evolution.feedback_complete}
    def submit(text, key):
        submitted = admin.post(f'/api/v2/diagnostic-sessions/{report["session_id"]}/feedback', json={
            "report_id": report["id"], "free_text": text, "provenance": "synthetic", "client_submission_id": key})
        assert submitted.status_code == 201, submitted.text
        job = execute_job(submitted.json()["job_id"], handler)
        assert job["status"] == "succeeded", job["error"]
        return submitted.json()
    submit("合成初始反馈：本次现场尚未取得独立确认。", "memory-first-source")
    cutoff = now()
    late = submit("LATER_MEMORY_PHENOMENON：这是截止时间之后才反馈的新增现象。", "memory-later-source")
    with tx() as c:
        source = one(c, "SELECT available_at FROM diagnostic_feedback WHERE id=:i", {"i": late["feedback_id"]})
        assert datetime.fromisoformat(source["available_at"]) > datetime.fromisoformat(cutoff)
    requested = admin.post("/api/v2/agent/runs", json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "session_id": report["session_id"], "visible_cutoff": cutoff}, headers={"Idempotency-Key": "memory-historical-replay"})
    assert requested.status_code == 202, requested.text
    with tx() as c:
        snapshot = api_agent.agent_snapshot(c, one(c, "SELECT * FROM jobs WHERE id=:i", {"i": requested.json()["job_id"]}))
    memories = ContextStore(initial_snapshot=snapshot["context_snapshot"]).history(scope={"installation_id": asset["installation_id"]}, cutoff=cutoff)
    assert "LATER_MEMORY_PHENOMENON" not in js(memories)


def test_persisted_incident_context_and_split_preserve_individual_alerts(admin):
    primary = seed(admin)
    assets = admin.get("/api/assets").json()
    peer = next(item for item in assets if item["kind"] == "cell" and item["parent_id"] == primary["parent_id"] and item["id"] != primary["id"])
    alerts = []
    for asset in (primary, peer):
        created = admin.post("/api/demo/events", json={"asset_id": asset["id"], "scenario": "capacity-review"})
        assert created.status_code == 200, created.text
        alerts.append(created.json()["alert_id"])
    analyzed = admin.post("/api/v2/incidents/analyze", json={"asset_ids": [primary["id"], peer["id"]], "visible_cutoff": now(), "window_minutes": 60}, headers={"Idempotency-Key": "acceptance-topology-group"})
    assert analyzed.status_code == 202, analyzed.text
    job = execute_job(analyzed.json()["job_id"], {"snapshot": api_agent.incident_snapshot, "compute": api_agent.incident_compute, "complete": api_agent.incident_complete})
    assert job["status"] == "succeeded", job["error"]
    group_id = obj(job["result"])["group_ids"][0]
    group = admin.get(f"/api/v2/incidents/{group_id}").json()
    assert group["relation_type"] == "topology_association" and group["evidence"]["confirmed_common_cause"] is False
    requested = admin.post("/api/v2/agent/runs", json={"asset_id": primary["id"], "installation_id": primary["installation_id"], "incident_group_id": group_id, "visible_cutoff": now()}, headers={"Idempotency-Key": "acceptance-group-diagnosis"})
    assert requested.status_code == 202, requested.text
    with tx() as c:
        snapshot = api_agent.agent_snapshot(c, one(c, "SELECT * FROM jobs WHERE id=:i", {"i": requested.json()["job_id"]}))
    group_context = snapshot.get("group_context", {})
    job = execute_job(requested.json()["job_id"], rule_handler())
    assert job["status"] == "succeeded", job["error"]
    with tx() as c:
        report = one(c, "SELECT id FROM agent_reports WHERE agent_run_id=:i", {"i": requested.json()["run_id"]})
        before = rows(c, "SELECT id,status,version FROM alerts ORDER BY id")
    proposal = admin.post("/api/v2/work-proposals", json={"report_id": report["id"], "incident_group_id": group_id, "asset_ids": [primary["id"], peer["id"]], "allowed_tests": ["T_CAPACITY_REVIEW"], "title": "合成拓扑关联组检查提案"}, headers={"Idempotency-Key": "acceptance-group-proposal"})
    assert proposal.status_code == 201, proposal.text
    rerun = admin.post("/api/v2/agent/runs", json={"asset_id": primary["id"], "installation_id": primary["installation_id"], "session_id": requested.json()["session_id"], "visible_cutoff": now()}, headers={"Idempotency-Key": "acceptance-stale-group-run"})
    assert rerun.status_code == 202, rerun.text
    split_results = []
    handler = rule_handler()
    original_compute = handler["compute"]
    def compute_and_split(request, cancelled):
        result = original_compute(request, cancelled)
        split = admin.post(f"/api/v2/incidents/{group_id}/split", json={"version": group["version"], "member_asset_ids": [primary["id"]], "note": "检查后拆分，保留每个单体的未解决告警"})
        assert split.status_code == 200, split.text
        split_results.append(split.json())
        return result
    handler["compute"] = compute_and_split
    rejected_job = execute_job(rerun.json()["job_id"], handler)
    assert rejected_job["status"] == "failed"
    split = split_results[0]
    with tx() as c:
        assert rows(c, "SELECT id,status,version FROM alerts ORDER BY id") == before
        assert one(c, "SELECT count(*) n FROM agent_reports WHERE agent_run_id=:i", {"i": rerun.json()["run_id"]})["n"] == 0
        assert {row["alert_id"] for row in rows(c, "SELECT alert_id FROM incident_members WHERE group_id IN (:a,:b)", {"a": split["child_ids"][0], "b": split["child_ids"][1]})} == set(alerts)
    stale = admin.post(f'/api/v2/work-proposals/{proposal.json()["id"]}/approve', json={"version": proposal.json()["version"]}, headers={"Idempotency-Key": "acceptance-stale-group-approve"})
    assert stale.status_code == 409
    assert str(group_id) in js(group_context) and peer["installation_id"] in js(group_context)
    assert "confirmed_common_cause" in js(group_context)


def test_submitted_round_does_not_recommend_an_already_completed_check(admin):
    asset, _, _, order, _ = approved_order(admin)
    with TestClient(app) as technician:
        sign_in(technician, "tech")
        order = technician.post(f'/api/orders/{order["id"]}/transition', json={"version": order["version"], "action": "accept", "note": "本人接单"}).json()
        observed = technician.post(f'/api/v2/orders/{order["id"]}/observations', json=observation_body(asset, order))
        assert observed.status_code == 201, observed.text
        extraction = execute_job(observed.json()["extraction_job_id"], {"snapshot": api_evolution.feedback_snapshot, "compute": api_evolution.feedback_compute, "complete": api_evolution.feedback_complete})
        assert extraction["status"] == "succeeded", extraction["error"]
        submitted = technician.post(f'/api/v2/orders/{order["id"]}/rounds/1/submit', json={"order_version": order["version"], "installation_id": asset["installation_id"], "client_submission_id": "completed-round-one"})
        assert submitted.status_code == 200, submitted.text
        repeated = technician.post(f'/api/v2/orders/{order["id"]}/rounds/1/submit', json={"order_version": order["version"], "installation_id": asset["installation_id"], "client_submission_id": "completed-round-one"})
        assert repeated.status_code == 200 and repeated.json()["job_id"] == submitted.json()["job_id"]
        job = execute_job(submitted.json()["job_id"], rule_handler())
        assert job["status"] == "succeeded", job["error"]
        with tx() as c:
            report = obj(one(c, "SELECT report FROM agent_reports WHERE agent_run_id=:i", {"i": submitted.json()["run_id"]})["report"])
        assert all(item["test_id"] != "T_TIME_ALIGN" for item in report["suggested_tests"])
        # Submitting evidence does not perform final verification or extend tests.
        view = technician.get(f'/api/v2/orders/{order["id"]}/inspection').json()
        assert view["order"]["status"] == "ACCEPTED"
        assert view["order"]["verified_by"] is None
        assert set(view["proposal"]["allowed_tests"]) == {"T_TIME_ALIGN"}


def test_evolution_publication_retains_earlier_ace_and_gepa_changes(admin):
    """A publication boundary fixture; it does not certify candidate quality."""
    asset = seed(admin)
    with tx() as c:
        base = api_evolution.ensure_context(c)
    case_ids = ["acceptance-first-feedback-root", "acceptance-second-feedback-root"]
    submitted = admin.post("/api/v2/evolution/experiments", json={"method": "gepa", "base_version": base["context_version"],
        "case_ids": case_ids, "split": "evolution", "max_rollouts": 20, "activate": True}, headers={"Idempotency-Key": "acceptance-complete-context-changes"})
    assert submitted.status_code == 202, submitted.text
    cutoff = now()
    cases = [{"case_id": identifier, "root_scenario_id": identifier, "split": "evolution", "synthetic": True,
              "initial_visible": {"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": cutoff,
                  "asset": {"chemistry": "LFP"}, "observations": [{"evidence_id": "acceptance-source", "summary": "Synthetic unresolved observation"}], "test_catalog": []},
              "hidden_truth": {"unresolved": True}, "feedback": {"free_text": "Retain this distinct unresolved feedback root", "evidence_ids": ["acceptance-source"]}}
             for identifier in case_ids]
    def compute_fixture(request, cancelled):
        assert not cancelled()
        batches = []
        def staged_optimizer(events, store):
            batches.append(events)
            if len(batches) == 1:
                # Test-only validated delta isolates the publication adapter;
                # real candidate scoring/limits have their own GEPA suites.
                update = {"operation": "SKILL_REVISE", "skill_id": "data-quality", "fields": {"instructions": "TEST_ONLY_EARLY_GEPA_DELTA"}}
                applied = store.apply([update], expected_version=store.snapshot()["version"], source_scope="evolution",
                    regression={"passed": True, "hard_failures": [], "split": "dev", "test_only": True})
                assert applied["state"] == "active"
                return {"state": "candidate_ready", "rollouts": 0, "test_only": True}
            return {"state": "no_update", "rollouts": 0, "test_only": True}
        result = ReplayEvaluator().evaluate("A4", cases, llm=False, initial_snapshot=obj(request["base"]["content"]),
            batch_optimizer=staged_optimizer, batch_size=1)
        assert len(batches) == 2
        assert [change["operation"] for change in result["context_changes"]] == ["ADD", "SKILL_REVISE", "ADD"]
        assert [change["operation"] for change in result["final_context_snapshot"]["changes"]] == ["ADD"]
        result.update(gepa_status="test_only_publication_boundary", budget={"rollouts": 2, "max_rollouts": 20, "test_only": True})
        return result
    job = execute_job(submitted.json()["job_id"], {"snapshot": api_evolution.evolution_snapshot, "compute": compute_fixture,
        "complete": api_evolution.evolution_complete})
    assert job["status"] == "succeeded", job["error"]
    with tx() as c:
        run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:i", {"i": job["id"]})
        snapshot = api_evolution.ensure_context(c)
        assert run["status"] == "active" and snapshot["id"] != base["id"]
        changes = obj(run["changes"])
        assert [change["operation"] for change in changes] == ["ADD", "SKILL_REVISE", "ADD"]
        assert obj(snapshot["changes"]) == changes
        assert obj(snapshot["content"])["skills"]["data-quality"]["instructions"] == "TEST_ONLY_EARLY_GEPA_DELTA"
        assert len([memory for memory in obj(snapshot["content"])["memories"] if set(memory["supporting_case_ids"]) & set(case_ids)]) == 2
