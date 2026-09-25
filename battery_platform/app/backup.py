"""Local operator-only, quiescent backup/restore with integrity checks."""

from __future__ import annotations
import fcntl
import json
import shutil
import sqlite3
from pathlib import Path
from .config import APP_ROOT, RUNTIME
from .db import now
from .services import sha


def create_backup():
    lock = (RUNTIME / "worker.lock").open("a+")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "请先停止应用服务；备份要求数据库、附件和模型处于一致的静止状态"
            )
        destination = RUNTIME / "backups" / ("backup-" + now().replace(":", "-"))
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        source = sqlite3.connect(RUNTIME / "battery.db")
        target = sqlite3.connect(destination / "battery.db")
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        (destination / "battery.db").chmod(0o600)
        for name in ("attachments", "models", "jobs"):
            shutil.copytree(RUNTIME / name, destination / name)
        files = {
            str(p.relative_to(destination)): sha(p)
            for p in destination.rglob("*")
            if p.is_file()
        }
        manifest = {
            "schema": "huiguan-backup-v1",
            "created_at": now(),
            "original_runtime": str(RUNTIME),
            "files": files,
            "contains_private_records": True,
            "original_model_lab_included": False,
        }
        (destination / "backup-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        return destination
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def restore_backup(source: Path, destination: Path):
    source = source.resolve()
    destination = destination.resolve()
    allowed = (APP_ROOT / "runtime").resolve()
    if not source.is_relative_to(allowed) or not destination.is_relative_to(allowed):
        raise ValueError("只支持项目 runtime 内的本地备份和新的恢复目录")
    if destination.exists():
        raise ValueError("恢复目标必须是不存在的新目录；禁止覆盖当前数据")
    manifest = json.loads((source / "backup-manifest.json").read_text())
    if (
        manifest.get("schema") != "huiguan-backup-v1"
        or "battery.db" not in manifest["files"]
    ):
        raise ValueError("备份格式不匹配")
    for relative, digest in manifest["files"].items():
        path = source / relative
        if (
            not path.resolve().is_relative_to(source)
            or path.is_symlink()
            or not path.is_file()
            or sha(path) != digest
        ):
            raise ValueError("备份校验失败: " + relative)
    destination.mkdir(parents=True, mode=0o700)
    for relative in manifest["files"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    for name in ("attachments", "models", "jobs", "backups"):
        (destination / name).mkdir(exist_ok=True)
    connection = sqlite3.connect(destination / "battery.db")
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("恢复数据库完整性校验失败")
        original = Path(manifest["original_runtime"])
        for identifier, value in connection.execute(
            "SELECT id,artifact_path FROM models"
        ).fetchall():
            old = Path(value)
            if old.is_relative_to(original):
                connection.execute(
                    "UPDATE models SET artifact_path=? WHERE id=?",
                    (str(destination / old.relative_to(original)), identifier),
                )
        connection.execute("DELETE FROM sessions")
        connection.execute(
            "UPDATE jobs SET status='interrupted',finished_at=?,error='从备份恢复，未自动重放' WHERE status IN ('running','queued')",
            (now(),),
        )
        connection.commit()
    finally:
        connection.close()
    return {
        "runtime": str(destination),
        "all_sessions_revoked": True,
        "jobs_automatically_replayed": False,
    }
