"""Tests use a separate disposable database and no production credentials."""

from __future__ import annotations
import atexit
import os
import shutil
import tempfile
from pathlib import Path

test_runtime_root = Path(__file__).resolve().parents[1] / "runtime"
test_runtime_root.mkdir(parents=True, exist_ok=True)
os.environ["BATTERY_RUNTIME"] = tempfile.mkdtemp(prefix="test-api-", dir=str(test_runtime_root))
os.environ["BATTERY_DISABLE_WORKER"] = "1"
atexit.register(shutil.rmtree, os.environ["BATTERY_RUNTIME"], True)

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import tx, execute, initialize
from app.security import create_user

PASSWORD = "Test-only-valid-password-2047"


@pytest.fixture(autouse=True)
def clean_database():
    initialize()
    order = [
        "feedback",
        "attachments",
        "order_events",
        "orders",
        "notifications",
        "alerts",
        "health_events",
        "predictions",
        "job_logs",
        "jobs",
        "bindings",
        "personnel",
        "models",
        "samples",
        "datasets",
        "assets",
        "policies",
        "audit",
        "sessions",
        "login_attempts",
        "users",
    ]
    with tx() as c:
        execute(c, "PRAGMA defer_foreign_keys=ON")
        core_tables = set(order) | {"schema_version", "schema_migrations", "sqlite_sequence"}
        from app.db import rows
        extra_tables = rows(c, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        for table in extra_tables:
            if table["name"] not in core_tables:
                c.exec_driver_sql('DELETE FROM "' + table["name"].replace('"', '""') + '"')
        for table in order:
            execute(c, f"DELETE FROM {table}")
        if any(t["name"] == "dispatch_resources" for t in extra_tables):
            execute(c, "INSERT INTO dispatch_resources(id,payload,updated_at) VALUES(1,'{}','')")
        for role, name in [
            ("admin", "admin"),
            ("dispatcher", "dispatch"),
            ("technician", "tech"),
            ("technician", "othertech"),
            ("researcher", "research"),
            ("viewer", "viewer"),
        ]:
            create_user(c, name, name, PASSWORD, role)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def sign_in(client, username="admin"):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()


@pytest.fixture
def admin(client):
    sign_in(client)
    return client
