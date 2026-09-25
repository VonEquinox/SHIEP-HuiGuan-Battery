from __future__ import annotations
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import create_engine, event, text
from .config import RUNTIME, prepare_runtime

prepare_runtime()
engine = create_engine(
    f'sqlite:///{RUNTIME / "battery.db"}',
    connect_args={"check_same_thread": False, "timeout": 15},
)


@event.listens_for(engine, "connect")
def configure(dbapi, _):
    dbapi.isolation_level = None
    cursor = dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def js(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def obj(value, default=None):
    return json.loads(value) if value else ({} if default is None else default)


@contextmanager
def tx():
    # Single-node writes are serialized, keeping multi-object workflow atomic.
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def execute(c, sql, values=None):
    return c.execute(text(sql), values or {})


def rows(c, sql, values=None):
    return [dict(r) for r in execute(c, sql, values).mappings()]


def one(c, sql, values=None):
    r = execute(c, sql, values).mappings().first()
    return dict(r) if r is not None else None


def insert(c, table, values):
    # table/column identifiers are always application constants, never request strings.
    columns = ",".join(values)
    bindings = ",".join(":" + k for k in values)
    return execute(
        c, f"INSERT INTO {table} ({columns}) VALUES ({bindings})", values
    ).lastrowid


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (key TEXT PRIMARY KEY, failures INTEGER NOT NULL, until_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS datasets (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, schema_id TEXT NOT NULL, source TEXT NOT NULL,
 source_hash TEXT NOT NULL UNIQUE, provenance TEXT NOT NULL, status TEXT NOT NULL,
 sample_count INTEGER NOT NULL, cell_count INTEGER NOT NULL, quality TEXT NOT NULL,
 created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS samples (
 id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES datasets(id),
 cell_id TEXT NOT NULL, sample_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
 current_json TEXT NOT NULL, reference_json TEXT NOT NULL, log_ratio REAL NOT NULL,
 truth REAL, batch TEXT, input_hash TEXT NOT NULL, UNIQUE(dataset_id,sample_key));
CREATE INDEX IF NOT EXISTS sample_cell ON samples(dataset_id,cell_id,ordinal);
CREATE TABLE IF NOT EXISTS assets (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, kind TEXT NOT NULL,
 parent_id INTEGER REFERENCES assets(id), provenance TEXT NOT NULL DEFAULT 'simulated',
 latitude REAL, longitude REAL, location TEXT NOT NULL DEFAULT '',
 installation_id TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bindings (
 asset_id INTEGER PRIMARY KEY REFERENCES assets(id), dataset_id INTEGER NOT NULL REFERENCES datasets(id),
 cell_id TEXT NOT NULL, scenario_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, schema_id TEXT NOT NULL,
 status TEXT NOT NULL, artifact_path TEXT NOT NULL, artifact_hash TEXT NOT NULL,
 dataset_id INTEGER REFERENCES datasets(id), train_cells TEXT NOT NULL,
 metrics TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
 result TEXT, error TEXT, progress INTEGER NOT NULL DEFAULT 0,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 started_at TEXT, finished_at TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
 idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 UNIQUE(created_by,idempotency_key));
CREATE TABLE IF NOT EXISTS job_logs (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), at TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS predictions (
 id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), model_id INTEGER NOT NULL REFERENCES models(id),
 sample_id INTEGER NOT NULL REFERENCES samples(id), asset_id INTEGER REFERENCES assets(id),
 installation_id TEXT, soh REAL NOT NULL, extra_trees_soh REAL, tabicl_soh REAL,
 outside_fraction REAL NOT NULL, applicability TEXT NOT NULL, input_hash TEXT NOT NULL,
 provenance TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,sample_id));
CREATE INDEX IF NOT EXISTS prediction_asset ON predictions(asset_id,id);
CREATE TABLE IF NOT EXISTS policies (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, threshold REAL NOT NULL, persistence INTEGER NOT NULL,
 cooldown_seconds INTEGER NOT NULL, stale_seconds INTEGER NOT NULL, active INTEGER NOT NULL,
 created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS health_events (
 id INTEGER PRIMARY KEY, prediction_id INTEGER REFERENCES predictions(id), asset_id INTEGER NOT NULL REFERENCES assets(id),
 policy_id INTEGER REFERENCES policies(id), installation_id TEXT NOT NULL, severity TEXT NOT NULL,
 reason TEXT NOT NULL, evidence TEXT NOT NULL, scenario_id TEXT, provenance TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(prediction_id,policy_id));
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES health_events(id), asset_id INTEGER NOT NULL REFERENCES assets(id),
 dedup_key TEXT NOT NULL, status TEXT NOT NULL, severity TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, occurrence_count INTEGER NOT NULL DEFAULT 1,
 version INTEGER NOT NULL DEFAULT 1);
CREATE UNIQUE INDEX IF NOT EXISTS alert_active_key ON alerts(dedup_key) WHERE status IN ('OPEN','ACKNOWLEDGED');
CREATE TABLE IF NOT EXISTS personnel (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
 skills TEXT NOT NULL, on_call INTEGER NOT NULL, latitude REAL, longitude REAL,
 max_workload INTEGER NOT NULL DEFAULT 4, provenance TEXT NOT NULL DEFAULT 'simulated', version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY, alert_id INTEGER NOT NULL UNIQUE REFERENCES alerts(id),
 asset_id INTEGER NOT NULL REFERENCES assets(id), title TEXT NOT NULL, status TEXT NOT NULL,
 assignee_id INTEGER REFERENCES users(id), required_skill TEXT NOT NULL DEFAULT 'battery',
 resolution TEXT, resolved_by INTEGER REFERENCES users(id), verified_by INTEGER REFERENCES users(id),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS order_events (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), from_status TEXT,
 to_status TEXT NOT NULL, actor_id INTEGER NOT NULL REFERENCES users(id), note TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attachments (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), file_name TEXT NOT NULL,
 storage_name TEXT NOT NULL UNIQUE, mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY, prediction_id INTEGER NOT NULL REFERENCES predictions(id),
 order_id INTEGER REFERENCES orders(id), value REAL NOT NULL, unit TEXT NOT NULL,
 provenance TEXT NOT NULL, source TEXT NOT NULL, measured_at TEXT NOT NULL, note TEXT NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 body TEXT NOT NULL, target TEXT NOT NULL, read_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 entity TEXT NOT NULL, entity_id TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def initialize():
    with tx() as c:
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                execute(c, statement)


def audit(c, actor, action, entity, entity_id, details=None):
    insert(
        c,
        "audit",
        {
            "actor_id": actor,
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id),
            "details": js(details or {}),
            "created_at": now(),
        },
    )


def notify(c, user_id, title, body, target):
    insert(
        c,
        "notifications",
        {
            "user_id": user_id,
            "title": title,
            "body": body,
            "target": target,
            "created_at": now(),
        },
    )
