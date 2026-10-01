"""Small dependency-free serialization helpers for the content pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "battery-content-v1"
TOOL_WHITELIST = frozenset({
    "get_asset_context", "get_signal_evidence", "read_prediction",
    "get_peer_anomalies", "search_knowledge", "load_skill", "search_memory",
    "rank_tests", "propose_work_order", "append_report",
})


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def opaque_id(prefix: str, identity: str) -> str:
    return prefix + "-" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
