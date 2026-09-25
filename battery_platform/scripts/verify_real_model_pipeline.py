"""Run actual model/import/training/evaluation through the app job supervisor.

All operations use a fresh isolated acceptance runtime, never protected test
cells. Metrics here are execution checks, not claims of battery SOTA.
"""

from __future__ import annotations
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
runtime = APP / "runtime" / ("acceptance-ml-" + str(int(time.time())))
os.environ["BATTERY_RUNTIME"] = str(runtime)
os.environ["BATTERY_DISABLE_WORKER"] = "0"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
from fastapi.testclient import TestClient
from app.main import app
from app.db import initialize, tx, one, rows, insert, execute, now
from app.security import create_user
from app.services import sha

OUT = APP / "runtime/acceptance"
OUT.mkdir(exist_ok=True, parents=True)
PROTECTED = {
    "Batch-4/R3_battery-5",
    "Batch-5/RW_battery-5",
    "Batch-6/Sim_satellite_battery-5",
}
FROZEN = APP.parent / "model_lab/reports/round3/champion_hybrid_v2_streaming"
MODEL_SOURCES = [
    FROZEN / "manifest.json",
    FROZEN / "et_champion.joblib",
    FROZEN / "development_context.npz",
    APP.parent / "model_lab/modeling/frozen_hybrid_streaming.py",
    APP.parent / "model_lab/modeling/frozen_hybrid.py",
    APP.parent / "model_lab/modeling/frozen_et.py",
    APP.parent / "model_lab/reports/round2/cv_physical/view_bundle.npz",
]
before = {str(p.relative_to(APP.parent)): sha(p) for p in MODEL_SOURCES}
initialize()
password = secrets.token_urlsafe(24)
with tx() as c:
    uid = create_user(c, "acceptance-admin", "隔离验收管理员", password, "admin")
checks = []
job_reports = []
started = time.monotonic()


def check(name, value, details=None):
    checks.append({"check": name, "passed": bool(value), "details": details})
    if not value:
        raise AssertionError(name + ": " + str(details))


def wait(client, job_id, expected="succeeded"):
    last = None
    deadline = time.monotonic() + 905
    while time.monotonic() < deadline:
        result = client.get(f"/api/jobs/{job_id}").json()
        current = (result["status"], result["progress"])
        if current != last:
            print(
                json.dumps(
                    {
                        "job": job_id,
                        "kind": result["kind"],
                        "status": current[0],
                        "progress": current[1],
                    }
                ),
                flush=True,
            )
            last = current
        if current[0] in ("succeeded", "failed", "cancelled", "interrupted"):
            check(
                f"job_{job_id}_{expected}", current[0] == expected, result.get("error")
            )
            job_reports.append(
                {
                    "id": job_id,
                    "kind": result["kind"],
                    "status": result["status"],
                    "result": result["result"],
                    "error": result.get("error"),
                }
            )
            return result
        time.sleep(0.4)
    raise RuntimeError("bounded app job did not finish")


def submit(client, body):
    r = client.post(
        "/api/jobs", json=body, headers={"Idempotency-Key": uuid.uuid4().hex}
    )
    check("enqueue_" + body["kind"], r.status_code == 202, r.text[:300])
    return wait(client, r.json()["job_id"])


