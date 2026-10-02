"""Prediction and dataset contracts with explicit domain, time, and target support."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import numpy as np

SCHEMA = "battery_features_v2"
# Historical packages retain SCHEMA. Temperature-aware views have a distinct
# input contract and require newly trained models, even when statistics are 30D.
CHANNEL_VALIDITY_SCHEMA = "battery_features_v2_channel_validity_1"
FEATURE_SCHEMAS = frozenset({SCHEMA, CHANNEL_VALIDITY_SCHEMA})
PREDICTION_SCHEMA = "battery_prediction_v2"
PROTECTED_XJTU = frozenset({"Batch-4/R3_battery-5", "Batch-5/RW_battery-5", "Batch-6/Sim_satellite_battery-5"})
HEADS = ("soh", "rul", "threshold_risk", "efficiency", "fault")


def domain_key(row: dict) -> str:
    return "::".join(str(row.get(k)) for k in ("source_id", "chemistry", "protocol_id"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def unsupported_profile(query: dict, reason: str, model_version: str = "unavailable") -> dict:
    return {"schema_version": PREDICTION_SCHEMA, "model_version": model_version,
            "data_namespace": query.get("data_namespace", "experimental"), "query": query,
            "support": {"status": "unsupported", "reasons": [reason], "ood_score": None},
            "heads": {k: {"support": "unsupported", "reason": reason, "target_definition": None,
                         "unit": None, "horizon": None, "distribution_kind": None,
                         "calibration_version": None, "evidence_refs": []} for k in HEADS}}


def check_query(query: dict, support_domains: list[dict], *, feature_schema: str = SCHEMA) -> list[str]:
    reasons = []
    if query.get("source_id") == "xjtu" and str(query.get("physical_cell_id", "")).endswith("-5"):
        reasons.append("protected_xjtu_cell")
    if feature_schema not in FEATURE_SCHEMAS or query.get("feature_schema") != feature_schema:
        reasons.append("feature_schema_mismatch")
    if query.get("data_namespace") not in ("experimental", "demo_synthetic"):
        reasons.append("missing_or_invalid_namespace")
    if query.get("visible_cutoff") is None or query.get("query_time") is None:
        reasons.append("missing_time_boundary")
    elif query["visible_cutoff"] > query["query_time"]:
        reasons.append("visible_cutoff_after_query")
    for key in ("source_id", "chemistry", "protocol_id", "physical_cell_id"):
        if not query.get(key):
            reasons.append(f"missing_{key}")
    if not any(all(query.get(k) == d.get(k) for k in ("source_id", "chemistry", "protocol_id")) for d in support_domains):
        reasons.append("unsupported_source_chemistry_protocol")
    if not set(query.get("allowed_heads", HEADS)).issubset(HEADS):
        reasons.append("invalid_head")
    if query.get("operating_scenario_id") is None and query.get("horizon_unit") == "day":
        reasons.append("calendar_horizon_requires_operating_scenario")
    return reasons


def validate_temperature_stat_domains(domains: dict, temperature_domains: list) -> None:
    """Reject incomplete new-feature metadata before fitting or prediction."""
    if (not isinstance(domains, dict) or not domains
            or any(not isinstance(key, str) or type(index) is not int or index < 0 for key, index in domains.items())
            or len(set(domains.values())) != len(domains)):
        raise ValueError("temperature-statistics domain mapping must use unique nonnegative integer IDs")
    if (not isinstance(temperature_domains, list)
            or any(type(index) is not int for index in temperature_domains)
            or len(set(temperature_domains)) != len(temperature_domains)
            or not set(temperature_domains).issubset(domains.values())):
        raise ValueError("temperature_stat_domains is required and must contain unique registered integer IDs")
    # Prefix views use temperature summaries even when their curve is wholly
    # absent. Only DYAD's native statistics have different column meanings.
    expected = {index for key, index in domains.items() if key.split("::", 1)[0] != "dyad"}
    if set(temperature_domains) != expected:
        raise ValueError("temperature_stat_domains must cover all prefix-view domains and exclude native DYAD statistics")


def validate_training_manifest(manifest: dict) -> None:
    """Validate before loading arrays; no future/heldout rows may become development inputs."""
    if manifest.get("schema_version") not in FEATURE_SCHEMAS:
        raise ValueError("unsupported dataset schema")
    if manifest.get("data_namespace") not in ("experimental", "demo_synthetic"):
        raise ValueError("namespace required")
    if manifest["schema_version"] == CHANNEL_VALIDITY_SCHEMA:
        validate_temperature_stat_domains(manifest.get("domains"), manifest.get("temperature_stat_domains"))
    memberships: dict[str, str] = {}
    for row in manifest["rows"]:
        cell, split = row["physical_cell_id"], row["split"]
        if row.get("source_id") == "xjtu" and (cell in PROTECTED_XJTU or cell.endswith("-5")):
            raise ValueError("protected XJTU cells are forbidden in V2 development")
        if split not in ("train", "dev", "calibration", "final"):
            raise ValueError("invalid split")
        if cell in memberships and memberships[cell] != split:
            raise ValueError("physical object crosses split")
        memberships[cell] = split
        for key in ("available_at", "reference_cutoff", "feature_max_time"):
            if row.get(key) is not None and row[key] > row["visible_cutoff"]:
                raise ValueError(f"future {key} exceeds visible cutoff")
        if row["visible_cutoff"] > row["query_time"]:
            raise ValueError("visible cutoff after query")
        if row.get("survival_time_unit") == "ordinal":
            raise ValueError("ordinal is not a physical RUL time unit")
    if "train" not in memberships.values():
        raise ValueError("training objects required")


def load_dataset(manifest_path: str | Path) -> tuple[dict, dict[str, np.ndarray]]:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    validate_training_manifest(manifest)
    arrays_path = path.parent / manifest["arrays_file"]
    if sha256_file(arrays_path) != manifest["arrays_sha256"]:
        raise ValueError("dataset array hash mismatch")
    with np.load(arrays_path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    if any(len(v) != len(manifest["rows"]) for v in arrays.values()):
        raise ValueError("array/manifest row count mismatch")
    if not np.isfinite(arrays["features"]).all():
        raise ValueError("features must use missing masks and finite values")
    if manifest["schema_version"] == CHANNEL_VALIDITY_SCHEMA:
        sequence, mask = arrays["sequences"], arrays["sequence_mask"]
        if sequence.ndim != 4 or sequence.shape[-1] != 6 or mask.shape != sequence.shape[:-1]:
            raise ValueError("channel-validity sequences require six channels and matching point masks")
        if not np.isfinite(sequence).all() or not np.isfinite(mask).all() or not np.isin(mask, [0, 1]).all():
            raise ValueError("sequence values must be finite and point masks binary")
        temperature_valid = sequence[..., 5]
        if not np.isin(temperature_valid, [0, 1]).all() or np.any(temperature_valid > mask):
            raise ValueError("temperature validity must be binary and bounded by point validity")
        if np.any(sequence[..., 2][temperature_valid == 0] != 0):
            raise ValueError("unobserved temperature must have a neutral fill and explicit missing validity")
    for task in ("soh", "efficiency"):
        y = arrays[f"y_{task}"]
        finite = np.isfinite(y)
        if np.any(y[finite] <= 0) or (task == "efficiency" and np.any(y[finite] > 1)):
            raise ValueError(f"invalid {task} target")
    if not set(np.unique(arrays["y_fault"])).issubset({-1, 0, 1}):
        raise ValueError("fault head requires explicit binary label mapping")
    if not set(np.unique(arrays["survival_kind"])).issubset({-1, 0, 1, 2}):
        raise ValueError("invalid survival censor type")
    intervals = arrays["survival_kind"] == 2
    if np.any(arrays["survival_upper"][intervals] <= arrays["survival_lower"][intervals]):
        raise ValueError("empty interval-censored target")
    return manifest, arrays
