from __future__ import annotations
import concurrent.futures
import csv
import io
import json
import threading
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import tx, rows, one, insert, execute, now, js
from app.services import create_dataset, seed_demo, assess
from conftest import sign_in, PASSWORD


def fake_samples(cells=4, n=3):
    # Explicit synthetic fixture; never a reported battery/model benchmark.
    x = [0.0] * 71
    for i in range(16, 32):
        x[i] = 1 / 16
    x[66] = x[70] = 1.0
    x[68] = 1.0
    x[69] = 25.0
    return [
        {
            "cell_id": f"fixture-cell-{c}",
            "sample_key": f"test-{c}-{i}",
            "ordinal": i,
            "current": x.copy(),
            "reference": x.copy(),
            "log_ratio": 0.0,
            "truth": 0.95 - i * 0.02,
            "batch": "fixture",
        }
        for c in range(cells)
        for i in range(n)
    ]


def dataset_fixture():
    with tx() as c:
        admin = one(c, "SELECT id FROM users WHERE username='admin'")["id"]
        return create_dataset(
            c,
            {
                "name": "Test-only synthetic",
                "source": "test fixture",
                "source_hash": "a" * 64,
                "provenance": "simulated",
                "quality": {"verified": False, "test_only": True},
                "samples": fake_samples(),
            },
            admin,
        )


def seed(client):
    r = client.post("/api/demo/seed")
    assert r.status_code == 200, r.text
    assets = client.get("/api/assets").json()
    return next(a for a in assets if a["kind"] == "cell")


def event_order(client):
    asset = seed(client)
    r = client.post(
        "/api/demo/events",
        json={"asset_id": asset["id"], "scenario": "capacity-review"},
    )
    assert r.status_code == 200, r.text
    alert_id = r.json()["alert_id"]
    r = client.post(f"/api/alerts/{alert_id}/work-order")
    assert r.status_code == 201, r.text
    return asset, alert_id, r.json()


def tech_profile(client, on_call=True):
    users = client.get("/api/users").json()
    tech = next(u for u in users if u["username"] == "tech")
    r = client.post(
        "/api/personnel",
        json={
            "user_id": tech["id"],
            "skills": ["battery"],
            "on_call": on_call,
            "latitude": 31.051,
            "longitude": 121.801,
            "max_workload": 4,
        },
    )
    assert r.status_code == 200, r.text
    return tech


def transition(client, order, action, **extra):
    return client.post(
        f'/api/orders/{order["id"]}/transition',
        json={
            "version": order["version"],
            "action": action,
            "note": "测试处置依据记录",
            **extra,
        },
    )


def fixture_prediction(asset, ds, ordinal=0, soh=0.8, model_id=None):
    with tx() as c:
        uid = one(c, "SELECT id FROM users WHERE username='admin'")["id"]
        if model_id is None:
            model_id = insert(
                c,
                "models",
                {
                    "name": "Explicit fake for route tests",
                    "kind": "trained_et",
                    "schema_id": "xjtu_71d_partial_cc_v1",
                    "status": "enabled",
                    "artifact_path": "not-real-test-model",
                    "artifact_hash": "x" * 64,
                    "train_cells": "[]",
                    "metrics": "{}",
                    "metadata": "{}",
                    "created_at": now(),
                    "created_by": uid,
                },
            )
        s = one(
            c,
            "SELECT * FROM samples WHERE dataset_id=:d AND ordinal=:i ORDER BY id LIMIT 1",
            {"d": ds, "i": ordinal},
        )
        job = insert(
            c,
            "jobs",
            {
                "kind": "inference",
                "status": "succeeded",
                "payload": "{}",
                "created_by": uid,
                "created_at": now(),
                "idempotency_key": str(now()),
                "request_hash": "fixture",
            },
        )
        p = insert(
            c,
            "predictions",
            {
                "job_id": job,
                "model_id": model_id,
                "sample_id": s["id"],
                "asset_id": asset["id"],
                "installation_id": asset["installation_id"],
                "soh": soh,
                "outside_fraction": 0.0,
                "applicability": "within_observed_range",
                "input_hash": s["input_hash"],
                "provenance": "simulated",
                "created_at": now(),
            },
        )
        return p, model_id


