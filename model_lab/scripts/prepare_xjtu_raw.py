#!/usr/bin/env python3
"""Prepare a measured-label, bounded-memory audit view of official XJTU MAT files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from model_lab.data.xjtu_raw import RAW_FIELDS, SUMMARY_FIELDS, as_float_1d, as_text, audit_summary, build_cc_window, description_family, split_time_segments, finite_summary_label, measured_discharge_audit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "data" / "raw" / "xjtu" / "extracted" / "Battery Dataset"
DEFAULT_OUT = ROOT / "data" / "derived" / "xjtu_phase_a"
DEFAULT_REPORT = ROOT / "reports" / "round2"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_identity(path: Path) -> tuple[str, str, str, int | None]:
    batch = path.parent.name
    stem = path.stem
    match = re.match(r"(.+)-([0-9]+)$", stem)
    number = int(match.group(2)) if match else None
    protocol = match.group(1) if match else stem
    cell_id = f"{batch}/{stem}"
    return cell_id, batch, protocol, number


def assignment_for(path: Path) -> str:
    """Filename-only frozen assignment; no labels are read here."""
    _, _, _, number = parse_identity(path)
    return "holdout" if number == 5 else "development"


def safe_cycle_arrays(cycle: dict[str, Any]) -> dict[str, Any]:
    return {key: cycle[key] for key in RAW_FIELDS if key in cycle}


def cycle_anomalies(cycle: dict[str, Any]) -> dict[str, Any]:
    try:
        t = as_float_1d(cycle["relative_time_min"])
        v = as_float_1d(cycle["voltage_V"])
        i = as_float_1d(cycle["current_A"])
        temp = as_float_1d(cycle["temperature_C"])
        lengths = {"time": len(t), "voltage": len(v), "current": len(i), "temperature": len(temp)}
        segments, resets = split_time_segments(t)
        dt = np.diff(t[np.isfinite(t)]) if np.isfinite(t).sum() > 1 else np.array([])
        return {"lengths": lengths, "time_reset_count": int(resets), "segment_count": len(segments), "nonpositive_time_step_count": int((dt <= 0).sum()), "max_time_step_min": float(np.max(dt)) if len(dt) else None, "finite_signal_fraction": float(np.mean(np.isfinite(np.column_stack([t[:min(map(len, [t, v, i, temp]))], v[:min(map(len, [t, v, i, temp]))], i[:min(map(len, [t, v, i, temp]))], temp[:min(map(len, [t, v, i, temp]))]])))) if min(map(len, [t, v, i, temp])) else 0.0}
    except (KeyError, TypeError, ValueError):
        return {"lengths": {}, "time_reset_count": None, "segment_count": 0, "nonpositive_time_step_count": None, "max_time_step_min": None, "finite_signal_fraction": 0.0}


def save_npz(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    arrays: dict[str, np.ndarray] = {}
    for name in ("elapsed_min", "current_A", "temperature_rel_C", "incremental_charge_Ah", "voltage_grid_V", "finite_mask"):
        arrays[name] = np.stack([row["window"][name] for row in rows])
    arrays["window_duration_min"] = np.asarray([row["window"]["duration_min"] for row in rows], dtype=np.float32)
    arrays["window_charge_Ah"] = np.asarray([row["window"]["charge_Ah"] for row in rows], dtype=np.float32)
    arrays["original_cycle_index"] = np.asarray([row["cycle_index"] for row in rows], dtype=np.int32)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def process_cell(path: Path, out_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cell_id, batch, protocol, number = parse_identity(path)
    source_hash = sha256_file(path)
    result: dict[str, Any] = {"cell_id": cell_id, "batch": batch, "protocol": protocol, "filename": path.name, "source_path": str(path), "source_sha256": source_hash, "assignment": assignment_for(path), "status": "failed", "cycle_count": 0, "description_families": {}, "summary": {}, "time_reset_cycle_count": 0, "window_valid_count": 0, "window_invalid_count": 0, "errors": []}
    rows: list[dict[str, Any]] = []
    try:
        mat = loadmat(path, simplify_cells=True)
        data = mat.get("data")
        summary = mat.get("summary")
        if not isinstance(data, list) or not isinstance(summary, dict):
            raise ValueError("expected top-level list data and dict summary")
        result["cycle_count"] = len(data)
        descriptions = [as_text(cycle.get("description", "")) if isinstance(cycle, dict) else "" for cycle in data]
        families = Counter(description_family(desc) for desc in descriptions)
        result["description_families"] = dict(families)
        result["summary_description"] = as_text(summary.get("description", ""))
        diagnostic_indices = [index for index, desc in enumerate(descriptions) if description_family(desc) == "diagnostic"]
        result["diagnostic_cycle_indices"] = [index + 1 for index in diagnostic_indices]
        result["summary"] = audit_summary(summary, len(data), diagnostic_indices)
        reset_count = 0
        anomalies: list[dict[str, Any]] = []
        for index, cycle in enumerate(data):
            if not isinstance(cycle, dict):
                result["errors"].append({"cycle_index": index + 1, "error": "cycle_not_dict"})
                continue
            anomaly = cycle_anomalies(cycle)
            reset_count += int(anomaly.get("time_reset_count") or 0)
            if anomaly.get("time_reset_count") or anomaly.get("nonpositive_time_step_count"):
                anomalies.append({"cycle_index": index + 1, **anomaly})
            if index not in diagnostic_indices:
                continue
            label = finite_summary_label(summary, index)
            window = build_cc_window(cycle)
            provenance = "measured_RPT" if np.isfinite(label) else "unknown"
            rows.append({"cell_id": cell_id, "batch": batch, "protocol": protocol, "cycle_index": index + 1, "description": descriptions[index], "label_provenance": provenance, "target_discharge_capacity_Ah": float(label) if np.isfinite(label) else None, "window_valid": bool(window.valid), "validity_reason": window.reason, "is_first_valid_diagnostic": False, "is_scored_primary": False, "window": window.__dict__})
            rows[-1].update({"source_start_index": window.source_start_index, "source_end_index": window.source_end_index, "window_duration_min": window.duration_min if window.valid else None, "window_charge_Ah": window.charge_Ah if window.valid else None, "discharge_audit": measured_discharge_audit(cycle, label)})
            if window.valid:
                result["window_valid_count"] += 1
            else:
                result["window_invalid_count"] += 1
        result["time_reset_cycle_count"] = len(anomalies)
        result["time_reset_total"] = reset_count
        result["anomalies"] = anomalies[:100]
        first_valid = next((row for row in rows if row["label_provenance"] == "measured_RPT" and row["window_valid"]), None)
        if first_valid:
            first_valid["is_first_valid_diagnostic"] = True
            for row in rows:
                row["reference_cycle_index"] = first_valid["cycle_index"]
                if row["label_provenance"] == "measured_RPT" and row["window_valid"] and row["cycle_index"] > first_valid["cycle_index"]:
                    row["is_scored_primary"] = True
                    row["reference_capacity_Ah"] = first_valid["target_discharge_capacity_Ah"]
                else:
                    row["reference_capacity_Ah"] = None
        valid_rows = [row for row in rows if row["window_valid"]]
        cell_dir = out_root / batch / protocol / path.stem
        cell_dir.mkdir(parents=True, exist_ok=True)
        save_npz(cell_dir / "inputs.npz", valid_rows)
        metadata_rows = [{key: value for key, value in row.items() if key != "window"} for row in rows]
        (cell_dir / "rows.json").write_text(json.dumps(metadata_rows, ensure_ascii=False, indent=2, default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x) + "\n", encoding="utf-8")
        result["output_npz"] = str((cell_dir / "inputs.npz").relative_to(ROOT)) if valid_rows else None
        result["output_rows"] = str((cell_dir / "rows.json").relative_to(ROOT))
        result["status"] = "ok"
    except Exception as exc:  # malformed source is retained in audit, other cells continue
        result["errors"].append({"error": repr(exc), "traceback": traceback.format_exc(limit=3)})
    return result, rows


def main(args: argparse.Namespace) -> int:
    start = time.monotonic()
    root = Path(args.root).resolve()
    out_root = Path(args.out).resolve()
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)
    paths = sorted(path for path in root.glob("Batch-*/*.mat") if path.name != "Temperature_Compensation_Data.mat")
    paths = [path for path in paths if "Temperature_Compensation" not in path.name]
    manifest_rows = [{"cell_id": parse_identity(path)[0], "batch": parse_identity(path)[1], "protocol": parse_identity(path)[2], "filename": path.name, "assignment": assignment_for(path), "source_path": str(path), "source_sha256": None} for path in paths]
    # Assignment is filename-only and therefore frozen before any label is inspected.
    all_results: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    description_totals: Counter[str] = Counter()
    family_totals: Counter[str] = Counter()
    summary_keys: Counter[str] = Counter()
    for number, path in enumerate(paths, 1):
        result, rows = process_cell(path, out_root)
        all_results.append(result)
        all_rows.extend([{key: value for key, value in row.items() if key != "window"} for row in rows])
        description_totals.update(result.get("description_families", {}))
        family_totals.update(result.get("description_families", {}))
        summary_keys.update(result.get("summary", {}).get("summary_keys", []))
        print(f"[{number}/{len(paths)}] {result['cell_id']} status={result['status']} cycles={result.get('cycle_count', 0)} diagnostic={len(result.get('diagnostic_cycle_indices', []))} valid_windows={result.get('window_valid_count', 0)}", flush=True)
    by_cell = {result["cell_id"]: result for result in all_results}
    for row in manifest_rows:
        result = by_cell.get(row["cell_id"], {})
        row["source_sha256"] = result.get("source_sha256")
        row["status"] = result.get("status", "missing")
        row["cycle_count"] = result.get("cycle_count", 0)
        row["diagnostic_count"] = len(result.get("diagnostic_cycle_indices", []))
    report = {"generated_at": now(), "source_root": str(root), "physical_cell_count": len(paths), "successful_cell_count": sum(result.get("status") == "ok" for result in all_results), "failed_cell_count": sum(result.get("status") != "ok" for result in all_results), "assignment_rule": "holdout iff filename suffix is -5; all other cells development; selected before label inspection", "expected_physical_cells": 55, "excluded_files": ["Temperature_Compensation_Data.mat"], "description_family_totals": dict(family_totals), "summary_key_counts": dict(summary_keys), "diagnostic_rows": len(all_rows), "valid_window_rows": sum(result.get("window_valid_count", 0) for result in all_results), "invalid_window_rows": sum(result.get("window_invalid_count", 0) for result in all_results), "measured_rpt_rows": sum(row.get("label_provenance") == "measured_RPT" for row in all_rows), "primary_scored_rows": sum(row.get("is_scored_primary") for row in all_rows), "interpolation_used": False, "cycle_life_used_as_eol": False, "raw_results": all_results, "elapsed_seconds": time.monotonic() - start}
    (report_dir / "raw_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (report_dir / "raw_audit_rows.csv").open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["cell_id", "batch", "protocol", "cycle_index", "description", "label_provenance", "target_discharge_capacity_Ah", "window_valid", "validity_reason", "is_first_valid_diagnostic", "is_scored_primary", "reference_capacity_Ah"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore"); writer.writeheader(); writer.writerows(all_rows)
    (report_dir / "xjtu_cell_manifest.json").write_text(json.dumps({"generated_at": now(), "assignment_rule": report["assignment_rule"], "cells": manifest_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"physical_cell_count": len(paths), "successful_cell_count": report["successful_cell_count"], "diagnostic_rows": report["diagnostic_rows"], "valid_window_rows": report["valid_window_rows"], "primary_scored_rows": report["primary_scored_rows"], "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False))
    return 0 if report["failed_cell_count"] == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT))
    raise SystemExit(main(parser.parse_args()))
