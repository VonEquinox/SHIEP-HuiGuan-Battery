"""V2 source-preserving data contracts. Never reads executable serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

PARSER_VERSION = "v2-data-1.0.0"
PROTECTED_XJTU = frozenset({"Batch-4/R3_battery-5", "Batch-5/RW_battery-5", "Batch-6/Sim_satellite_battery-5"})
TABLES = ("identity_map", "cycles", "segments", "targets")


def _protected_identity(value: Any) -> bool:
    text = str(value)
    return any(cell in text for cell in PROTECTED_XJTU) or (text.startswith("xjtu:") and text.endswith("-5"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path: str | Path, data: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=_json_default) + "\n", encoding="utf-8")


@dataclass
class ParsedDataset:
    identity_map: pd.DataFrame = field(default_factory=pd.DataFrame)
    cycles: pd.DataFrame = field(default_factory=pd.DataFrame)
    segments: pd.DataFrame = field(default_factory=pd.DataFrame)
    targets: pd.DataFrame = field(default_factory=pd.DataFrame)
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def concat(cls, datasets: Iterable["ParsedDataset"]) -> "ParsedDataset":
        items = list(datasets)
        return cls(**{name: pd.concat([getattr(item, name) for item in items if not getattr(item, name).empty], ignore_index=True) if any(not getattr(item, name).empty for item in items) else pd.DataFrame() for name in TABLES}, exclusions=[row for item in items for row in item.exclusions], provenance=[row for item in items for row in item.provenance])

    def write(self, output: str | Path, split: dict[str, Any]) -> dict[str, Any]:
        output = Path(output).resolve()
        namespaces = set(self.identity_map.get("namespace", pd.Series(["experimental"])).dropna())
        if len(namespaces) > 1:
            raise ValueError("experimental and demo_synthetic data require separate manifests")
        namespace = next(iter(namespaces), "experimental")
        # Output must be new V2 derived data; neither an artifact nor V1 raw can
        # be overwritten accidentally by a CLI argument.
        if "v2" not in output.parts or "derived" not in output.parts:
            raise ValueError("V2 derived output must contain data/derived/v2")
        output.mkdir(parents=True, exist_ok=True)
        files = {}
        for name in TABLES:
            path = output / f"{name}.parquet"
            if path.exists():
                raise FileExistsError(f"immutable parsed run already exists: {path}")
            getattr(self, name).to_parquet(path, index=False)
            files[name] = {"path": str(path), "sha256": sha256_file(path), "rows": len(getattr(self, name))}
        quality = {"parser_version": PARSER_VERSION, "exclusions": self.exclusions, "counts": {name: len(getattr(self, name)) for name in TABLES}, "efficiency_policy": "unavailable unless complete, equal SOC and explicit metering boundary", "cycle_life_field_used_as_input": False}
        write_json(output / "quality_report.json", quality)
        write_json(output / "split_manifest.json", split)
        manifest = {"schema_version": "battery-data-v2", "created_at": utc_now(), "parser_version": PARSER_VERSION, "namespace": namespace, "tables": files, "sources": self.provenance, "quality_report": str(output / "quality_report.json"), "split_manifest": str(output / "split_manifest.json"), "target_units": {"soh": "ratio", "capacity": "Ah", "rul": "cycle", "efficiency": "ratio"}, "protected_xjtu_cells": sorted(PROTECTED_XJTU), "split_created_before_parser": True}
        if "source_id" in self.identity_map and self.identity_map.source_id.eq("matr").any():
            paper_flags = self.identity_map.get("paper_reproduction", pd.Series(dtype=object))
            paper_ready = len(paper_flags) == len(self.identity_map) and paper_flags.notna().all()
            paper = {"schema_version": "matr-paper-reproduction-v2", "status": "selection_configured_from_verified_author_rules" if paper_ready else "blocked", "physical_cell_ids": self.identity_map.loc[paper_flags.fillna(False).astype(bool), "physical_cell_id"].tolist() if paper_ready else [], "reason": None if paper_ready else "complete corrected MATLAB batches and verified author selection mapping required; current chart/CSV subsets are not a paper reproduction", "threshold_Ah": .88, "threshold_operator": "strictly_less_than", "last_cycle_plus_one_is_event": False}
            supported = self.targets[self.targets.get("target_name", pd.Series(dtype=str)).eq("rul") & self.targets.get("label_status", pd.Series(dtype=str)).eq("available")] if not self.targets.empty else pd.DataFrame()
            survival = {"schema_version": "matr-survival-all-valid-v2", "physical_cell_ids": sorted(self.cycles.physical_cell_id.unique()) if not self.cycles.empty else [], "supported_survival_physical_cell_ids": sorted(supported.physical_cell_id.unique()) if not supported.empty else [], "right_censored_retained": True, "raw_measurements_not_monotonized": True, "source_ordinal_not_promoted_to_physical_cycle": True}
            write_json(output / "paper_reproduction.json", paper)
            write_json(output / "survival_all_valid.json", survival)
            manifest["task_manifests"] = {"paper_reproduction": str(output / "paper_reproduction.json"), "survival_all_valid": str(output / "survival_all_valid.json")}
        write_json(output / "manifest.json", manifest)
        return manifest


def read_measurement_file(path: str | Path, *, max_bytes: int = 1024**3) -> Any:
    """Read MAT/HDF5/CSV/Parquet, rejecting pickle/joblib and HDF5 links."""
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("raw file exceeds parser size budget")
    extension = path.suffix.lower()
    if extension == ".csv":
        return pd.read_csv(path)
    if extension == ".parquet":
        return pd.read_parquet(path)
    if extension not in {".mat", ".h5", ".hdf5"}:
        raise ValueError("unsupported raw format; pickle/joblib are not accepted")
    import h5py
    if h5py.is_hdf5(path):
        with h5py.File(path, "r") as handle:
            def decode(node: Any, depth: int = 0) -> Any:
                if depth > 12:
                    raise ValueError("MAT/HDF5 nesting exceeds limit")
                if isinstance(node, h5py.Group):
                    result = {}
                    for key in node.keys():
                        link = node.get(key, getlink=True)
                        if isinstance(link, (h5py.ExternalLink, h5py.SoftLink)):
                            raise ValueError("linked HDF5 objects are not accepted")
                        if key != "#refs#":
                            result[key] = decode(node[key], depth + 1)
                    return result
                value = node[()]
                if h5py.check_dtype(ref=node.dtype):
                    decoded = [decode(handle[ref], depth + 1) if ref else None for ref in np.asarray(value).reshape(-1)]
                    return decoded[0] if len(decoded) == 1 else decoded
                if node.attrs.get("MATLAB_class") in (b"char", "char"):
                    return "".join(chr(int(x)) for x in np.asarray(value).reshape(-1))
                return np.asarray(value).squeeze()
            return decode(handle)
    from scipy.io import loadmat
    return {key: value for key, value in loadmat(path, simplify_cells=True).items() if not key.startswith("__")}


def protected_xjtu_filename(path: str | Path) -> bool:
    """Filename-only gate, before opening or hashing any protected raw file."""
    path = Path(path)
    identity = f"{path.parent.name}/{path.stem}"
    # The existing V1 parsing policy reserved every '-5' cell. Preserve the
    # stricter policy as well as the explicitly frozen three final cells.
    return identity in PROTECTED_XJTU or path.stem.endswith("-5")


def _vector(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=float).reshape(-1)


def _finite(value: Any) -> float | None:
    try:
        result = float(np.asarray(value).reshape(-1)[0])
        return result if np.isfinite(result) else None
    except (ValueError, TypeError, IndexError):
        return None


def efficiency_label(time_s: Any, voltage_V: Any, current_A: Any, *, complete: bool, start_soc: float | None, end_soc: float | None, metering_boundary: str | None, soc_tolerance: float = .01) -> dict[str, Any]:
    unavailable = {"label_status": "unavailable", "value": None, "unit": "ratio", "metering_boundary": metering_boundary}
    if not complete or start_soc is None or end_soc is None or not metering_boundary or abs(start_soc - end_soc) > soc_tolerance:
        return {**unavailable, "reason": "incomplete_or_soc_boundary_mismatch"}
    t, v, current = map(_vector, (time_s, voltage_V, current_A))
    if len(t) < 2 or len({len(t), len(v), len(current)}) != 1 or not np.isfinite(np.column_stack([t, v, current])).all() or np.any(np.diff(t) <= 0):
        return {**unavailable, "reason": "invalid_measurement"}
    trapezoid = getattr(np, "trapezoid", None)
    if trapezoid is None:  # NumPy < 2 compatibility without eager np.trapz access.
        trapezoid = np.trapz
    ein = float(trapezoid(np.maximum(v * current, 0), t) / 3600)
    eout = float(trapezoid(np.maximum(-v * current, 0), t) / 3600)
    if ein <= 0 or eout <= 0 or eout > ein:
        return {**unavailable, "reason": "energy_boundary_inconsistent"}
    return {"label_status": "available", "value": eout / ein, "unit": "ratio", "energy_in_Wh": ein, "energy_out_Wh": eout, "metering_boundary": metering_boundary}


def build_survival_target(cycle_numbers: Any, capacity_Ah: Any, *, threshold_Ah: float, target_definition_id: str, physical_cycles_known: bool = True, inclusive: bool = True) -> dict[str, Any]:
    if not physical_cycles_known:
        return {"target_name": "rul", "label_status": "unavailable", "reason": "source_ordinal_is_not_verified_physical_cycle", "target_definition_id": target_definition_id}
    cycles, capacity = map(_vector, (cycle_numbers, capacity_Ah))
    valid = np.isfinite(cycles) & np.isfinite(capacity) & (capacity > 0)
    cycles, capacity = cycles[valid], capacity[valid]
    if not len(cycles) or np.any(np.diff(cycles) <= 0) or threshold_Ah <= 0:
        raise ValueError("survival target needs positive threshold and ordered physical cycles")
    hits = np.flatnonzero(capacity <= threshold_Ah if inclusive else capacity < threshold_Ah)
    threshold_operator = "less_than_or_equal" if inclusive else "strictly_less_than"
    if not len(hits):
        return {"target_name": "rul", "unit": "cycle", "value": None, "event": False, "censor_type": "right", "lower_event_bound": float(cycles[-1]), "upper_event_bound": None, "observed_at": float(cycles[-1]), "available_at": float(cycles[-1]), "target_definition_id": target_definition_id, "threshold_Ah": threshold_Ah, "threshold_operator": threshold_operator, "label_status": "available"}
    index = int(hits[0])
    upper = float(cycles[index])
    lower = float(cycles[index - 1]) if index else 0.
    exact = index > 0 and upper - lower == 1
    return {"target_name": "rul", "unit": "cycle", "value": upper if exact else None, "event": True, "censor_type": "exact" if exact else "interval", "lower_event_bound": upper if exact else lower, "upper_event_bound": upper, "observed_at": upper, "available_at": upper, "target_definition_id": target_definition_id, "threshold_Ah": threshold_Ah, "threshold_operator": threshold_operator, "label_status": "available"}


def parse_xjtu_mat(path: str | Path, *, max_segments: int = 32) -> ParsedDataset:
    path = Path(path)
    if protected_xjtu_filename(path):
        raise PermissionError("protected XJTU cell is excluded before any raw-file access")
    from model_lab.data.xjtu_raw import as_text, description_family, split_time_segments
    data = read_measurement_file(path)
    raw = data.get("data")
    summary = data.get("summary")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, np.ndarray)) or not isinstance(summary, dict):
        raise ValueError("XJTU requires data cycle list and summary structure")
    local_id = f"{path.parent.name}/{path.stem}"
    physical_id = f"xjtu:{local_id}"
    protocol = path.stem.rsplit("-", 1)[0]
    source_hash = sha256_file(path)
    provenance = {"source_id": "xjtu", "path": str(path.resolve()), "sha256": source_hash, "bytes": path.stat().st_size, "parser_version": PARSER_VERSION, "origin": "real_experimental"}
    identity = {"source_id": "xjtu", "physical_cell_id": physical_id, "source_cell_id": local_id, "chemistry": "NCM", "manufacturer_model": "LISHEN 18650", "nominal_capacity_Ah": 2., "batch_id": path.parent.name, "protocol_id": protocol, "installation_id": None, "identity_basis": "official_record_and_original_filename", "namespace": "experimental"}
    capacities = _vector(summary.get("discharge_capacity_Ah", []))
    cycle_rows, segment_rows, target_rows, exclusions = [], [], [], []
    reference: dict[str, Any] | None = None
    for ordinal, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            exclusions.append({"physical_cell_id": physical_id, "cycle_index": ordinal, "reason": "cycle_not_structure"})
            continue
        diagnostic = description_family(as_text(item.get("description", ""))) == "diagnostic"
        capacity = _finite(capacities[ordinal - 1]) if ordinal <= len(capacities) else None
        if capacity is not None and capacity <= 0:
            exclusions.append({"physical_cell_id": physical_id, "cycle_index": ordinal, "reason": "nonpositive_capacity_label"})
            capacity = None
        cycle_rows.append({"physical_cell_id": physical_id, "source_id": "xjtu", "cycle_index": ordinal, "source_cycle_ordinal": ordinal, "physical_cycles_known": False, "capacity_Ah": capacity, "nominal_capacity_Ah": 2., "chemistry": "NCM", "protocol_id": protocol, "batch_id": path.parent.name, "diagnostic": diagnostic, "observed_at": float(ordinal), "available_at": float(ordinal), "time_basis": "source_record_ordinal", "soh_nominal": capacity / 2 if capacity is not None else None, "raw_ref": f"{path.resolve()}#data/{ordinal}"})
        if not diagnostic:
            continue
        if reference is None and capacity is not None:
            reference = {"reference_capacity_Ah": capacity, "reference_cutoff": float(ordinal), "reference_segment_ids": [f"{physical_id}:record-{ordinal}:part-0"], "reference_protocol": protocol}
        if capacity is not None and reference is not None:
            target_rows.append({"physical_cell_id": physical_id, "source_id": "xjtu", "cycle_index": ordinal, "target_name": "soh", "value": capacity / reference["reference_capacity_Ah"], "unit": "ratio", "target_basis": "frozen_first_observed_RPT_capacity", "target_definition_id": "xjtu-rpt-reference-soh-v2", "observed_at": float(ordinal), "available_at": float(ordinal), "event": None, "censor_type": None, "label_status": "available", "label_source": f"{path.resolve()}#summary/discharge_capacity_Ah/{ordinal}", **reference})
        if len(segment_rows) >= max_segments:
            exclusions.append({"physical_cell_id": physical_id, "cycle_index": ordinal, "reason": "diagnostic_curve_exceeds_explicit_segment_budget", "label_retained": True})
            continue
        arrays = {"time_s": _vector(item.get("relative_time_min", [])) * 60, "voltage_V": _vector(item.get("voltage_V", [])), "current_A": _vector(item.get("current_A", [])), "temperature_C": _vector(item.get("temperature_C", []))}
        lengths = {name: len(array) for name, array in arrays.items()}
        if not lengths["time_s"] or len(set(lengths.values())) != 1:
            exclusions.append({"physical_cell_id": physical_id, "cycle_index": ordinal, "reason": "signal_length_mismatch", "lengths": lengths})
            continue
        parts, reset_count = split_time_segments(arrays["time_s"])
        for part_index, part in enumerate(parts):
            segment_id = f"{physical_id}:record-{ordinal}:part-{part_index}"
            signals = {name: [float(value) if np.isfinite(value) else None for value in array[part]] for name, array in arrays.items()}
            current = arrays["current_A"][part]
            phase = ["charge" if x > .05 else "discharge" if x < -.05 else "rest" for x in current]
            segment_rows.append({"segment_id": segment_id, "physical_cell_id": physical_id, "cell_id": physical_id, "source_id": "xjtu", "cycle_index": ordinal, "observed_at": float(ordinal), "available_at": float(ordinal), "start": float(arrays["time_s"][part][0]), "end": float(arrays["time_s"][part][-1]), "time_unit": "s", "time_basis": "source_record_ordinal", "phase": phase, "sensor_level": "cell", "provenance": "real_experimental", "raw_ref": f"{path.resolve()}#data/{ordinal}", "quality_flags": ["time_reset_split"] if reset_count else [], "sample_count": len(current), "complete_cycle": False, "efficiency_label_status": "unavailable", "chemistry": "NCM", "protocol_id": protocol, **signals})
    # The observed record ordinal is preserved, but never silently promoted to
    # a physical aging-cycle count for RUL. No author cycle_life is loaded as a
    # feature or interpreted as a measured event.
    exclusions.append({"physical_cell_id": physical_id, "target_name": "rul", "reason": "source_record_ordinal_not_verified_physical_cycle"})
    return ParsedDataset(pd.DataFrame([identity]), pd.DataFrame(cycle_rows), pd.DataFrame(segment_rows), pd.DataFrame(target_rows), exclusions, [provenance])


def verify_matr_continuation(first: dict[str, Any], second: dict[str, Any], *, capacity_tolerance_Ah: float = .1) -> dict[str, Any]:
    """Prove original identity and measured continuity before joining records."""
    for field_name in ("source_identity",):
        if not first.get(field_name) or first.get(field_name) != second.get(field_name) or first.get("identity_basis") == "channel_only" or second.get("identity_basis") == "channel_only":
            raise ValueError("MATR continuation requires matching original barcode/channel identity")
    previous = pd.DataFrame(first["cycles"]).sort_values("cycle_index")
    following = pd.DataFrame(second["cycles"]).sort_values("cycle_index")
    if previous.empty or following.empty:
        raise ValueError("MATR continuation has no measurable cycles")
    if any(np.any(np.diff(frame["cycle_index"].to_numpy(float)) <= 0) for frame in (previous, following)):
        raise ValueError("MATR continuation has nonmonotonic cycle sequence")
    last, start = previous.iloc[-1], following.iloc[0]
    if not np.isfinite([last["capacity_Ah"], start["capacity_Ah"]]).all() or abs(last["capacity_Ah"] - start["capacity_Ah"]) > capacity_tolerance_Ah:
        raise ValueError("MATR continuation failed measured capacity continuity")
    if start["cycle_index"] == last["cycle_index"] + 1:
        offset = 0
    elif start["cycle_index"] == 1:
        offset = int(last["cycle_index"])
    else:
        raise ValueError("MATR continuation has unexplained cycle gap")
    physical_id = first["physical_cell_id"]
    following["source_cycle_index"] = following["cycle_index"]
    following["cycle_index"] += offset
    following["physical_cell_id"] = physical_id
    raw_parts = [{"raw_cycles": part.get("raw_cycles", {}), "path": part.get("path"), "batch_index_zero": part.get("batch_index_zero"), "source_record_id": part["source_record_id"], "cycle_offset": part_offset} for part, part_offset in ((first, 0), (second, offset))]
    return {"physical_cell_id": physical_id, "cycles": pd.concat([previous, following], ignore_index=True), "cycle_offset": offset, "raw_parts": raw_parts, "identity_verified": True, "capacity_continuity_Ah": float(abs(last["capacity_Ah"] - start["capacity_Ah"])), "source_record_ids": [first["source_record_id"], second["source_record_id"]]}


def repair_matr_continuations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Author's MATLAB b2 [8,9,10,16,17] maps to Python [7,8,9,15,16]."""
    pairs = [(index, b2) for index, b2 in enumerate((7, 8, 9, 15, 16))]
    lookup = {(row["batch_id"], row["batch_index_zero"]): row for row in records}
    repaired, removed = [], set()
    for b1, b2 in pairs:
        key1, key2 = ("2017-05-12", b1), ("2017-06-30", b2)
        if key1 not in lookup or key2 not in lookup:
            raise ValueError("MATR identity repair requires all five original continuation pairs")
        joined = verify_matr_continuation(lookup[key1], lookup[key2])
        repaired.append({**lookup[key1], **joined})
        removed.update((key1, key2))
    return repaired + [row for row in records if (row["batch_id"], row["batch_index_zero"]) not in removed]


