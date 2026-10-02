"""MATR physical-cycle prefix views with source-preserving remaining-life labels.

This adapter consumes already qualified V2 numeric tables. It does not qualify
raw MATLAB identities, fit a model, or release a final-test split.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .contracts import CHANNEL_VALIDITY_SCHEMA, domain_key, sha256_file, validate_training_manifest
from .features import FEATURE_NAMES, HISTORY_FEATURES, SEQUENCE_CHANNELS, segment_view, statistical_view, values

DEFAULT_QUERY_PREFIXES = (50, 100, 200)
SOH_DEFINITION = "matr-physical-cycle-first-valid-at-or-after10-reference-soh-v2"
DEVELOPMENT_SPLITS = frozenset({"train", "dev", "calibration"})
BARCODE_IDENTITY_BASES = frozenset({
    "verified_original_identity", "official_original_barcode",
    "original_official_cellId_barcode", "verified_original_barcode",
    "audited_full_trajectory_barcode", "original_corrected_mat_barcode",
})


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _true(value: Any) -> bool:
    return isinstance(value, (bool, np.bool_)) and bool(value)


def validate_prefix_configuration(query_prefixes, history: int, points: int) -> tuple[int, ...]:
    """Validate the fixed query grid without opening any source table."""
    supplied = tuple(query_prefixes)
    if not supplied or any(isinstance(q, (bool, np.bool_)) or _number(q) is None
                           or float(q) != int(float(q)) or float(q) <= 10 for q in supplied):
        raise ValueError("query prefixes must be integer physical cycles greater than 10")
    queries = tuple(int(q) for q in supplied)
    if tuple(sorted(set(queries))) != queries:
        raise ValueError("query prefixes must be unique and strictly increasing")
    if isinstance(history, bool) or not isinstance(history, int) or not 1 <= history <= 32:
        raise ValueError("history must be an integer in [1, 32]")
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 256:
        raise ValueError("points must be an integer in [2, 256]")
    return queries


def _assignments(split: dict) -> dict[str, str]:
    assignments = dict(split.get("assignments", split.get("memberships", {})))
    if not assignments:
        for name, identities in split.get("splits", {}).items():
            for cell in identities:
                if cell in assignments and assignments[cell] != name:
                    raise ValueError("frozen split contains a repeated physical identity")
                assignments[cell] = name
    return {cell: "final" if name == "final-test" else name for cell, name in assignments.items()}


def _prior_final_identities(path: str | Path | None) -> tuple[set[str], dict | None]:
    """Read prior identity/split JSON metadata only, never its array file."""
    if path is None:
        return set(), None
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ValueError("prior final identity exclusions require JSON metadata, not numerical arrays")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    identities = set()
    if "rows" in metadata:
        if not isinstance(metadata["rows"], list):
            raise ValueError("prior identity manifest rows must be a list")
        for row in metadata["rows"]:
            if not isinstance(row, dict):
                raise ValueError("invalid prior identity row")
            if row.get("split") in {"final", "final-test"} and row.get("source_id") == "matr":
                cell = _text(row.get("physical_cell_id"))
                if cell is None or not cell.casefold().startswith("matr:"):
                    raise ValueError("prior final MATR identity is missing a canonical barcode namespace")
                identities.add(cell.casefold())
    elif any(key in metadata for key in ("assignments", "memberships", "splits")):
        identities = {cell.casefold() for cell, name in _assignments(metadata).items()
                      if name == "final" and cell.casefold().startswith("matr:")}
    else:
        raise ValueError("prior exclusion metadata requires feature rows or frozen split assignments")
    return identities, {"manifest_sha256": sha256_file(path), "physical_cell_ids": sorted(identities),
                        "prior_final_identity_count": len(identities), "identity_matching": "MATR barcode namespace casefold", "numerical_arrays_opened": False}


def _qualified_identity(identity: dict) -> bool:
    if identity.get("source_id") != "matr" or identity.get("namespace", "experimental") != "experimental":
        return False
    cell = _text(identity.get("physical_cell_id"))
    if not cell or not cell.startswith("matr:") or "channel-" in cell:
        return False
    # A batch/channel index or file metadata is insufficient. The recognized
    # basis is an assertion made by the upstream barcode qualification step.
    if identity.get("identity_basis") not in BARCODE_IDENTITY_BASES:
        return False
    if identity.get("identity_basis") == "original_corrected_mat_barcode" and not _true(identity.get("identity_verified")):
        return False
    if identity.get("identity_verified") is not None and not _true(identity["identity_verified"]):
        return False
    if _text(identity.get("chemistry")) is None:
        return False
    return _text(identity.get("source_protocol_id")) is not None or _text(identity.get("protocol_id")) is not None


def _read_admitted_table(path: Path, cells: list[str], allowed_columns: tuple[str, ...]) -> pd.DataFrame:
    """Project allowed fields and filter IDs before returning numerical rows.

    The Parquet footer is schema metadata. Arrow may scan a shared row group
    internally; excluded rows are never returned to the feature adapter. No
    hash over a combined numerical table is recomputed.
    """
    if not path.exists():
        return pd.DataFrame()
    names = set(pq.ParquetFile(path).schema_arrow.names)
    if "physical_cell_id" not in names:
        if not names:
            return pd.DataFrame()
        raise ValueError(f"{path.name} lacks physical_cell_id")
    return pd.read_parquet(path, columns=[column for column in allowed_columns if column in names],
                           filters=[("physical_cell_id", "in", cells)])


def remaining_survival_target(target: dict, query: float) -> tuple[int, float, float, str | None]:
    """Convert an absolute physical-cycle outcome to remaining cycles.

    The interval convention is lower < T <= upper. A non-null reason excludes
    the query because survival at that query cannot be established, or because
    the source definition cannot be interpreted safely.
    """
    if target.get("label_status") != "available":
        return -1, 0., 0., "survival_label_unavailable"
    if target.get("unit") != "cycle":
        return -1, 0., 0., "survival_unit_not_verified_physical_cycle"
    if not _text(target.get("target_definition_id")):
        return -1, 0., 0., "missing_source_survival_definition"
    threshold = _number(target.get("threshold_Ah"))
    if threshold is None or threshold <= 0 or target.get("threshold_operator") not in {
        "strictly_less_than", "less_than_or_equal",
    }:
        return -1, 0., 0., "missing_or_invalid_threshold_contract"
    lower, upper = _number(target.get("lower_event_bound")), _number(target.get("upper_event_bound"))
    if lower is None or lower < 0:
        return -1, 0., 0., "invalid_survival_lower_bound"
    censor = target.get("censor_type")
    if censor == "right":
        if upper is not None or _true(target.get("event")):
            return -1, 0., 0., "invalid_right_censor_contract"
        if lower < query:
            return -1, 0., 0., "right_censor_before_query_alive_status_unknown"
        return 0, lower - query, 0., None
    if censor not in {"exact", "interval"} or upper is None or not _true(target.get("event")):
        return -1, 0., 0., "invalid_event_contract"
    if upper <= query:
        return -1, 0., 0., "event_already_occurred_at_query"
    if censor == "exact":
        if lower != upper:
            return -1, 0., 0., "invalid_exact_event_bounds"
        return 1, upper - query, upper - query, None
    if upper <= lower:
        return -1, 0., 0., "empty_event_interval"
    if lower < query:
        return -1, 0., 0., "event_interval_straddles_query_alive_status_unknown"
    return 2, lower - query, upper - query, None


def _remaining_definition(target: dict) -> str:
    threshold = float(target["threshold_Ah"])
    return (f"{target['target_definition_id']}::threshold_Ah={threshold:.17g}"
            f"::operator={target['threshold_operator']}::remaining_physical_cycles_at_query")


def build_lifetime_feature_bundle(derived_dir, out_dir, *, query_prefixes=DEFAULT_QUERY_PREFIXES,
                                  history: int = 32, points: int = 256,
                                  exclude_identity_manifest: str | Path | None = None) -> dict:
    """Build immutable development-only MATR views; no fitting or final release."""
    queries = validate_prefix_configuration(query_prefixes, history, points)
    directory, out = Path(derived_dir), Path(out_dir)
    if out.exists():
        raise FileExistsError("lifetime feature output must be a new directory")
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    identity_path, split_path = directory / "identity_map.parquet", directory / "split_manifest.json"
    identity = pd.read_parquet(identity_path)
    split = json.loads(split_path.read_text(encoding="utf-8"))
    assignments = _assignments(split)
    previously_consumed_final_ids, prior_exclusions = _prior_final_identities(exclude_identity_manifest)
    if "physical_cell_id" not in identity or identity.physical_cell_id.duplicated().any():
        raise ValueError("physical identities must be present and unique before lifetime views")
    exclusions: list[dict] = []
    admitted: list[dict] = []
    for record in identity.to_dict("records"):
        cell = record["physical_cell_id"]
        split_name = assignments.get(cell)
        if split_name is None:
            raise ValueError(f"identity lacks a frozen split assignment: {cell}")
        if split_name not in DEVELOPMENT_SPLITS:
            exclusions.append({"physical_cell_id": cell, "reason": "non_development_split_excluded_before_numeric_read", "split": split_name})
            continue
        if str(cell).casefold() in previously_consumed_final_ids:
            exclusions.append({"physical_cell_id": cell, "reason": "previously_consumed_final_identity", "split": split_name})
            continue
        if not _qualified_identity(record):
            exclusions.append({"physical_cell_id": cell, "reason": "unqualified_matr_barcode_identity"})
            continue
        record["split"] = split_name
        record["protocol_id"] = _text(record.get("source_protocol_id")) or record["protocol_id"]
        admitted.append(record)
    if not admitted:
        raise ValueError("no qualified development MATR identities; no numerical table was read")
    cells = [record["physical_cell_id"] for record in admitted]
    cycles = _read_admitted_table(directory / "cycles.parquet", cells, (
        "physical_cell_id", "source_id", "cycle_index", "physical_cycles_known", "capacity_Ah",
        "observed_at", "available_at", "protocol_id", "source_protocol_id", "diagnostic", "raw_ref",
    ))
    segments = _read_admitted_table(directory / "segments.parquet", cells, (
        "physical_cell_id", "source_id", "cycle_index", "physical_cycles_known", "observed_at", "available_at",
        "protocol_id", "source_protocol_id", "voltage_V", "current_A", "temperature_C", "time_s", "relative_time_s", "raw_ref",
    ))
    targets = _read_admitted_table(directory / "targets.parquet", cells, (
        "physical_cell_id", "source_id", "target_name", "target_definition_id", "unit", "label_status", "censor_type",
        "event", "lower_event_bound", "upper_event_bound", "observed_at", "available_at", "threshold_Ah", "threshold_operator",
    ))
    rows, features, sequences, masks, labels, outcomes = [], [], [], [], [], []
    definitions: dict[str, dict] = {}
    for record in admitted:
        cell = record["physical_cell_id"]
        cc = cycles[cycles.physical_cell_id.eq(cell)].sort_values("cycle_index") if "physical_cell_id" in cycles else pd.DataFrame()
        reason = None
        if cc.empty or "physical_cycles_known" not in cc or not cc.physical_cycles_known.map(_true).all():
            reason = "source_ordinal_is_not_verified_physical_cycle"
        elif cc.cycle_index.duplicated().any() or not np.isfinite(cc.cycle_index).all() or (cc.cycle_index <= 0).any() or not (cc.cycle_index == np.floor(cc.cycle_index)).all():
            reason = "physical_cycle_numbers_not_unique_positive_integers"
        for protocol_column in ("source_protocol_id", "protocol_id"):
            if reason is None and protocol_column in cc:
                protocols = set(cc[protocol_column].dropna())
                if protocols and protocols != {record["protocol_id"]}:
                    reason = "cycle_protocol_differs_from_exact_identity_policy"
        if reason:
            exclusions.append({"physical_cell_id": cell, "reason": reason})
            continue
        for column in ("observed_at", "available_at"):
            if column not in cc:
                cc[column] = cc.cycle_index
        valid = cc[np.isfinite(cc.capacity_Ah) & cc.capacity_Ah.gt(0)]
        references = valid[valid.cycle_index.ge(10)]
        if references.empty:
            exclusions.append({"physical_cell_id": cell, "reason": "no_valid_physical_cycle10_reference"})
            continue
        reference_row = references.iloc[0]
        reference, reference_cycle = float(reference_row.capacity_Ah), float(reference_row.cycle_index)
        st = targets[targets.physical_cell_id.eq(cell) & targets.target_name.eq("rul")] if {"physical_cell_id", "target_name"}.issubset(targets.columns) else pd.DataFrame()
        if len(st) != 1:
            exclusions.append({"physical_cell_id": cell, "reason": "one_source_survival_definition_per_identity_required"})
            continue
        survival = st.iloc[0].to_dict()
        ss = segments[segments.physical_cell_id.eq(cell)].sort_values("cycle_index", kind="stable") if {"physical_cell_id", "cycle_index"}.issubset(segments.columns) else pd.DataFrame()
        nominal = _number(record.get("nominal_capacity_Ah"))
        nominal = nominal if nominal and nominal > 0 else None
        for query in queries:
            kind, lower, upper, reason = remaining_survival_target(survival, query)
            if reason:
                exclusions.append({"physical_cell_id": cell, "query_time": query, "reason": reason})
                continue
            cutoff = query - 1
            if (reference_cycle > cutoff or _number(reference_row.available_at) is None
                    or _number(reference_row.observed_at) is None or reference_row.available_at > cutoff
                    or reference_row.observed_at > cutoff):
                exclusions.append({"physical_cell_id": cell, "query_time": query, "reason": "frozen_reference_not_visible_before_query"})
                continue
            visible = valid[valid.cycle_index.le(cutoff) & valid.observed_at.le(cutoff) & valid.available_at.le(cutoff)].tail(history)
            if visible.empty:
                exclusions.append({"physical_cell_id": cell, "query_time": query, "reason": "no_visible_physical_capacity_history"})
                continue
            prior = ss[ss.cycle_index.le(cutoff)].copy() if not ss.empty else pd.DataFrame()
            for column in ("observed_at", "available_at"):
                if not prior.empty and column in prior:
                    prior = prior[prior[column].le(cutoff)]
            for protocol_column in ("source_protocol_id", "protocol_id"):
                if not prior.empty and protocol_column in prior:
                    prior = prior[prior[protocol_column].isna() | prior[protocol_column].eq(record["protocol_id"])]
            prior = prior.tail(history)
            sequence = np.zeros((history, points, len(SEQUENCE_CHANNELS)), np.float32)
            mask = np.zeros((history, points), np.float32)
            for j, segment in enumerate(prior.to_dict("records"), start=history - len(prior)):
                sequence[j], mask[j] = segment_view(segment, points, nominal)
            feature = statistical_view(sequence[-1], mask[-1], visible, reference, nominal)
            if not prior.empty:
                time = values(prior.iloc[-1].to_dict(), "time_s", "relative_time_s")
                if len(time) > 1 and np.isfinite(time).all() and np.all(np.diff(time) > 0):
                    feature[8] = float(time[-1] - time[0])
            exact = valid[valid.cycle_index.eq(query)]
            soh = float(exact.iloc[0].capacity_Ah) / reference if len(exact) == 1 else np.nan
            key = domain_key(record)
            defs = {"soh": SOH_DEFINITION, "rul": _remaining_definition(survival), "efficiency": None, "fault": None}
            if key in definitions and definitions[key] != defs:
                raise ValueError("one exact policy domain cannot mix different survival threshold definitions")
            definitions[key] = defs
            feature_max = max(float(visible.cycle_index.max()), float(prior.cycle_index.max()) if not prior.empty else 0.)
            rows.append({"source_id": "matr", "physical_cell_id": cell, "split": record["split"],
                         "chemistry": record.get("chemistry"), "protocol_id": record["protocol_id"],
                         "source_protocol_id": record["protocol_id"], "query_time": query, "visible_cutoff": cutoff,
                         "feature_max_time": feature_max, "available_at": cutoff,
                         "time_basis": "verified_physical_cycle", "physical_cycles_known": True,
                         "reference_cutoff": reference_cycle, "reference_capacity_Ah": reference,
                         "target_definition": SOH_DEFINITION, "unit": "ratio", "survival_time_unit": "cycle",
                         "target_observed_at": query if np.isfinite(soh) else None,
                         "target_available_at": float(exact.iloc[0].available_at) if np.isfinite(soh) else None,
                         "survival_target_definition_id": defs["rul"], "source_survival_target_definition_id": survival["target_definition_id"],
                         "survival_threshold_Ah": float(survival["threshold_Ah"]), "survival_threshold_operator": survival["threshold_operator"],
                         "survival_censor_type": survival["censor_type"],
                         "survival_label_observed_at": _number(survival.get("observed_at")),
                         "survival_label_available_at": _number(survival.get("available_at")),
                         "identity_basis": record["identity_basis"],
                         "evidence_refs": list(dict.fromkeys(visible.get("raw_ref", pd.Series(dtype=str)).dropna().astype(str).tolist()
                                                             + prior.get("raw_ref", pd.Series(dtype=str)).dropna().astype(str).tolist()))})
            features.append(feature); sequences.append(sequence); masks.append(mask); labels.append(soh); outcomes.append((kind, lower, upper))
    if not rows:
        raise ValueError("no qualified alive-at-query physical lifetime views")
    domains = {key: index for index, key in enumerate(sorted({domain_key(row) for row in rows}))}
    for row in rows:
        row["domain_index"] = domains[domain_key(row)]
    n = len(rows)
    outcomes_array = np.asarray(outcomes, dtype=np.float32)
    history_mask = np.zeros((n, 2 * len(FEATURE_NAMES)), np.float32)
    history_mask[:, HISTORY_FEATURES] = 1
    arrays = {"features": np.stack(features), "sequences": np.stack(sequences), "sequence_mask": np.stack(masks),
              "domain": np.asarray([row["domain_index"] for row in rows], np.int64), "y_soh": np.asarray(labels, np.float32),
              "y_efficiency": np.full(n, np.nan, np.float32), "y_fault": np.full(n, -1, np.float32),
              "survival_kind": outcomes_array[:, 0], "survival_lower": outcomes_array[:, 1], "survival_upper": outcomes_array[:, 2],
              "history_feature_mask": history_mask}
    source_manifest_path = directory / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8")) if source_manifest_path.exists() else {}
    all_rul_defs = {defs["rul"] for defs in definitions.values()}
    manifest = {"schema_version": CHANNEL_VALIDITY_SCHEMA, "data_namespace": "experimental", "data_version": "v2-matr-physical-lifetime-prefix-channel-validity-2",
                "arrays_file": "features.npz", "rows": rows, "feature_names": FEATURE_NAMES + [f"missing_{name}" for name in FEATURE_NAMES],
                "sequence_channels": SEQUENCE_CHANNELS,
                "temperature_stat_domains": list(domains.values()),
                "domains": domains, "history_limit": history, "points": points,
                "target_definitions": {"soh": SOH_DEFINITION, "rul": next(iter(all_rul_defs)) if len(all_rul_defs) == 1 else "source_policy_specific_remaining_physical_cycle_survival_v2", "efficiency": None, "fault": None},
                "target_definitions_by_domain": definitions,
                "query_prefixes": list(queries), "input_visibility": "strictly_before_query", "reference_policy": "first_valid_capacity_at_or_after_physical_cycle10_frozen_before_query",
                "development_only": True, "final_rows_loaded_into_feature_adapter": False, "split_assignments_preserved": True,
                "numeric_read_boundary": "Parquet ID filter and permitted column projection; excluded rows never returned; storage row-group decoding is reader-managed",
                "split_sha256": sha256_file(split_path), "identity_map_sha256": sha256_file(identity_path),
                "source_parsed_manifest_sha256": sha256_file(source_manifest_path) if source_manifest_path.exists() else None,
                "source_table_sha256_recorded_not_recomputed": {name: table.get("sha256") for name, table in source_manifest.get("tables", {}).items()},
                "prior_final_identity_exclusions": prior_exclusions,
                "excluded_rows": exclusions, "exclusion_counts": dict(Counter(row["reason"] for row in exclusions)),
                "censor_counts": {name: sum(kind == code for kind, _, _ in outcomes) for name, code in (("right", 0), ("exact", 1), ("interval", 2))},
                "missing_heads": {"efficiency": "unverified equal SOC and metering boundary", "fault": "no confirmed source fault label"},
                "capability_status": "candidate_feature_adapter_requires_independent_development_validation"}
    validate_training_manifest(manifest)
    out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(out / "features.npz", **arrays)
    manifest["arrays_sha256"] = sha256_file(out / "features.npz")
    (out / "features.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest
