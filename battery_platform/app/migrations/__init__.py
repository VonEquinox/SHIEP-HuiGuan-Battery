"""Ordered additive SQLite upgrades with pre-upgrade backups and checksums."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..db import engine, execute, rows, tx
from ..config import RUNTIME


def _statements(source: str):
    pending = ""
    for line in source.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip() and not all(
        not line.strip() or line.lstrip().startswith("--") for line in pending.splitlines()
    ):
        raise ValueError("Migration has incomplete SQL")


def migrate(directory=None):
    directory = Path(directory) if directory is not None else Path(__file__).parent
    scripts = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    with tx() as c:
        execute(c, """CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL,
          applied_at TEXT NOT NULL, backup_path TEXT NOT NULL)""")
        applied = {item["version"]: item for item in rows(c, "SELECT * FROM schema_migrations")}
    pending = []
    versions = set()
    for script in scripts:
        version = int(script.name.split("_", 1)[0])
        if version in versions:
            raise RuntimeError(f"Duplicate migration version: {version}")
        versions.add(version)
        checksum = hashlib.sha256(script.read_bytes()).hexdigest()
        if version in applied:
            if applied[version]["sha256"] != checksum:
                raise RuntimeError(f"Applied migration was modified: {script.name}")
        else:
            if applied and version < max(applied):
                raise RuntimeError("Cannot insert a migration before an applied version")
            pending.append((version, script, checksum))
    if not pending:
        return []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = RUNTIME / "backups" / f"pre-v2-migration-{stamp}.sqlite"
    with sqlite3.connect(engine.url.database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Pre-migration backup failed integrity check")
    backup.chmod(0o600)
    # The entire pending chain commits together or rolls back together.
    with tx() as c:
        for version, script, checksum in pending:
            for statement in _statements(script.read_text(encoding="utf-8")):
                execute(c, statement)
            execute(c, """INSERT INTO schema_migrations
              (version,filename,sha256,applied_at,backup_path) VALUES (:v,:f,:h,:t,:b)""",
                {"v": version, "f": script.name, "h": checksum,
                 "t": datetime.now(timezone.utc).isoformat(), "b": str(backup)})
            foreign_errors = c.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if foreign_errors:
                raise RuntimeError("Migration violated foreign key integrity")
    return [script.name for _, script, _ in pending]