def _matr_cells(batch: Any) -> list[dict[str, Any]]:
    if isinstance(batch, list):
        return batch
    if isinstance(batch, dict):
        if isinstance(batch.get("summary"), list):
            count = len(batch["summary"])
            return [{key: value[index] if isinstance(value, list) and len(value) == count else value for key, value in batch.items()} for index in range(count)]
        return [batch]
    raise ValueError("unrecognized MATR batch structure")


def parse_matr_mat(paths: Iterable[str | Path], *, repair_continuations: bool = True, paper_exclusion_record_ids: Iterable[str] = ()) -> ParsedDataset:
    """Parse official corrected structures, failing closed on unknown joins.

    The author filtering list must be supplied from a verified reproduction
    manifest, not blindly copied from a mirror. Measurable right-censored
    records remain in survival_all_valid even if excluded by the paper task.
    """
    import re
    records, provenance, exclusions = [], [], []
    paper_excluded = set(paper_exclusion_record_ids)
    for raw_path in paths:
        path = Path(raw_path)
        match = re.search(r"201[78]-\d{2}-\d{2}", path.name)
        if not match:
            raise ValueError("MATR corrected file requires original batch date in filename")
        batch_id = match.group()
        data = read_measurement_file(path, max_bytes=4 * 1024**3)
        if "batch" not in data:
            raise ValueError("MATR file has no batch structure; inspect actual official schema")
        provenance.append({"source_id": "matr", "path": str(path.resolve()), "sha256": sha256_file(path), "bytes": path.stat().st_size, "parser_version": PARSER_VERSION, "origin": "real_experimental"})
        for index, cell in enumerate(_matr_cells(data["batch"])):
            source_record_id = f"{batch_id}:channel-{index + 1}"
            source_identity = next((str(cell[key]) for key in ("barcode", "cell_id") if key in cell and cell[key] is not None), None)
            summary = cell.get("summary", {})
            cycle_numbers = _vector(summary.get("cycle", []))
            capacities = _vector(summary.get("QDischarge", []))
            if len(cycle_numbers) != len(capacities) or not len(capacities):
                exclusions.append({"source_record_id": source_record_id, "reason": "summary_cycle_capacity_length_mismatch"})
                continue
            physical_id = f"matr:{source_identity or source_record_id}"
            cycles = []
            for cycle_number, capacity in zip(cycle_numbers, capacities):
                if not np.isfinite([cycle_number, capacity]).all() or capacity <= 0:
                    exclusions.append({"source_record_id": source_record_id, "cycle_index": _finite(cycle_number), "reason": "invalid_capacity_or_cycle"})
                    continue
                cycles.append({"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle_number), "source_cycle_index": float(cycle_number), "physical_cycles_known": True, "capacity_Ah": float(capacity), "nominal_capacity_Ah": 1.1, "chemistry": "LFP", "protocol_id": str(cell.get("policy", "unknown")), "batch_id": batch_id, "observed_at": float(cycle_number), "available_at": float(cycle_number), "soh_nominal": float(capacity) / 1.1, "raw_ref": f"{path.resolve()}#batch/{index + 1}/summary", "source_record_id": source_record_id})
            if cycles:
                records.append({"source_record_id": source_record_id, "physical_cell_id": physical_id, "source_identity": source_identity, "batch_id": batch_id, "batch_index_zero": index, "cycles": cycles, "raw_cycles": cell.get("cycles", {}), "path": str(path.resolve()), "protocol_id": str(cell.get("policy", "unknown"))})
    if repair_continuations:
        # Identity absence is a blocker, not permission to silently assign five
        # continuing batteries to two objects or different dataset splits.
        records = repair_matr_continuations(records)
    identities, cycles, segments, targets = [], [], [], []
    for record in records:
        physical_id = record["physical_cell_id"]
        frame = pd.DataFrame(record["cycles"])
        identities.append({"source_id": "matr", "physical_cell_id": physical_id, "source_cell_id": record["source_record_id"], "chemistry": "LFP", "manufacturer_model": None, "nominal_capacity_Ah": 1.1, "batch_id": record["batch_id"], "protocol_id": record["protocol_id"], "installation_id": None, "identity_basis": "verified_original_identity" if record.get("source_identity") else "original_batch_and_channel", "namespace": "experimental", "continuation_verified": record.get("identity_verified", False), "paper_reproduction": record["source_record_id"] not in paper_excluded if paper_excluded else None, "survival_all_valid": True})
        cycles.extend(frame.to_dict("records"))
        survival = build_survival_target(frame.cycle_index, frame.capacity_Ah, threshold_Ah=.88, target_definition_id="matr-2019-nominal-80pct-0.88Ah-v2", inclusive=False)
        targets.append({"physical_cell_id": physical_id, "source_id": "matr", "target_basis": "1.1Ah_nominal_80percent", "label_source": "measured_discharge_capacity_summary", **survival})
        reference_capacity = float(frame.capacity_Ah.iloc[0])
        for row in frame.to_dict("records"):
            targets.append({"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": row["cycle_index"], "target_name": "soh", "value": row["capacity_Ah"] / reference_capacity, "unit": "ratio", "target_definition_id": "matr-frozen-initial-reference-soh-v2", "target_basis": "frozen_first_valid_capacity", "reference_capacity_Ah": reference_capacity, "reference_cutoff": float(frame.cycle_index.iloc[0]), "observed_at": row["observed_at"], "available_at": row["available_at"], "label_status": "available", "label_source": row["raw_ref"]})
        raw_items = []
        for part in record.get("raw_parts", [{**record, "cycle_offset": 0}]):
            raw_cycles = part.get("raw_cycles", {})
            source_items = list(raw_cycles.items()) if isinstance(raw_cycles, dict) else list(enumerate(raw_cycles, 1))
            raw_items.extend((key, raw, part) for key, raw in source_items)
        for key, raw, part in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                cycle_number = int(str(key)) + int(part.get("cycle_offset", 0))
                t, v, current = (_vector(raw[field]) for field in ("t", "V", "I"))
            except (KeyError, ValueError, TypeError):
                exclusions.append({"source_record_id": record["source_record_id"], "raw_cycle_key": str(key), "reason": "unsupported_raw_cycle_schema"})
                continue
            temp = _vector(raw.get("T", np.full(len(t), np.nan)))
            if len({len(t), len(v), len(current), len(temp)}) != 1 or len(t) < 2 or np.any(np.diff(t) <= 0):
                exclusions.append({"source_record_id": record["source_record_id"], "raw_cycle_key": str(key), "reason": "invalid_raw_signal_lengths_or_time"})
                continue
            segments.append({"segment_id": f"{physical_id}:cycle-{cycle_number}", "physical_cell_id": physical_id, "cell_id": physical_id, "source_id": "matr", "cycle_index": cycle_number, "observed_at": float(cycle_number), "available_at": float(cycle_number), "time_s": (t * 60).tolist(), "time_unit": "s", "source_time_unit": "min", "voltage_V": v.tolist(), "current_A": current.tolist(), "temperature_C": [float(x) if np.isfinite(x) else None for x in temp], "phase": ["charge" if x > .05 else "discharge" if x < -.05 else "rest" for x in current], "chemistry": "LFP", "protocol_id": record["protocol_id"], "sensor_level": "cell", "provenance": "real_experimental", "raw_ref": f"{part['path']}#batch/{part['batch_index_zero'] + 1}/cycles/{key}", "quality_flags": [], "efficiency_label_status": "unavailable"})
        if record["source_record_id"] in paper_excluded:
            exclusions.append({"source_record_id": record["source_record_id"], "reason": "verified_author_paper_reproduction_exclusion", "retained_in_survival_all_valid": True})
    return ParsedDataset(pd.DataFrame(identities), pd.DataFrame(cycles), pd.DataFrame(segments), pd.DataFrame(targets), exclusions, provenance)


def parse_table(path: str | Path, contract: dict[str, Any]) -> ParsedDataset:
    """Explicit table adapter for actual operational/generated task granularity."""
    frame = read_measurement_file(path)
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("CSV/Parquet operational adapter requires a tabular source")
    columns = contract.get("columns", {})
    frame = frame.rename(columns=columns)
    group = contract.get("group_column", "physical_cell_id")
    required = {group, "available_at", "observed_at"}
    if not required <= set(frame.columns) or frame[group].isna().any():
        raise ValueError("operational/generated input requires explicit group identity and visibility")
    if (frame.available_at < frame.observed_at).any():
        raise ValueError("observation cannot become available before it exists")
    source_id = contract["source_id"]
    origin = contract["origin"]
    if origin not in {"real_operational", "public_generated"}:
        raise ValueError("adapter origin must preserve operational/generated distinction")
    frame["physical_cell_id"] = frame[group].astype(str).map(lambda value: value if value.startswith(source_id + ":") else source_id + ":" + value)
    frame["source_id"] = source_id
    frame["provenance"] = origin
    identity = frame[["physical_cell_id", "source_id"]].drop_duplicates().assign(chemistry=contract.get("chemistry"), manufacturer_model=None, nominal_capacity_Ah=None, batch_id=None, protocol_id=contract.get("protocol_id"), installation_id=None, sensor_level=contract.get("sensor_level"), namespace="experimental" if origin == "real_operational" else "demo_synthetic")
    targets = pd.DataFrame()
    label_column = contract.get("label_column")
    if label_column:
        if label_column not in frame:
            raise ValueError("declared label is absent; do not synthesize a fault label")
        targets = frame[["physical_cell_id", "source_id", "available_at", "observed_at", label_column]].rename(columns={label_column: "value"}).assign(target_name="fault", unit="class", target_definition_id=contract["target_definition_id"], target_basis=contract.get("sensor_level"), label_status="available", label_source=str(Path(path).resolve()))
    label_only_columns = {"original_snippet_label", "hidden_truth", "final_root_cause", *contract.get("label_only_columns", [])}
    if label_column:
        label_only_columns.add(label_column)
    return ParsedDataset(identity, pd.DataFrame(), frame.drop(columns=[name for name in label_only_columns if name in frame]), targets, [], [{"source_id": source_id, "origin": origin, "path": str(Path(path).resolve()), "sha256": sha256_file(path), "parser_version": PARSER_VERSION}])


def parse_matr_official(tests_json: str | Path, *, max_cells: int = 36, reference_ordinal: int = 10, query_stride: int = 10) -> tuple[ParsedDataset, dict[str, Any]]:
    """Import official original-barcode capacity charts as measured summaries.

    The current API omits numeric x values. Chart ordinal is therefore explicit
    and RUL unavailable, unless a separate complete raw CSV establishes actual
    physical-cycle numbers. No absent curve is interpolated into existence.
    Selection/split uses barcode only, before reading a capacity value.
    """
    tests_json = Path(tests_json)
    raw_tests = json.loads(tests_json.read_text(encoding="utf-8"))
    # Isolate the independent 2018 batch. Earlier batches have five continuing
    # batteries requiring verified identity joins, not new independent rows.
    candidates = [test for test in raw_tests if test.get("cellId") and test.get("name", "").startswith("2018-04-12_")]
    candidates.sort(key=lambda test: hashlib.sha256(str(test["cellId"]).encode()).hexdigest())
    candidates = candidates[:max_cells]
    if len({test["cellId"] for test in candidates}) != len(candidates):
        raise ValueError("duplicate original barcode must be repaired before splitting")
    identity_rows = [{"source_id": "matr", "physical_cell_id": f"matr:{test['cellId']}", "source_cell_id": test["cellId"], "source_record_id": test["_id"], "channel_id": str(test.get("channel")), "chemistry": "LFP", "manufacturer_model": "A123 Systems APR18650M1A", "nominal_capacity_Ah": 1.1, "batch_id": "2018-04-12", "protocol_id": "unknown", "installation_id": None, "namespace": "experimental", "identity_basis": "original_official_cellId_barcode", "curve_available": False, "summary_available": True} for test in candidates]
    identity = pd.DataFrame(identity_rows)
    split = freeze_group_split(identity, ratios=(.5, 1/6, 1/6, 1/6))
    cycles, segments, targets, exclusions = [], [], [], []
    for test, ident in zip(candidates, identity_rows):
        physical_id = ident["physical_cell_id"]
        if ident["channel_id"] == "46":
            exclusions.append({"physical_cell_id": physical_id, "reason": "official_batch_collection_problem_channel_46", "scope": "preserve original record; exclude from modeled queries"})
            continue
        chart = test.get("summary", {}).get("Discharge capacity vs cycle number", {})
        capacity = _vector(chart.get("y", {}).get("data", []))
        if len(capacity) < reference_ordinal or not np.isfinite(capacity[reference_ordinal - 1]) or capacity[reference_ordinal - 1] <= 0:
            exclusions.append({"physical_cell_id": physical_id, "reason": "fixed_ordinal10_reference_unavailable"})
            continue
        reference = float(capacity[reference_ordinal - 1])
        x_data = chart.get("x", {}).get("data")
        physical_known = x_data is not None and len(x_data) == len(capacity)
        cycle_numbers = _vector(x_data) if physical_known else np.arange(1, len(capacity) + 1)
        for index, (cycle_number, measured) in enumerate(zip(cycle_numbers, capacity), 1):
            if not np.isfinite(measured) or measured <= 0:
                exclusions.append({"physical_cell_id": physical_id, "source_chart_ordinal": index, "reason": "invalid_measured_capacity"})
                continue
            raw_ref = f"{tests_json.resolve()}#test/{test['_id']}/summary/discharge_capacity/{index}"
            flags = ["capacity_above_150pct_nominal_preserved"] if measured > 1.5 * 1.1 else []
            row = {"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle_number), "source_chart_ordinal": index, "physical_cycles_known": physical_known, "capacity_Ah": float(measured), "nominal_capacity_Ah": 1.1, "chemistry": "LFP", "protocol_id": "unknown", "batch_id": "2018-04-12", "diagnostic": True, "observed_at": float(index), "available_at": float(index), "time_basis": "official_capacity_chart_ordinal" if not physical_known else "official_physical_cycle", "soh_nominal": float(measured) / 1.1, "reference_capacity_Ah": reference, "reference_cutoff": float(reference_ordinal), "quality_flags": flags, "raw_ref": raw_ref}
            cycles.append(row)
            if index >= reference_ordinal:
                targets.append({"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle_number), "target_name": "soh", "value": float(measured) / reference, "unit": "ratio", "target_definition_id": "matr-official-chart-frozen-ordinal10-reference-soh-v2", "target_basis": "fixed_visible_capacity_chart_ordinal10", "reference_capacity_Ah": reference, "reference_cutoff": float(reference_ordinal), "reference_segment_ids": [], "observed_at": float(index), "available_at": float(index), "label_status": "available", "label_source": raw_ref})
                if (index - reference_ordinal) % query_stride == 0:
                    segments.append({"segment_id": f"{physical_id}:chart-{index}", "physical_cell_id": physical_id, "cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle_number), "observed_at": float(index), "available_at": float(index), "time_unit": "source_chart_ordinal", "time_basis": row["time_basis"], "time_s": [], "voltage_V": [], "current_A": [], "temperature_C": [], "phase": [], "sample_count": 0, "input_kind": "measured_capacity_history_statistics", "curve_available": False, "sensor_level": "cell", "provenance": "real_experimental", "raw_ref": raw_ref, "quality_flags": ["raw_curve_unavailable", "charging_protocol_unknown"], "chemistry": "LFP", "protocol_id": "unknown", "reference_capacity_Ah": reference, "reference_cutoff": float(reference_ordinal), "efficiency_label_status": "unavailable"})
        survival = build_survival_target(cycle_numbers, capacity, threshold_Ah=.88, target_definition_id="matr-2019-nominal-80pct-0.88Ah-v2", physical_cycles_known=physical_known, inclusive=False)
        targets.append({"physical_cell_id": physical_id, "source_id": "matr", "target_basis": "1.1Ah_nominal_80percent", "label_source": str(tests_json.resolve()), **survival})
    provenance = [{"source_id": "matr", "path": str(tests_json.resolve()), "sha256": sha256_file(tests_json), "bytes": tests_json.stat().st_size, "parser_version": PARSER_VERSION, "origin": "real_experimental", "scope": "official capacity summary chart measurements; not imported corrected MATLAB raw batch", "missing_curves": True}]
    return ParsedDataset(identity, pd.DataFrame(cycles), pd.DataFrame(segments), pd.DataFrame(targets), exclusions, provenance), split


def parse_matr_csv(path: str | Path, test_metadata: dict[str, Any], *, max_segments: int = 32) -> ParsedDataset:
    """Original Arbin CSV with explicit cycles and units, separate from charts."""
    path = Path(path)
    frame = pd.read_csv(path)
    needed = {"Test_Time", "Cycle_Index", "Voltage", "Current", "Temperature", "Discharge_Capacity"}
    if not needed <= set(frame.columns) or not test_metadata.get("cellId"):
        raise ValueError("official MATR CSV requires actual Arbin fields and original barcode")
    physical_id = f"matr:{test_metadata['cellId']}"
    identity = {"source_id": "matr", "physical_cell_id": physical_id, "source_cell_id": test_metadata["cellId"], "chemistry": "LFP", "manufacturer_model": "A123 Systems APR18650M1A", "nominal_capacity_Ah": 1.1, "batch_id": test_metadata["name"][:10], "protocol_id": "unknown", "installation_id": None, "namespace": "experimental", "identity_basis": "official_original_barcode", "curve_available": True}
    cycle_rows, segment_rows, target_rows, exclusions = [], [], [], []
    grouped = frame.groupby("Cycle_Index", sort=True)
    reference_capacity, reference_cycle = None, None
    for cycle, group in grouped:
        measured = _finite(group.Discharge_Capacity.max())
        if measured is None or measured <= 0:
            exclusions.append({"physical_cell_id": physical_id, "cycle_index": _finite(cycle), "reason": "no_valid_measured_discharge"})
            continue
        if reference_capacity is None and cycle >= 10:
            reference_capacity, reference_cycle = measured, float(cycle)
        raw_ref = f"{path.resolve()}#Cycle_Index={cycle}"
        cycle_rows.append({"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle), "physical_cycles_known": True, "capacity_Ah": measured, "nominal_capacity_Ah": 1.1, "chemistry": "LFP", "protocol_id": "unknown", "diagnostic": True, "observed_at": float(cycle), "available_at": float(cycle), "time_basis": "original_arbin_physical_Cycle_Index", "soh_nominal": measured/1.1, "raw_ref": raw_ref})
        if reference_capacity is not None:
            target_rows.append({"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle), "target_name": "soh", "value": measured/reference_capacity, "unit": "ratio", "target_definition_id": "matr-arbin-frozen-cycle10-reference-soh-v2", "target_basis": "first_valid_original_arbin_cycle_at_or_after10", "reference_capacity_Ah": reference_capacity, "reference_cutoff": reference_cycle, "observed_at": float(cycle), "available_at": float(cycle), "label_status": "available", "label_source": raw_ref})
        if len(segment_rows) < max_segments:
            group = group.sort_values("Test_Time")
            if len(group) < 2 or (np.diff(group.Test_Time.to_numpy()) <= 0).any():
                exclusions.append({"physical_cell_id": physical_id, "cycle_index": float(cycle), "reason": "nonmonotonic_original_time"})
                continue
            segment_rows.append({"segment_id": f"{physical_id}:arbin-{cycle}", "physical_cell_id": physical_id, "cell_id": physical_id, "source_id": "matr", "cycle_index": float(cycle), "observed_at": float(cycle), "available_at": float(cycle), "time_s": group.Test_Time.to_list(), "voltage_V": group.Voltage.to_list(), "current_A": group.Current.to_list(), "temperature_C": group.Temperature.to_list(), "phase": ["charge" if value > .05 else "discharge" if value < -.05 else "rest" for value in group.Current], "time_unit": "s", "time_basis": "original_arbin_physical_Cycle_Index", "chemistry": "LFP", "protocol_id": "unknown", "sensor_level": "cell", "provenance": "real_experimental", "raw_ref": raw_ref, "quality_flags": [], "efficiency_label_status": "unavailable"})
    cycles = pd.DataFrame(cycle_rows)
    if not cycles.empty:
        survival = build_survival_target(cycles.cycle_index, cycles.capacity_Ah, threshold_Ah=.88, target_definition_id="matr-arbin-nominal-80pct-0.88Ah-v2", inclusive=False)
        target_rows.append({"physical_cell_id": physical_id, "source_id": "matr", "target_basis": "1.1Ah_nominal_80percent", "label_source": str(path.resolve()), **survival})
    return ParsedDataset(pd.DataFrame([identity]), cycles, pd.DataFrame(segment_rows), pd.DataFrame(target_rows), exclusions, [{"source_id": "matr", "path": str(path.resolve()), "sha256": sha256_file(path), "bytes": path.stat().st_size, "parser_version": PARSER_VERSION, "origin": "real_experimental", "source_test_id": test_metadata["_id"]}])


def parse_ch_csvs(paths: Iterable[str | Path], *, archive_ref: str | None = None) -> tuple[ParsedDataset, dict[str, Any]]:
    """Actual published generated faults, grouped conservatively by VIN token.

    The generator's original mother-data IDs are not published. Reused VIN
    tokens stay together across chemistry and fault categories; independence
    of different VIN mother data cannot be certified and is reported.
    """
    paths = sorted(Path(path) for path in paths)
    identities, segments, targets, exclusions, provenance = [], [], [], [], []
    classes = {"normal": 0, "high_resistance": 1, "low_capacity": 2, "self_discharge": 3}
    for path in paths:
        chemistry, category, vin = path.parts[-4:-1]
        if chemistry not in {"LFP", "NCM"} or category not in classes:
            raise ValueError("generated source chemistry/fault directory does not match inspected release schema")
        identities.append({"source_id": "ch_batterygen", "physical_cell_id": f"ch_batterygen:{chemistry}:{category}:{vin}", "source_cell_id": vin, "root_scenario_id": f"ch_batterygen:conservative-{vin}", "generation_parent_id": None, "chemistry": chemistry, "manufacturer_model": None, "nominal_capacity_Ah": None, "batch_id": "public_generated_v1.0.0", "protocol_id": "generated_vehicle_charging", "installation_id": None, "sensor_level": "vehicle_pack", "namespace": "demo_synthetic", "identity_basis": "published_generated_path_not_real_vehicle_identity"})
    identity = pd.DataFrame(identities).drop_duplicates("physical_cell_id")
    root_identity = identity[["root_scenario_id"]].drop_duplicates()
    root_split = freeze_group_split(root_identity, group_column="root_scenario_id")
    split = {**root_split, "assignments": {row.physical_cell_id: root_split["assignments"][row.root_scenario_id] for row in identity.itertuples()}, "root_assignments": root_split["assignments"], "independent_root_count": len(root_identity), "generation_parent_overlap": "unavailable_original_generator_mother_ids_not_published", "final_benchmark_eligibility": "exploratory_only_mother_overlap_unknown"}
    mapping = {row["physical_cell_id"]: row for row in identities}
    for path in paths:
        chemistry, category, vin = path.parts[-4:-1]
        physical_id = f"ch_batterygen:{chemistry}:{category}:{vin}"
        frame = pd.read_csv(path)
        needed = {"TIME", "SUM_VOLTAGE", "SUM_CURRENT", "SOC", "MAX_CELL_VOLT", "MIN_CELL_VOLT", "MAX_TEMP", "MIN_TEMP"}
        if not needed <= set(frame.columns):
            exclusions.append({"path": str(path), "reason": "required_release_columns_missing"})
            continue
        charge_index = int(path.stem.rsplit("_", 1)[-1])
        row = {"segment_id": f"{physical_id}:{path.stem}", "physical_cell_id": physical_id, "cell_id": physical_id, "source_id": "ch_batterygen", "root_scenario_id": mapping[physical_id]["root_scenario_id"], "cycle_index": charge_index, "observed_at": float(charge_index), "available_at": float(charge_index), "time_basis": "published_charge_snippet_number_not_physical_aging_cycle", "time_unit": "s", "sensor_level": "vehicle_pack", "provenance": "public_generated", "chemistry": chemistry, "protocol_id": "generated_vehicle_charging", "raw_ref": f"{archive_ref}#{'/'.join(path.parts[-4:])}" if archive_ref else str(path.resolve()), "raw_member_sha256": sha256_file(path), "quality_flags": ["generator_mother_identity_unknown"], "input_kind": "measured_generated_pack_statistics", "efficiency_label_status": "unavailable", "time_s": frame.TIME.to_list(), "voltage_V": frame.SUM_VOLTAGE.to_list(), "current_A": frame.SUM_CURRENT.to_list(), "temperature_C": ((frame.MAX_TEMP + frame.MIN_TEMP) / 2).to_list(), "phase": ["charge"] * len(frame), "sample_count": len(frame)}
        for name in sorted(needed):
            values = pd.to_numeric(frame[name], errors="coerce").to_numpy(float)
            finite = values[np.isfinite(values)]
            row[f"{name}_mean"] = float(np.mean(finite)) if len(finite) else None
            row[f"{name}_std"] = float(np.std(finite)) if len(finite) else None
        delta = (frame.MAX_CELL_VOLT - frame.MIN_CELL_VOLT).to_numpy(float)
        row["cell_voltage_spread_mean_V"] = _finite(np.nanmean(delta))
        segments.append(row)
        targets.append({"physical_cell_id": physical_id, "source_id": "ch_batterygen", "segment_id": row["segment_id"], "cycle_index": charge_index, "target_name": "fault", "value": classes[category], "unit": "class", "class_name": category, "target_definition_id": "ch-batterygen-v1-published-generated-fault-class-v2", "target_basis": "published_generator_fault_category_vehicle_pack", "observed_at": float(charge_index), "available_at": float(charge_index), "label_status": "available", "label_source": row["raw_ref"], "origin": "public_generated"})
        provenance.append({"source_id": "ch_batterygen", "path": str(path.resolve()), "sha256": row["raw_member_sha256"], "bytes": path.stat().st_size, "parser_version": PARSER_VERSION, "origin": "public_generated"})
    return ParsedDataset(identity, pd.DataFrame(), pd.DataFrame(segments), pd.DataFrame(targets), exclusions, provenance), split


def freeze_group_split(identity: pd.DataFrame, *, seed: int = 20261001, ratios: tuple[float, ...] = (.6, .15, .1, .15), group_column: str = "physical_cell_id") -> dict[str, Any]:
    if len(ratios) != 4 or any(x < 0 for x in ratios) or not np.isclose(sum(ratios), 1):
        raise ValueError("train/dev/calibration/final ratios must sum to one")
    if group_column not in identity or identity[group_column].isna().any():
        raise ValueError("split requires known physical/vehicle/root identities")
    groups = sorted(identity[group_column].unique(), key=lambda group: hashlib.sha256(f"{seed}:{group}".encode()).hexdigest())
    if any(_protected_identity(group) for group in groups):
        raise ValueError("protected identity may not enter V2 development splits")
    counts = np.floor(np.asarray(ratios) * len(groups)).astype(int)
    # Largest remainder avoids a split changing with input row repetition.
    remainder = len(groups) - counts.sum()
    fractional = np.asarray(ratios) * len(groups) - counts
    for index in np.argsort(-fractional, kind="stable")[:remainder]:
        counts[index] += 1
    mapping, cursor = {}, 0
    for split, count in zip(("train", "dev", "calibration", "final"), counts):
        for group in groups[cursor:cursor + count]:
            mapping[str(group)] = split
        cursor += count
    return {"schema_version": "physical-split-v2", "group_column": group_column, "seed": seed, "ratios": list(ratios), "assignments": mapping, "counts": {split: list(mapping.values()).count(split) for split in ("train", "dev", "calibration", "final")}, "final_policy": "sealed until preregistered comparison; not for selection", "protected_xjtu_cells": sorted(PROTECTED_XJTU)}


def visible_prefix(rows: pd.DataFrame, cutoff: float, *, physical_cell_id: str | None = None) -> pd.DataFrame:
    """Use a server-known numeric source-time cutoff; deny future labels."""
    if "available_at" not in rows:
        raise ValueError("availability timestamp is required")
    selected = rows[rows["available_at"] <= cutoff]
    if physical_cell_id is not None:
        selected = selected[selected["physical_cell_id"] == physical_cell_id]
    denied = {"cycle_life", "eol_cycle", "final_root_cause", "hidden_truth", "future_capacity_Ah", "terminal_cycle"}
    return selected.drop(columns=[name for name in denied if name in selected]).copy()


def audit_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    failures, checks = [], []
    loaded = {}
    for name, record in manifest.get("tables", {}).items():
        table_path = Path(record["path"])
        if not table_path.is_absolute():
            table_path = path.parent / table_path
        if not table_path.exists() or sha256_file(table_path) != record["sha256"]:
            failures.append(f"{name}: missing or changed hash")
            continue
        frame = pd.read_parquet(table_path)
        loaded[name] = frame
        checks.append(f"{name}: hash verified, {len(frame)} rows")
        if len(frame) != record["rows"]:
            failures.append(f"{name}: count mismatch")
        if "physical_cell_id" in frame and frame["physical_cell_id"].map(_protected_identity).any():
            failures.append(f"{name}: protected XJTU identity")
        if "available_at" in frame and "observed_at" in frame and (frame["available_at"] < frame["observed_at"]).any():
            failures.append(f"{name}: label available before observation")
        if set(frame.columns) & {"cycle_life", "hidden_truth", "future_capacity_Ah"}:
            failures.append(f"{name}: forbidden future feature field")
    split_path = Path(manifest["split_manifest"])
    if not split_path.is_absolute():
        split_path = path.parent / split_path
    split = json.loads(split_path.read_text())
    identities = set(loaded.get("identity_map", pd.DataFrame()).get("physical_cell_id", []))
    if identities != set(split.get("assignments", {})):
        failures.append("identity coverage differs from frozen split")
    identity_frame = loaded.get("identity_map", pd.DataFrame())
    group_column = split.get("group_column", "physical_cell_id")
    if group_column in identity_frame:
        for _, group in identity_frame.groupby(group_column, dropna=False):
            assigned = {split["assignments"].get(str(cell)) for cell in group.physical_cell_id}
            if len(assigned) > 1:
                failures.append("one source vehicle/root/physical identity occurs in multiple splits")
    # Scan explicit query dependencies where supplied; target labels are not
    # model inputs and do not themselves have to precede each prediction.
    for query in manifest.get("queries", []):
        for evidence in query.get("feature_dependencies", []):
            if evidence["available_at"] > query["visible_cutoff"]:
                failures.append(f"query {query.get('query_id')}: future feature dependency")
            if evidence.get("physical_cell_id", query.get("physical_cell_id")) != query.get("physical_cell_id"):
                failures.append(f"query {query.get('query_id')}: identity mixing")
    independent_groups = int(identity_frame[group_column].nunique()) if group_column in identity_frame else len(identities)
    measured = loaded.get("cycles", pd.DataFrame())
    if measured.empty:
        measured = loaded.get("segments", pd.DataFrame())
    measured_objects = int(measured.physical_cell_id.nunique()) if "physical_cell_id" in measured else 0
    return {"schema_version": "data-audit-v2", "manifest_sha256": sha256_file(path), "passed": not failures, "checks": checks, "failures": failures, "registered_objects": len(identities), "independent_objects": independent_groups, "measured_objects": measured_objects, "group_column": group_column, "split_counts": split.get("counts"), "scope": "structural provenance, grouped split and explicit query dependency audit; not proof of scientific model performance"}