def test_first_run_and_unknown_api(client):
    assert client.get("/api/status").json()["production_bms"] is False
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/api/assets").status_code == 401


def test_session_cookie_csrf_logout(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert (
        "HttpOnly" in r.headers["set-cookie"]
        and "SameSite=strict" in r.headers["set-cookie"]
    )
    csrf = r.json()["csrf"]
    assert client.post("/api/demo/seed").status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert (
        client.post(
            "/api/demo/seed", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/demo/seed", headers={"Origin": "http://testserver"}
        ).status_code
        == 200
    )
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "route,body",
    [
        ("/demo/seed", None),
        ("/models/register-frozen", None),
        ("/demo/events", {"asset_id": 1, "scenario": "capacity-review"}),
        (
            "/users",
            {
                "username": "new",
                "display_name": "new",
                "password": PASSWORD,
                "role": "admin",
            },
        ),
    ],
)
def test_viewer_no_mutations(client, route, body):
    sign_in(client, "viewer")
    assert client.post("/api" + route, json=body).status_code == 403


def test_login_throttle(client):
    for _ in range(8):
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": PASSWORD}
        ).status_code
        == 429
    )


def test_last_admin_and_session_revocation(admin):
    current = admin.get("/api/auth/me").json()
    assert (
        admin.put(
            "/api/users/" + str(current["id"]),
            json={"version": current["version"], "role": "viewer", "active": True},
        ).status_code
        == 409
    )
    users = admin.get("/api/users").json()
    viewer = next(u for u in users if u["username"] == "viewer")
    with TestClient(app) as v:
        sign_in(v, "viewer")
        assert (
            admin.put(
                "/api/users/" + str(viewer["id"]),
                json={"version": viewer["version"], "role": "viewer", "active": False},
            ).status_code
            == 200
        )
        assert v.get("/api/auth/me").status_code == 401


def test_asset_hierarchy_and_version(admin):
    cell = seed(admin)
    all_assets = admin.get("/api/assets").json()
    site = next(a for a in all_assets if a["kind"] == "site")
    assert len([a for a in all_assets if a["kind"] == "cell"]) == 21
    assert (
        admin.post(
            "/api/assets",
            json={
                "code": "BAD",
                "name": "bad",
                "kind": "cell",
                "parent_id": site["id"],
            },
        ).status_code
        == 422
    )
    assert (
        admin.post(
            f'/api/assets/{site["id"]}/retire', json={"version": 1, "note": "测试退役"}
        ).status_code
        == 409
    )
    body = {
        "version": 1,
        "name": "renamed",
        "latitude": None,
        "longitude": None,
        "location": "test",
    }
    assert admin.put("/api/assets/" + str(cell["id"]), json=body).status_code == 200
    assert admin.put("/api/assets/" + str(cell["id"]), json=body).status_code == 409


def test_dataset_and_explicit_binding(admin):
    ds = dataset_fixture()
    cell = seed(admin)
    assert (
        admin.post(
            f'/api/assets/{cell["id"]}/binding',
            json={"dataset_id": ds, "cell_id": "missing"},
        ).status_code
        == 422
    )
    assert (
        admin.post(
            f'/api/assets/{cell["id"]}/binding',
            json={"dataset_id": ds, "cell_id": "fixture-cell-0"},
        ).status_code
        == 200
    )
    assert admin.delete("/api/datasets/" + str(ds)).status_code == 409
    page = admin.get(f"/api/datasets/{ds}/samples?limit=2").json()
    assert len(page["items"]) == 2 and page["total"] == 12
    assert "current_json" not in page["items"][0]
    s = admin.get("/api/samples/" + str(page["items"][0]["id"])).json()
    assert len(s["current"]) == 71
    export = admin.get(f"/api/datasets/{ds}/export?limit=3")
    assert export.status_code == 200
    assert len(list(csv.DictReader(io.StringIO(export.text)))) == 3