try:
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/login",
            json={"username": "acceptance-admin", "password": password},
        )
        check("login", r.status_code == 200)
        client.headers["X-CSRF-Token"] = r.json()["csrf"]
        r = client.post(
            "/api/datasets/import-xjtu", headers={"Idempotency-Key": uuid.uuid4().hex}
        )
        check("import_queued", r.status_code == 202)
        imported = wait(client, r.json()["job_id"])
        ds = imported["result"]["dataset_id"]
        check(
            "verified2058_rows_21cells",
            imported["result"]["rows"] == 2058 and imported["result"]["cells"] == 21,
        )
        with tx() as c:
            cells = {
                s["cell_id"] for s in rows(c, "SELECT DISTINCT cell_id FROM samples")
            }
        check("protected_cells_excluded", not cells & PROTECTED)
        check("seed_simulated_assets", client.post("/api/demo/seed").status_code == 200)
        check(
            "explicit_replay_binding",
            client.post(f"/api/demo/bind/{ds}").status_code == 200,
        )
        check(
            "frozen_model_registration",
            client.post("/api/models/register-frozen").status_code == 200,
        )
        models = client.get("/api/models").json()
        et = next(m for m in models if m["kind"] == "frozen_et")
        hybrid = next(m for m in models if m["kind"] == "frozen_hybrid")
        page = client.get(f"/api/datasets/{ds}/samples?limit=3").json()
        sample_ids = [s["id"] for s in page["items"]]
        fast = submit(
            client,
            {
                "kind": "inference",
                "dataset_id": ds,
                "model_id": et["id"],
                "sample_ids": sample_ids,
            },
        )
        check(
            "fast_named_branch",
            fast["result"]["model_kind"] == "frozen_et"
            and fast["result"]["device"] == "cpu",
        )
        check(
            "training_overlap_honest",
            fast["result"]["metrics"]["scope"] == "in_sample_or_mixed",
        )
        trained = submit(
            client,
            {
                "kind": "training",
                "dataset_id": ds,
                "n_estimators": 100,
                "min_samples_leaf": 3,
            },
        )
        train = set(trained["result"]["train_cells"])
        valid = set(trained["result"]["validation_cells"])
        check(
            "real_training_cell_disjoint",
            not train & valid and train | valid == cells,
            {"train": len(train), "validation": len(valid)},
        )
        model_id = trained["result"]["model_id"]
        with tx() as c:
            sample = one(
                c,
                "SELECT id FROM samples WHERE cell_id=:s ORDER BY id LIMIT 1",
                {"s": sorted(valid)[0]},
            )
        evaluated = submit(
            client,
            {
                "kind": "evaluation",
                "dataset_id": ds,
                "model_id": model_id,
                "sample_ids": [sample["id"]],
            },
        )
        check(
            "new_model_validation_no_overlap",
            evaluated["result"]["metrics"]["overlap_cells"] == [],
        )
        full = submit(
            client,
            {
                "kind": "inference",
                "dataset_id": ds,
                "model_id": hybrid["id"],
                "sample_ids": sample_ids[:1],
            },
        )
        actual = client.get("/api/predictions?job_id=" + str(full["id"])).json()
        check(
            "hybrid_real_both_branches",
            len(actual) == 1
            and actual[0]["tabicl_soh"] is not None
            and actual[0]["extra_trees_soh"] is not None,
        )
        check(
            "hybrid_geometric_mixture",
            abs(
                actual[0]["soh"]
                - (actual[0]["tabicl_soh"] * actual[0]["extra_trees_soh"]) ** 0.5
            )
            < 1e-9,
        )
        check(
            "real_mps_hybrid",
            full["result"]["device"] == "mps",
            {"device": full["result"]["device"]},
        )
        # Corrupt only a newly trained disposable app model. Never alter original weights.
        with tx() as c:
            model = one(c, "SELECT * FROM models WHERE id=:i", {"i": model_id})
        path = Path(model["artifact_path"])
        copy = path.with_suffix(".saved")
        path.rename(copy)
        try:
            request = {
                "kind": "inference",
                "dataset_id": ds,
                "model_id": model_id,
                "sample_ids": [sample["id"]],
            }
            r = client.post(
                "/api/jobs", json=request, headers={"Idempotency-Key": uuid.uuid4().hex}
            )
            failed = wait(client, r.json()["job_id"], "failed")
            check(
                "missing_model_no_fake_predictions",
                client.get("/api/predictions?job_id=" + str(failed["id"])).json() == [],
            )
        finally:
            copy.rename(path)
        with tx() as c:
            count = one(c, "SELECT count(*) n FROM predictions")["n"]
            abandoned = insert(
                c,
                "jobs",
                {
                    "kind": "inference",
                    "status": "running",
                    "payload": "{}",
                    "created_by": uid,
                    "created_at": now(),
                    "idempotency_key": "intentional-restart-fixture",
                    "request_hash": "fixture",
                },
            )
    # A new app lifespan reconciles interrupted jobs without silently re-running.
    with TestClient(app) as restarted:
        with tx() as c:
            check(
                "database_persists_restart",
                one(c, "SELECT count(*) n FROM predictions")["n"] == count,
            )
            check(
                "restart_interrupted_job_not_replayed",
                one(c, "SELECT status FROM jobs WHERE id=:i", {"i": abandoned})[
                    "status"
                ]
                == "interrupted",
            )
    after = {str(p.relative_to(APP.parent)): sha(p) for p in MODEL_SOURCES}
    check("original_model_and_data_unchanged", before == after)
    report = {
        "status": "passed",
        "scope": "real app import/training/evaluation/inference/restart acceptance; not a new model benchmark",
        "runtime": str(runtime.relative_to(APP)),
        "elapsed_seconds": time.monotonic() - started,
        "checks": checks,
        "jobs": job_reports,
        "original_source_hashes": after,
        "protected_holdout_scored": False,
        "model_execution": "actual subprocess, no test model mocks",
    }
except BaseException as error:
    report = {
        "status": "failed",
        "error": repr(error),
        "checks": checks,
        "jobs": job_reports,
        "runtime": str(runtime.relative_to(APP)),
        "elapsed_seconds": time.monotonic() - started,
        "protected_holdout_scored": False,
    }
    (OUT / "real-model-pipeline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    raise
else:
    (OUT / "real-model-pipeline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("jobs", "original_source_hashes")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
