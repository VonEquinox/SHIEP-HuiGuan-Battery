"""A group order's secondary installation observations reach bounded peer tools."""
from fastapi.testclient import TestClient

from app import api_agent
from app.agent.contracts import public_context
from app.db import now, obj, one, tx
from app.main import app
from conftest import sign_in
from test_platform import seed
from test_v2_workflow import observation, work_job


def test_secondary_installation_observation_is_scoped_peer_evidence(admin, monkeypatch):
    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)
    primary = seed(admin)
    peer = next(item for item in admin.get("/api/assets").json() if item["kind"] == "cell" and item["parent_id"] == primary["parent_id"] and item["id"] != primary["id"])
    for asset in (primary, peer):
        response = admin.post("/api/demo/events", json={"asset_id": asset["id"], "scenario": "capacity-review"})
        assert response.status_code == 200, response.text
    response = admin.post("/api/v2/incidents/analyze", json={"asset_ids": [primary["id"], peer["id"]], "visible_cutoff": now()}, headers={"Idempotency-Key": "secondary-incident"})
    assert response.status_code == 202, response.text
    analyzed = work_job(response.json()["job_id"])
    assert analyzed["status"] == "succeeded", analyzed["error"]
    group_id = obj(analyzed["result"])["group_ids"][0]
    response = admin.post("/api/v2/agent/runs", json={"asset_id": primary["id"], "installation_id": primary["installation_id"], "incident_group_id": group_id,
                          "visible_cutoff": now()}, headers={"Idempotency-Key": "secondary-report"})
    assert response.status_code == 202, response.text
    initial = response.json()
    assert work_job(initial["job_id"])["status"] == "succeeded"
    report = admin.get(f"/api/v2/agent/runs/{initial['run_id']}").json()["report"]
    response = admin.post("/api/v2/work-proposals", json={"report_id": report["id"], "asset_ids": [primary["id"], peer["id"]], "incident_group_id": group_id,
                          "title": "有界群组独立读数", "allowed_tests": ["T_CHANNEL_CHECK"], "required_tests": ["T_CHANNEL_CHECK"]},
                          headers={"Idempotency-Key": "secondary-proposal"})
    assert response.status_code == 201, response.text
    proposal = response.json()
    response = admin.post(f"/api/v2/work-proposals/{proposal['id']}/approve", json={"version": proposal["version"]}, headers={"Idempotency-Key": "secondary-approve"})
    assert response.status_code == 200, response.text
    order = response.json()["order"]
    technician = next(user for user in admin.get("/api/users").json() if user["username"] == "tech")
    response = admin.post("/api/personnel", json={"user_id": technician["id"], "skills": ["battery", "instrumentation"], "on_call": True})
    assert response.status_code == 200, response.text
    response = admin.post(f"/api/orders/{order['id']}/transition", json={"version": order["version"], "action": "assign", "assignee_id": technician["id"]})
    assert response.status_code == 200, response.text
    order = response.json()
    with TestClient(app) as mobile:
        sign_in(mobile, "tech")
        response = mobile.post(f"/api/orders/{order['id']}/transition", json={"version": order["version"], "action": "accept"})
        assert response.status_code == 200, response.text
        order = response.json()
        body = {**observation(peer, order, "secondary-measurement-uuid"), "asset_id": peer["id"], "free_text": "SECONDARY_MEMBER_VISIBLE；仅针对第二安装的独立读数。"}
        response = mobile.post(f"/api/v2/orders/{order['id']}/observations", json=body)
        assert response.status_code == 201, response.text
        pending = response.json()
    with tx() as c:
        snapshot = api_agent.agent_snapshot(c, one(c, "SELECT * FROM jobs WHERE id=:i", {"i": pending["job_id"]}))
    visible = public_context(snapshot, cutoff=snapshot["visible_cutoff"], installation_id=primary["installation_id"])
    assert all(item.get("id") != pending["observation_id"] for item in visible["observations"])
    member = next(member for member in visible["group_context"]["groups"][0]["members"] if member["asset_id"] == peer["id"])
    assert member["peer_installation_id"] == peer["installation_id"]
    observed = member["observations"][0]
    assert observed["id"] == pending["observation_id"] and observed["peer_installation_id"] == peer["installation_id"]
    assert "SECONDARY_MEMBER_VISIBLE" in observed["free_text"]
    assert member["not_confirmed_common_cause"] is True
    assert work_job(pending["job_id"])["status"] == "succeeded"