def test_csv_validation_and_source_dedup(admin):
    ds = dataset_fixture()
    blob = admin.get(f"/api/datasets/{ds}/export?limit=3").content
    kwargs = {
        "data": {"name": "uploaded"},
        "files": {"file": ("features.csv", blob, "text/csv")},
    }
    r = admin.post("/api/datasets/upload", **kwargs)
    assert r.status_code == 201, r.text
    assert admin.post("/api/datasets/upload", **kwargs).json()["id"] == r.json()["id"]
    bad = blob.replace(b"fixture-cell-0", b"Batch-4/R3_battery-5")
    assert (
        admin.post(
            "/api/datasets/upload",
            data={"name": "protected"},
            files={"file": ("bad.csv", bad, "text/csv")},
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/datasets/upload",
            data={"name": "pickle"},
            files={"file": ("bad.pkl", b"not trusted", "application/octet-stream")},
        ).status_code
        == 415
    )
    assert (
        admin.post(
            "/api/datasets/upload",
            data={"name": "bad"},
            files={"file": ("bad.csv", b"a,b\n1,2", "text/csv")},
        ).status_code
        == 422
    )


def test_job_idempotency_cancel_and_invalid_kind(admin):
    ds = dataset_fixture()
    payload = {"kind": "training", "dataset_id": ds}
    r = admin.post("/api/jobs", headers={"Idempotency-Key": "test-job"}, json=payload)
    assert r.status_code == 202, r.text
    assert (
        admin.post(
            "/api/jobs", headers={"Idempotency-Key": "test-job"}, json=payload
        ).json()
        == r.json()
    )
    assert (
        admin.post(
            "/api/jobs",
            headers={"Idempotency-Key": "test-job"},
            json={**payload, "n_estimators": 200},
        ).status_code
        == 409
    )
    identifier = r.json()["job_id"]
    assert admin.post(f"/api/jobs/{identifier}/cancel").status_code == 200
    assert admin.get(f"/api/jobs/{identifier}").json()["status"] == "cancelled"
    assert (
        admin.post(
            "/api/jobs", json={"kind": "eval-any-file", "dataset_id": ds}
        ).status_code
        == 422
    )


def test_alert_dedup_and_order_idempotency(admin):
    asset, alert, order = event_order(admin)
    a = admin.post(
        "/api/demo/events",
        json={"asset_id": asset["id"], "scenario": "capacity-review"},
    ).json()["alert_id"]
    assert a == alert
    assert admin.post(f"/api/alerts/{alert}/work-order").json()["id"] == order["id"]
    assert len(admin.get("/api/orders").json()) == 1
    event = admin.get("/api/health-events").json()[0]
    assert (
        event["evidence"]["not_model_result"] is True
        and event["provenance"] == "simulated"
    )


def test_off_duty_and_illegal_skip(admin):
    _, _, order = event_order(admin)
    tech = tech_profile(admin, on_call=False)
    assert transition(admin, order, "assign", assignee_id=tech["id"]).status_code == 422
    assert transition(admin, order, "close").status_code == 409


