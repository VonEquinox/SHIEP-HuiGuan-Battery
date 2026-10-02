"""Audit admitted temperature channels and rebuild immutable F01 development views.

Identity/split metadata is read first. Numerical parquet rows are filtered by
physical identity before entering Python; protected and historically exposed
final identities are excluded even if another source calls them training.
No previous source, feature artifact, model weight, or metric is overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from model_lab.modeling.v2.contracts import sha256_file
from model_lab.modeling.v2.features import build_feature_bundle, combine_feature_bundles, segment_view, values


ROOT = Path(__file__).resolve().parents[2]
DERIVED = ROOT / "model_lab/data/derived/v2"
OUT = ROOT / "battery_platform/research/f01_channel_validity_20261002_qualified"
ALLOWED = {"train", "dev", "calibration"}
SOURCES = {
    "xjtu_prefix": "xjtu_final_20261002",
    "matr_summary_prefix": "matr_official_summary_20261002",
    "matr_corrected_curves": "matr_corrected_development_20261002",
    "matr_arbin_curve": "matr_arbin_cell_20261002",
    "ch_statistics": "ch_batterygen_20261002",
    "dyad_statistics": "dyad_brand3_20261002",
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def historical_final_identities():
    result = set()
    for source in ("xjtu_final_20261002", "matr_official_summary_20261002"):
        split = json.loads((DERIVED / source / "split_manifest.json").read_text())
        result.update(cell.casefold() for cell, name in split["assignments"].items()
                      if name in {"final", "final-test", "sealed", "protected"})
    return result


def admitted(source):
    directory = DERIVED / source
    split = json.loads((directory / "split_manifest.json").read_text())
    identity = pd.read_parquet(directory / "identity_map.parquet")
    assignments = split["assignments"]
    exposed = historical_final_identities()
    cells, exclusions = [], []
    for cell in identity.physical_cell_id.unique():
        name = assignments.get(cell)
        reason = None
        if str(cell).casefold() in exposed:
            reason = "historically_exposed_final_identity"
        elif str(cell).startswith("xjtu:") and str(cell).endswith("-5"):
            reason = "protected_xjtu_identity"
        elif name not in ALLOWED:
            reason = "not_development_split"
        if reason:
            exclusions.append({"physical_cell_id": cell, "split": name, "reason": reason})
        else:
            cells.append(cell)
    return directory, identity[identity.physical_cell_id.isin(cells)].copy(), cells, assignments, exclusions


def read_filtered(directory, table, cells):
    return pd.read_parquet(directory / table, filters=[("physical_cell_id", "in", cells)])


def audit_source(name, source):
    directory, identity, cells, assignments, exclusions = admitted(source)
    segments = read_filtered(directory, "segments.parquet", cells)
    counters = Counter()
    point_counts = Counter()
    cells_with_trigger = set()
    for row in segments.to_dict("records"):
        counters["segments"] += 1
        v, i, t = values(row, "voltage_V"), values(row, "current_A"), values(row, "time_s", "relative_time_s")
        n = min(len(v), len(i), len(t))
        temp = values(row, "temperature_C")
        if n < 2:
            counters["no_qualified_curve"] += 1
            continue
        counters["curve_segments"] += 1
        base_valid = np.isfinite(v[:n]) & np.isfinite(i[:n]) & np.isfinite(t[:n])
        prefix = np.full(n, np.nan)
        prefix[:min(n, len(temp))] = temp[:n]
        qualified = np.isfinite(prefix) & base_valid
        usable = base_valid.sum()
        point_counts["base_valid_points"] += int(usable)
        point_counts["temperature_valid_points"] += int(qualified.sum())
        point_counts["temperature_missing_points"] += int((base_valid & ~np.isfinite(prefix)).sum())
        point_counts["real_zero_temperature_points"] += int((qualified & (prefix == 0)).sum())
        counters["missing_array"] += int(len(temp) == 0)
        counters["short_array"] += int(0 < len(temp) < n)
        counters["all_nan_array"] += int(len(temp) >= n and not np.isfinite(temp[:n]).any())
        counters["partial_nonfinite_array"] += int(len(temp) >= n and np.isfinite(temp[:n]).any() and not np.isfinite(temp[:n]).all())
        counters["real_all_zero_array"] += int(usable > 0 and qualified.sum() == usable and np.all(prefix[base_valid] == 0))
        # This is the exact pre-fix trigger: otherwise valid V/I/time with a
        # missing/short/partially nonfinite temperature channel became 0C.
        pre_fix_trigger = usable >= 2 and (len(temp) < n or not np.isfinite(prefix[base_valid]).all())
        counters["pre_fix_trigger_segments"] += int(pre_fix_trigger)
        if pre_fix_trigger:
            cells_with_trigger.add(row["physical_cell_id"])
        sequence, mask = segment_view(row)
        if mask.sum() == 0:
            counters["curve_rejected_time_or_finite_basis"] += 1
        elif sequence.shape[-1] == 6:
            counters["new_view_temperature_missing"] += int(np.any(sequence[mask > 0, 5] == 0))
    count = counters["curve_segments"]
    rates = {key: (counters[key] / count if count else None) for key in
             ("missing_array", "short_array", "all_nan_array", "partial_nonfinite_array",
              "real_all_zero_array", "pre_fix_trigger_segments")}
    return {"source": source, "inventory_name": name, "objects": len(cells),
            "split_object_counts": dict(Counter(assignments[cell] for cell in cells)),
            "excluded_before_numeric_read": exclusions, "counts": dict(counters),
            "rates_among_curve_segments": rates, "point_counts": dict(point_counts),
            "trigger_physical_cell_ids": sorted(cells_with_trigger),
            "source_split_sha256": sha256_file(directory / "split_manifest.json"),
            "numerical_read_policy": "parquet physical_cell_id filter before materialization",
            "protected_or_final_numerical_rows_returned": 0}


def rebuild_prefix(name, source):
    directory, identity, cells, assignments, exclusions = admitted(source)
    filtered = OUT / "admitted_tables" / name
    if filtered.exists():
        raise FileExistsError(f"immutable admitted tables already exist: {filtered}")
    filtered.mkdir(parents=True)
    identity.to_parquet(filtered / "identity_map.parquet", index=False)
    for table in ("cycles.parquet", "segments.parquet", "targets.parquet"):
        read_filtered(directory, table, cells).to_parquet(filtered / table, index=False)
    write_json(filtered / "split_manifest.json", {
        "schema_version": "physical-split-v2", "group_column": "physical_cell_id",
        "assignments": {cell: assignments[cell] for cell in cells},
        "counts": dict(Counter(assignments[cell] for cell in cells)),
        "source_split_sha256": sha256_file(directory / "split_manifest.json"),
        "exclusions": exclusions, "policy": "development-only F01 rebuild; no re-split",
    })
    bundle = OUT / "bundles" / name
    manifest = build_feature_bundle(filtered, bundle)
    return bundle / "features.json", manifest


def feature_metadata_inventory():
    records = []
    for path in sorted(DERIVED.glob("*/features.json")):
        manifest = json.loads(path.read_text())
        records.append({
            "manifest": str(path.relative_to(ROOT)), "schema_version": manifest["schema_version"],
            "data_version": manifest.get("data_version"), "rows": len(manifest["rows"]),
            "sources": dict(Counter(row["source_id"] for row in manifest["rows"])),
            "split_rows": dict(Counter(row["split"] for row in manifest["rows"])),
            "sequence_channels": manifest.get("sequence_channels"),
            "metadata_sha256": sha256_file(path), "numerical_arrays_opened": False,
            "policy": "frozen historical artifacts preserved; new channel-validity features require separately bound retrained models",
        })
    return {"finding": "F01", "inventory_scope": "feature metadata only; not a numerical trigger count or model evaluation",
            "historical_manifests": records,
            "current_candidates_retrained": ["H-M1 source-residual qGBDT,3seeds", "M1 domain quantileGBDT,3seeds", "M2 sixchannel temporal multitask,3seeds"],
            "historical_or_nonselected_candidates": "not overwritten or auto-promoted to new feature version; old artifacts remain bound to old schema",
            "missing_temperature_not_demonstrated_as_negative_transfer_cause": True}


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    if not OUT.is_relative_to(ROOT / "battery_platform/research"):
        raise ValueError("F01 research outputs must stay under battery_platform/research")
    OUT.mkdir(parents=True, exist_ok=True)
    audit = OUT / "source_temperature_inventory.json"
    if audit.exists():
        raise FileExistsError("inventory receipt is immutable; choose a new version")
    write_json(audit, {"finding": "F01 missing temperature encoded as measured zero",
                      "scope": "admitted development numerical rows only",
                      "final_labels_accessed": False, "protected_labels_accessed": False,
                      "sources": [audit_source(name, source) for name, source in SOURCES.items()]})
    write_json(OUT / "historical_feature_impact_inventory.json", feature_metadata_inventory())
    if args.rebuild:
        xjtu, xm = rebuild_prefix("xjtu", SOURCES["xjtu_prefix"])
        matr, mm = rebuild_prefix("matr", SOURCES["matr_summary_prefix"])
        combined = OUT / "bundles/combined"
        cm = combine_feature_bundles([xjtu, matr], combined)
        write_json(OUT / "feature_rebuild_receipt.json", {
            "finding": "F01", "new_schema": cm["schema_version"],
            "manifest": str(combined / "features.json"),
            "manifest_sha256": sha256_file(combined / "features.json"),
            "arrays_sha256": sha256_file(combined / "features.npz"),
            "source_rows": {"xjtu": len(xm["rows"]), "matr": len(mm["rows"])},
            "splits": dict(Counter(r["split"] for r in cm["rows"])),
            "new_features_require_new_model_weights": True,
            "previous_artifacts_overwritten": False, "final_labels_accessed": False,
        })
    print(audit)


if __name__ == "__main__":
    main()
