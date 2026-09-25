"""Deterministic test setup in an explicitly isolated runtime; no app defaults."""

from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
import json

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from app.config import RUNTIME, ML_PYTHON
from app.db import initialize, tx, one, insert, js, now
from app.security import create_user
from app.services import seed_demo, create_dataset, register_frozen, demo_bind

if not RUNTIME.name.startswith("browser-"):
    raise SystemExit(
        "Refuse test credentials outside an explicit browser-* test runtime"
    )
initialize()
PASSWORD = "Browser-test-only-password-2047"
with tx() as c:
    if one(c, "SELECT id FROM users LIMIT 1"):
        raise SystemExit("Use a new empty browser test runtime")
    ids = {}
    for name, label, role in [
        ("admin", "验收管理员", "admin"),
        ("tech", "验收维修员", "technician"),
        ("dispatch", "验收调度员", "dispatcher"),
        ("viewer", "验收观察员", "viewer"),
    ]:
        ids[name] = create_user(c, name, label, PASSWORD, role)
    insert(
        c,
        "personnel",
        {
            "user_id": ids["tech"],
            "skills": js(["battery", "inspection"]),
            "on_call": 1,
            "latitude": 31.051,
            "longitude": 121.801,
            "max_workload": 4,
        },
    )
    seed_demo(c, ids["admin"])
request = RUNTIME / "source-request.json"
result = RUNTIME / "source-result.json"
request.write_text(json.dumps({"action": "import_xjtu"}))
subprocess.run(
    [str(ML_PYTHON), str(APP / "ml_bridge.py"), str(request), str(result)],
    check=True,
    cwd=APP.parent,
    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    timeout=90,
)
with tx() as c:
    dataset = create_dataset(c, json.loads(result.read_text()), ids["admin"])
    demo_bind(c, dataset, ids["admin"])
    register_frozen(c, ids["admin"])
    # Test-only maintenance policy guarantees exercise of alert logic with real
    # predictions; it is not fitted to results or represented as a safety rule.
    insert(
        c,
        "policies",
        {
            "name": "自动化验收专用宽阈值（非业务标准）",
            "threshold": 1.5,
            "persistence": 1,
            "cooldown_seconds": 0,
            "stale_seconds": 86400,
            "active": 1,
            "created_by": ids["admin"],
            "created_at": now(),
        },
    )
print(
    "Browser fixture ready: actual2058 development rows, simulated assets/users; final holdouts excluded."
)