def test_full_persistent_workflow_attachments_and_feedback(admin):
    asset, alert, order = event_order(admin)
    tech = tech_profile(admin)
    ds = dataset_fixture()
    prediction, _ = fixture_prediction(asset, ds)
    r = transition(admin, order, "assign", assignee_id=tech["id"])
    assert r.status_code == 200, r.text
    order = r.json()
    with TestClient(app) as t, TestClient(app) as other, TestClient(app) as dispatch:
        sign_in(t, "tech")
        sign_in(other, "othertech")
        sign_in(dispatch, "dispatch")
        assert other.get("/api/orders/" + str(order["id"])).status_code == 403
        assert transition(other, order, "accept").status_code == 403
        for action in ("accept", "start"):
            r = transition(t, order, action)
            assert r.status_code == 200, r.text
            order = r.json()
        assert (
            transition(t, order, "resolve").status_code == 422
        )  # evidence is mandatory
        bad = t.post(
            f'/api/orders/{order["id"]}/attachments',
            files={"file": ("fake.png", b"not png", "image/png")},
        )
        assert bad.status_code == 415
        bad = t.post(
            f'/api/orders/{order["id"]}/attachments',
            files={"file": ("../x.txt", b"text", "text/plain")},
        )
        assert bad.status_code == 422
        up = t.post(
            f'/api/orders/{order["id"]}/attachments',
            files={
                "file": ("inspection.txt", "Synthetic test evidence.", "text/plain")
            },
        )
        assert up.status_code == 201, up.text
        aid = up.json()["id"]
        assert other.get("/api/attachments/" + str(aid)).status_code == 403
        assert (
            t.get("/api/attachments/" + str(aid)).content == b"Synthetic test evidence."
        )
        feedback = {
            "prediction_id": prediction,
            "order_id": order["id"],
            "value": 0.88,
            "provenance": "simulated",
            "source": "fixture test",
            "measured_at": now(),
            "note": "not real measurement",
        }
        assert t.post("/api/feedback", json=feedback).status_code == 201
        r = transition(t, order, "resolve")
        assert r.status_code == 200, r.text
        order = r.json()
        assert transition(t, order, "verify").status_code == 403
        r = transition(dispatch, order, "verify")
        assert r.status_code == 200, r.text
        order = r.json()
        r = transition(dispatch, order, "close")
        assert r.status_code == 200, r.text
        order = r.json()
        assert (
            t.post(
                f'/api/orders/{order["id"]}/attachments',
                files={"file": ("late.txt", b"late", "text/plain")},
            ).status_code
            == 409
        )
        persisted = dispatch.get("/api/orders/" + str(order["id"])).json()
        assert persisted["status"] == "CLOSED" and len(persisted["events"]) == 7
        assert persisted["feedback"][0]["provenance"] == "simulated"
    assert admin.get("/api/predictions/" + str(prediction)).json()["soh"] == 0.8
    assert (
        admin.get("/api/alerts").json()[0]["status"] == "OPEN"
    )  # close is not false asset recovery


def test_concurrent_state_transition_one_winner(admin):
    _, _, order = event_order(admin)
    tech = tech_profile(admin)
    # Same session / same version copied across distinct HTTP clients.
    cookies = dict(admin.cookies)
    headers = dict(admin.headers)

    def submit():
        with TestClient(app) as c:
            c.cookies.update(cookies)
            c.headers.update(headers)
            return transition(c, order, "assign", assignee_id=tech["id"]).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(results) == [200, 409]


def test_unique_observation_persistence_and_replacement(admin):
    asset = seed(admin)
    ds = dataset_fixture()
    p, model = fixture_prediction(asset, ds, ordinal=0)
    with tx() as c:
        assess(c, p)
    assert not admin.get("/api/alerts").json()  # needs2 distinct samples
    p2, _ = fixture_prediction(asset, ds, ordinal=0, model_id=model)
    with tx() as c:
        assess(c, p2)
    assert not admin.get("/api/alerts").json()
    p3, _ = fixture_prediction(asset, ds, ordinal=1, model_id=model)
    with tx() as c:
        assess(c, p3)
    alerts = admin.get("/api/alerts").json()
    assert len(alerts) == 1
    p4, _ = fixture_prediction(asset, ds, ordinal=1, model_id=model)
    with tx() as c:
        assess(c, p4)
    assert len(admin.get("/api/alerts").json()) == 1
    r = admin.post(
        f'/api/assets/{asset["id"]}/replace',
        json={"version": 1, "note": "模拟更换记录"},
    )
    assert r.status_code == 200, r.text
    detail = admin.get("/api/assets/" + str(asset["id"])).json()
    assert detail["health"]["state"] == "unknown" and len(detail["history"]) == 4
    assert detail["installation_id"] != asset["installation_id"]


