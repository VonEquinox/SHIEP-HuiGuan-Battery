"""Real CP-SAT and real API/state-machine checks, no LLM-derived golden labels."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import tx, one, execute
from app.dispatch.solver import solve, validate_assignments
from app.dispatch import jobs as dispatch_jobs
from conftest import sign_in
from test_platform import event_order, tech_profile


def problem():
    return {"horizon_minutes": 30, "engineers": [
        {"id": 1, "qualifications": ["battery"], "shifts": [[0, 30]], "max_minutes": 30,
         "max_tasks": 4, "existing_load": 0, "home_location": "A"}],
        "tasks": [{"id": 1, "duration": 10, "release": 0, "due": 10, "severity": "routine",
                   "qualifications": ["battery"], "location": "A", "tools": {}, "predecessors": []}],
        "travel_minutes": {"A|B": 5, "B|A": 5}, "tool_capacities": {}}


def test_lexicographic_critical_never_trades_for_routine_count():
    p = problem()
    p["tasks"] = [dict(p["tasks"][0], id=1, severity="critical", duration=30, due=30)] + [
        dict(p["tasks"][0], id=i, duration=5, due=30) for i in range(2, 7)]
    result = solve(p)
    assert result["status"] == "optimal"
    assert [a["order_id"] for a in result["assignments"]] == [1]
    assert result["objectives"]["critical_unassigned"] == 0
    assert result["objectives"]["routine_unassigned"] == 5
    assert result["lexicographic_complete"]


@pytest.mark.parametrize("constraint", ["qualifications", "shift", "tool", "predecessor", "travel", "hours", "hard_deadline"])
def test_hard_constraints_return_unassigned(constraint):
    p = problem()
    if constraint == "qualifications":
        p["tasks"][0]["qualifications"] = ["electrical"]
    elif constraint == "shift":
        p["engineers"][0]["shifts"] = [[0, 5], [25, 30]]
    elif constraint == "tool":
        p["tasks"][0]["tools"] = {"meter": 1}
    elif constraint == "predecessor":
        p["tasks"][0]["predecessors"] = [99]
    elif constraint == "travel":
        p["tasks"][0]["location"] = "UNKNOWN"
    elif constraint == "hours":
        p["engineers"][0]["max_minutes"] = 5
    else:
        p["tasks"][0].update(hard_deadline=True, due=5)
    result = solve(p)
    assert result["status"] == "optimal"
    assert result["assignments"] == []
    assert result["unassigned"][0]["reasons"]


def test_travel_tools_precedence_and_locks_jointly_valid():
    p = problem()
    p["tool_capacities"] = {"meter": 1}
    p["engineers"].append(dict(p["engineers"][0], id=2))
    p["tasks"] = [dict(p["tasks"][0], locked={"engineer_id": 1, "start": 0}, tools={"meter": 1}),
                  dict(p["tasks"][0], id=2, location="B", predecessors=[1], tools={"meter": 1}, due=30)]
    result = solve(p)
    assert result["status"] == "optimal"
    assert validate_assignments(p, result["assignments"]) == []
    assert result["assignments"][0]["engineer_id"] == 1
    assert result["assignments"][0]["start"] == 0
    assert result["assignments"][1]["start"] >= 10
    changed = copy.deepcopy(result["assignments"])
    changed[0]["engineer_id"] = 2
    assert any("locked_assignment_changed" in e for e in validate_assignments(p, changed))


def test_infeasible_lock_timeout_and_cancel_are_distinct():
    p = problem()
    p["tasks"][0]["locked"] = {"engineer_id": 99, "start": 0}
    assert solve(p)["status"] == "infeasible"
    assert solve(problem(), 1e-9)["status"] == "timeout"
    result = solve(problem(), cancelled=lambda: True)
    assert result["status"] == "timeout" and result["cancelled"]


def prepared_plan(admin):
    asset, _, order = event_order(admin)
    tech = tech_profile(admin)
    r = admin.get("/api/v2/dispatch/resources")
    assert r.status_code == 200, r.text
    result = admin.put("/api/v2/dispatch/resources", json={"version": r.json()["version"], "payload": {
        "engineers": [{"id": tech["id"], "shifts": [[0, 120]], "max_minutes": 120, "home_location": asset["location"]}],
        "tool_capacities": {}, "travel_minutes": {}, "provenance": "simulated", "scenario_id": "TEST_DISPATCH"}})
    assert result.status_code == 200, result.text
    request = {"order_ids": [order["id"]], "horizon_start": datetime.now(timezone.utc).isoformat(),
               "horizon_minutes": 120, "time_limit_seconds": 3}
    response = admin.post("/api/v2/dispatch/plans", json=request, headers={"Idempotency-Key": "test-create-plan"})
    assert response.status_code == 202, response.text
    plan = response.json()
    # The integration worker uses these same three functions. Compute is
    # intentionally outside tx; no SQLite write transaction surrounds CP-SAT.
    with tx() as c:
        job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": plan["job_id"]})
        snapshot = dispatch_jobs.snapshot(c, job)
    result = dispatch_jobs.compute(snapshot, lambda: False)
    with tx() as c:
        dispatch_jobs.complete(c, job, result, snapshot)
    return order, tech, admin.get(f'/api/v2/dispatch/plans/{plan["plan_id"]}').json(), request


def test_human_confirmation_only_and_idempotent(admin):
    order, tech, plan, request = prepared_plan(admin)
    assert plan["status"] == "DRAFT"
    assert admin.get(f'/api/orders/{order["id"]}').json()["status"] == "CREATED"
    repeated = admin.post("/api/v2/dispatch/plans", json=request, headers={"Idempotency-Key": "test-create-plan"})
    assert repeated.json()["plan_id"] == plan["id"]
    with TestClient(app) as researcher:
        sign_in(researcher, "research")
        assert researcher.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', json={"version": plan["version"]}, headers={"Idempotency-Key": "blocked"}).status_code == 403
    args = {"json": {"version": plan["version"]}, "headers": {"Idempotency-Key": "confirm-once"}}
    r = admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', **args)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CONFIRMED"
    repeat = admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', **args)
    assert repeat.status_code == 200 and repeat.json()["id"] == plan["id"]
    updated = admin.get(f'/api/orders/{order["id"]}').json()
    assert updated["status"] == "ASSIGNED" and updated["assignee_id"] == tech["id"]
    with tx() as c:
        assert one(c, "SELECT count(*) n FROM dispatch_assignments WHERE plan_id=:i", {"i": plan["id"]})["n"] == 1


def test_edit_revalidates_constraints_and_stale_confirm_refuses(admin):
    order, _, plan, _ = prepared_plan(admin)
    assignment = plan["result"]["assignments"][0]
    bad = {k: assignment[k] for k in ("order_id", "engineer_id", "start", "end")}
    bad["end"] += 1
    assert admin.patch(f'/api/v2/dispatch/plans/{plan["id"]}', json={"version": plan["version"], "assignments": [bad]}).status_code == 422
    good = {k: assignment[k] for k in ("order_id", "engineer_id", "start", "end")}
    changed = admin.patch(f'/api/v2/dispatch/plans/{plan["id"]}', json={"version": plan["version"], "assignments": [good]})
    assert changed.status_code == 200, changed.text
    assert not changed.json()["result"]["lexicographic_complete"]
    with tx() as c:
        execute(c, "UPDATE orders SET version=version+1 WHERE id=:i", {"i": order["id"]})
    r = admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', json={"version": changed.json()["version"]}, headers={"Idempotency-Key": "stale-confirm"})
    assert r.status_code == 409
    assert admin.get(f'/api/orders/{order["id"]}').json()["status"] == "CREATED"


def test_mutations_require_csrf_and_technician_cannot_read_other_schedule(admin):
    _, _, plan, _ = prepared_plan(admin)
    with TestClient(app) as tech:
        sign_in(tech, "tech")
        assert tech.get(f'/api/v2/dispatch/plans/{plan["id"]}').status_code == 403
        assert tech.post("/api/v2/dispatch/plans", json={"order_ids": [1], "horizon_start": "2026-10-01T00:00:00Z"}).status_code == 403
    admin.headers.pop("X-CSRF-Token")
    assert admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', json={"version": plan["version"]}, headers={"Idempotency-Key": "csrf-missing"}).status_code == 403


def test_resource_changes_stale_draft_and_creation_key_conflict(admin):
    order, _, plan, request = prepared_plan(admin)
    conflicting = dict(request, horizon_minutes=121)
    r = admin.post("/api/v2/dispatch/plans", json=conflicting, headers={"Idempotency-Key": "test-create-plan"})
    assert r.status_code == 409
    resource = admin.get("/api/v2/dispatch/resources").json()
    r = admin.put("/api/v2/dispatch/resources", json={"version": resource["version"], "payload": resource["payload"]})
    assert r.status_code == 200
    r = admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', json={"version": plan["version"]}, headers={"Idempotency-Key": "resource-stale"})
    assert r.status_code == 409
    assert admin.get(f'/api/orders/{order["id"]}').json()["status"] == "CREATED"


def test_completion_rechecks_stale_and_no_assignment_written(admin):
    order, _, plan, _ = prepared_plan(admin)
    with tx() as c:
        job = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": plan["job_id"]})
        snap = dispatch_jobs.snapshot(c, job)
        execute(c, "UPDATE dispatch_plans SET status='QUEUED' WHERE id=:i", {"i": plan["id"]})
        execute(c, "UPDATE orders SET version=version+1 WHERE id=:i", {"i": order["id"]})
    result = dispatch_jobs.compute(snap, lambda: False)
    with tx() as c:
        status = dispatch_jobs.complete(c, job, result, snap)
    assert status["status"] == "STALE"
    assert admin.get(f'/api/orders/{order["id"]}').json()["status"] == "CREATED"


def test_unknown_existing_work_blocks_new_dispatch_without_guessing_time(admin):
    order, tech, plan, request = prepared_plan(admin)
    # Fixture: a distinct live V1 task without dispatch_assignments times.
    with tx() as c:
        from app.db import insert, now
        existing = one(c, "SELECT * FROM orders WHERE id=:i", {"i": order["id"]})
        alert = one(c, "SELECT * FROM alerts WHERE id=:i", {"i": existing["alert_id"]})
        alert.pop("id")
        alert["dedup_key"] += ":unknown-time"
        alert_id = insert(c, "alerts", alert)
        existing.pop("id")
        existing.update(alert_id=alert_id, status="IN_PROGRESS", assignee_id=tech["id"])
        insert(c, "orders", existing)
        snap = dispatch_jobs.make_snapshot(c, request)
    assert snap["data"]["warnings"][0]["code"] == "unscheduled_existing_work"
    result = dispatch_jobs.compute({**snap, "time_limit_seconds": 3}, lambda: False)
    assert result["assignments"] == []


def test_assignment_confirmation_is_atomic_when_order_already_taken(admin):
    order, tech, plan, _ = prepared_plan(admin)
    r = admin.post(f'/api/orders/{order["id"]}/transition', json={"version": order["version"], "action": "assign", "assignee_id": tech["id"], "note": "人工现场派单"})
    assert r.status_code == 200, r.text
    r = admin.post(f'/api/v2/dispatch/plans/{plan["id"]}/confirm', json={"version": plan["version"]}, headers={"Idempotency-Key": "already-taken"})
    assert r.status_code == 409
    with tx() as c:
        assert one(c, "SELECT count(*) n FROM dispatch_assignments WHERE plan_id=:i", {"i": plan["id"]})["n"] == 0
        assert one(c, "SELECT status FROM dispatch_plans WHERE id=:i", {"i": plan["id"]})["status"] == "DRAFT"
