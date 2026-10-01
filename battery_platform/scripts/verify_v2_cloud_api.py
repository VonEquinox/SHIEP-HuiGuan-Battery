"""Opt-in real provider/API smoke on a disposable, explicitly synthetic database.

Run from the repository root after exporting BATTERY_LLM_* credentials locally:
    .venv/bin/python battery_platform/scripts/verify_v2_cloud_api.py
No test account credentials, provider keys or raw HTTP headers are exported.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if not os.environ.get("BATTERY_LLM_API_KEY"):
        raise SystemExit("Export BATTERY_LLM_API_KEY locally to run this opt-in cloud smoke.")
    repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository / "battery_platform"))
    with tempfile.TemporaryDirectory(prefix="huiguan-cloud-api-") as runtime:
        os.environ["BATTERY_RUNTIME"] = runtime
        os.environ["BATTERY_DISABLE_WORKER"] = "1"
        from fastapi.testclient import TestClient
        from app.db import initialize, tx, one, execute, now
        from app.main import app
        from app.security import create_user
        from app.services import seed_demo, demo_event
        from app.jobs import JobSupervisor, extension_handler

        initialize()
        password = secrets.token_urlsafe(24)
        with tx() as connection:
            actor = create_user(connection, "cloud-smoke", "合成场景云端 API 验证", password, "admin")
            seed_demo(connection, actor)
            asset = one(connection, "SELECT * FROM assets WHERE kind='cell' ORDER BY id LIMIT 1")
            demo_event(connection, asset["id"], "sensor-temperature", actor)
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "cloud-smoke", "password": password})
            assert login.status_code == 200, login.text
            client.headers["X-CSRF-Token"] = login.json()["csrf"]
            submitted = client.post("/api/v2/agent/runs", headers={"Idempotency-Key": "opt-in-cloud-api-smoke"},
                json={"asset_id": asset["id"], "installation_id": asset["installation_id"], "visible_cutoff": now()})
            assert submitted.status_code == 202, submitted.text
            identifiers = submitted.json()
            with tx() as connection:
                execute(connection, "UPDATE jobs SET status='running',started_at=:t WHERE id=:i",
                        {"t": now(), "i": identifiers["job_id"]})
                job = one(connection, "SELECT * FROM jobs WHERE id=:i", {"i": identifiers["job_id"]})
            JobSupervisor().run_extension(job, extension_handler(job["kind"]))
            result = client.get(f"/api/v2/agent/runs/{identifiers['run_id']}")
            assert result.status_code == 200, result.text
            detail = result.json()
            assert detail["status"] == "succeeded", detail["job"].get("error")
            execution = detail["job"]["result"]
            assert execution["execution_mode"] == "cloud" and execution["run"]["cloud_report_valid"], execution
            with tx() as connection:
                formal_orders = one(connection, "SELECT count(*) n FROM orders")["n"]
                pending = one(connection, "SELECT count(*) n FROM work_proposals WHERE status='PENDING_APPROVAL'")["n"]
            assert formal_orders == 0, "A report may not automatically create a formal work order."
            evidence = {"created_at": now(), "provider_model": os.environ.get("BATTERY_LLM_MODEL"),
                "provenance": "self_synthetic", "scope": "real HTTP API and real cloud executor; no approval or physical control",
                "http_submit_status": submitted.status_code, "http_detail_status": result.status_code,
                "request_id_present": bool(result.headers.get("X-Request-ID")), "job_status": detail["status"],
                "execution": execution, "report": detail["report"], "formal_orders_before_approval": formal_orders,
                "pending_proposals": pending, "temporary_database_removed": True}
            destination = repository / "battery_platform/reports/v2_integration/cloud_api.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"artifact": str(destination), "mode": execution["execution_mode"],
                "formal_orders": formal_orders, "pending_proposals": pending, "run": execution.get("run")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