def test_invalid_feedback_time_and_notification_ownership(admin):
    asset, _, order = event_order(admin)
    ds = dataset_fixture()
    p, _ = fixture_prediction(asset, ds)
    r = admin.post(
        "/api/feedback",
        json={
            "prediction_id": p,
            "order_id": order["id"],
            "value": 0.9,
            "provenance": "measured_declared",
            "source": "test",
            "measured_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 422
    note = admin.get("/api/notifications").json()[0]
    with TestClient(app) as v:
        sign_in(v, "viewer")
        assert (
            v.post("/api/notifications/" + str(note["id"]) + "/read").status_code == 403
        )


def test_password_change_revokes_sessions_and_rejects_wrong_current(client):
    user = sign_in(client, "viewer")
    new = "A-new-test-password-1234"
    assert (
        client.post(
            f'/api/users/{user["id"]}/password',
            json={"current_password": "wrong", "new_password": new},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f'/api/users/{user["id"]}/password',
            json={"current_password": PASSWORD, "new_password": new},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "viewer", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"username": "viewer", "password": new}
        ).status_code
        == 200
    )


def test_admin_reset_without_exposing_password_in_audit(admin):
    user = next(u for u in admin.get("/api/users").json() if u["username"] == "tech")
    password = "Administrator-reset-test-1234"
    assert (
        admin.post(
            f'/api/users/{user["id"]}/password', json={"new_password": password}
        ).status_code
        == 200
    )
    records = admin.get("/api/audit?action=password").text
    assert password not in records and "password_reset" in records


def test_aggregate_coverage_uses_descendant_cells_not_fake_pack_soh(admin):
    cell = seed(admin)
    ds = dataset_fixture()
    fixture_prediction(cell, ds)
    site = next(a for a in admin.get("/api/assets").json() if a["kind"] == "site")
    aggregate = admin.get("/api/assets/" + str(site["id"])).json()["aggregate"]
    assert aggregate["total_cells"] == 21 and aggregate["fresh_prediction_cells"] == 1
    assert aggregate["not_measured_pack_soh"] is True and "soh" not in aggregate


def test_model_comparison_requires_same_samples_and_recomputes(admin):
    asset = seed(admin)
    ds = dataset_fixture()
    p1, model = fixture_prediction(asset, ds, 0, 0.8)
    p2, _ = fixture_prediction(asset, ds, 0, 0.9, model)
    with tx() as c:
        first = one(c, "SELECT * FROM predictions WHERE id=:i", {"i": p1})
        second = one(c, "SELECT * FROM predictions WHERE id=:i", {"i": p2})
        for j in (first["job_id"], second["job_id"]):
            execute(
                c,
                "UPDATE jobs SET kind='evaluation',result=:r WHERE id=:i",
                {"r": js({"metrics": {"scope": "test_only"}}), "i": j},
            )
    r = admin.get(f'/api/comparisons?job_ids={first["job_id"]},{second["job_id"]}')
    assert r.status_code == 200, r.text
    assert r.json()["comparisons"][0]["cell_macro_mae_pp"] == pytest.approx(15.0)
    assert r.json()["comparisons"][1]["cell_macro_mae_pp"] == pytest.approx(5.0)
    with tx() as c:
        different = one(
            c,
            "SELECT id FROM samples WHERE dataset_id=:d AND ordinal=1 ORDER BY id LIMIT 1",
            {"d": ds},
        )
        execute(
            c,
            "UPDATE predictions SET sample_id=:s WHERE id=:i",
            {"s": different["id"], "i": p2},
        )
    assert (
        admin.get(
            f'/api/comparisons?job_ids={first["job_id"]},{second["job_id"]}'
        ).status_code
        == 409
    )


def test_cannot_mix_cell_history_by_rebinding_installation(admin):
    asset = seed(admin)
    ds = dataset_fixture()
    assert (
        admin.post(
            f'/api/assets/{asset["id"]}/binding',
            json={"dataset_id": ds, "cell_id": "fixture-cell-0"},
        ).status_code
        == 200
    )
    fixture_prediction(asset, ds)
    assert (
        admin.post(
            f'/api/assets/{asset["id"]}/binding',
            json={"dataset_id": ds, "cell_id": "fixture-cell-1"},
        ).status_code
        == 409
    )


def test_quiescent_backup_restore_keeps_records_revokes_sessions(admin):
    from pathlib import Path
    import sqlite3, uuid, shutil
    from app.config import RUNTIME
    from app.backup import create_backup, restore_backup

    asset, _, order = event_order(admin)
    backup = create_backup()
    destination = RUNTIME / ("restored-" + uuid.uuid4().hex)
    try:
        report = restore_backup(backup, destination)
        assert report["all_sessions_revoked"] is True
        with sqlite3.connect(destination / "battery.db") as c:
            assert c.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
            assert c.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        with pytest.raises(ValueError):
            restore_backup(backup, destination)
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def test_unverified_source_is_review_not_green_and_cannot_raise_experimental_alert(
    admin,
):
    asset = seed(admin)
    ds = dataset_fixture()
    p, _ = fixture_prediction(asset, ds, soh=0.98)
    with tx() as c:
        execute(
            c,
            "UPDATE predictions SET provenance='declared_unverified' WHERE id=:i",
            {"i": p},
        )
        assess(c, p)
    detail = admin.get("/api/assets/" + str(asset["id"])).json()
    assert detail["health"]["state"] == "review"
    assert detail["health"]["prediction"]["provenance"] == "declared_unverified"
    assert admin.get("/api/health-events").json() == []


def test_chunked_request_cannot_bypass_upload_limit(admin):
    def chunks():
        for _ in range(10):
            yield b"x" * 1024 * 1024

    response = admin.post(
        "/api/demo/seed",
        content=chunks(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    assert admin.get("/api/assets").json() == []


def test_small_chunked_json_is_replayed_correctly(admin):
    content = json.dumps(
        {"code": "CHUNKED-SITE", "kind": "site", "name": "分块输入测试"}
    ).encode()
    response = admin.post(
        "/api/assets",
        content=iter([content[:20], content[20:]]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["code"] == "CHUNKED-SITE"


def test_model_child_exits_when_parent_disappears():
    import fcntl, os, subprocess, sys, time
    from pathlib import Path
    from app.config import APP_ROOT, RUNTIME, ML_PYTHON

    if not ML_PYTHON.exists():
        pytest.skip("Original local ML interpreter unavailable")
    request = RUNTIME / "watchdog-request.json"
    request.write_text('{"action":"never-executed-fixture"}')
    output = RUNTIME / "watchdog-result.json"
    log = RUNTIME / "watchdog.log"
    lock = (APP_ROOT / "runtime/model-compute.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX)
    program = """import subprocess,time,sys
log=open(sys.argv[4],'w')
p=subprocess.Popen([sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[5]],stdout=log,stderr=subprocess.STDOUT)
print(p.pid,flush=True)
time.sleep(60)
"""
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            program,
            str(ML_PYTHON),
            str(APP_ROOT / "ml_bridge.py"),
            str(request),
            str(log),
            str(output),
        ],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    child = None
    try:
        child = int(parent.stdout.readline().strip())
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if log.exists() and "等待本地单计算任务锁" in log.read_text():
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Child did not reach compute admission guard")
        parent.terminate()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Orphaned model child remained alive")
        assert not output.exists()
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=5)
        if child:
            try:
                os.kill(child, 15)
            except ProcessLookupError:
                pass
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
