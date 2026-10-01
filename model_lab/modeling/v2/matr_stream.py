"""Bounded readers for the official corrected MATLAB 7.3 MATR batches.

Only requested scalar metadata, summary vectors and a frozen prefix of raw
cycles are dereferenced.  HDF5 links and executable serialization are never
followed.  A batch array position is deliberately not called a channel.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import h5py
import numpy as np
import pandas as pd

from .data import ParsedDataset, build_survival_target, sha256_file

PARSER_VERSION = "matr-hdf5-stream-v2.1"
BATCH_IDS = ("2017-05-12", "2017-06-30", "2018-04-12")
CONTINUATIONS = tuple(zip(range(5), (7, 8, 9, 15, 16)))
AUTHOR_APPEND_COUNTS = (662, 981, 1060, 208, 482)
AUTHOR_SOURCE = "https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation/blob/master/LoadData.m"
AUTHOR_SOURCE_SHA256 = "7914333f0a963a0742d9fff340f1d4bc2ad912f1b04a236b3ae6c39fedd3623d"


def _child(group: h5py.Group, key: str) -> Any:
    link = group.get(key, getlink=True)
    if isinstance(link, (h5py.ExternalLink, h5py.SoftLink)):
        raise ValueError("linked HDF5 objects are not accepted")
    return group[key]


def _vector_size(node: h5py.Dataset, limit: int) -> int:
    if sum(dimension > 1 for dimension in node.shape) > 1:
        raise ValueError("expected a bounded MATLAB vector, not a multidimensional array")
    if node.size > limit:
        raise ValueError("MATLAB vector exceeds resource budget")
    return int(node.size)


def _ref_at(node: h5py.Dataset, index: int) -> Any:
    count = _vector_size(node, 200_000)
    if not 0 <= index < count:
        raise ValueError("MATLAB reference index outside struct array")
    if h5py.check_dtype(ref=node.dtype) is not h5py.Reference:
        raise ValueError("expected object reference, not region reference")
    ref = node[np.unravel_index(index, node.shape)] if node.shape else node[()]
    if not ref:
        raise ValueError("null MATLAB object reference")
    return node.file[ref]


def _unwrap(node: Any) -> Any:
    for _ in range(12):
        if isinstance(node, h5py.Dataset) and h5py.check_dtype(ref=node.dtype):
            if node.size != 1:
                return node
            node = _ref_at(node, 0)
        else:
            return node
    raise ValueError("MATLAB reference depth exceeds limit")


@dataclass(frozen=True)
class _Struct:
    group: h5py.Group
    index: int = 0
    count: int = 1

    def field(self, key: str) -> Any | None:
        if key not in self.group:
            return None
        node = _child(self.group, key)
        if isinstance(node, h5py.Dataset) and h5py.check_dtype(ref=node.dtype):
            count = _vector_size(node, 200_000)
            if count == self.count:
                return _unwrap(_ref_at(node, self.index))
            if self.count == 1:
                return _unwrap(node)
            raise ValueError(f"inconsistent MATLAB struct reference field {key}")
        if self.count != 1:
            raise ValueError(f"non-reference field in MATLAB struct array: {key}")
        return _unwrap(node)


def _struct_count(node: h5py.Group, anchor: str) -> int:
    dataset = _child(node, anchor)
    if isinstance(dataset, h5py.Dataset) and h5py.check_dtype(ref=dataset.dtype):
        return _vector_size(dataset, 200_000)
    return 1


def _batch_views(handle: h5py.File) -> list[_Struct]:
    for key in handle:
        # Metadata inspection never reads a measurement payload.
        _child(handle, key)
    node = _unwrap(_child(handle, "batch"))
    if isinstance(node, h5py.Group):
        count = _struct_count(node, "summary")
        return [_Struct(node, index, count) for index in range(count)]
    if isinstance(node, h5py.Dataset) and h5py.check_dtype(ref=node.dtype):
        count = _vector_size(node, 1_000)
        groups = [_unwrap(_ref_at(node, index)) for index in range(count)]
        if not all(isinstance(group, h5py.Group) for group in groups):
            raise ValueError("batch references must point to MATLAB struct groups")
        return [_Struct(group) for group in groups]
    raise ValueError("unsupported corrected MATLAB batch schema")


def _text(node: Any | None) -> str | None:
    if node is None:
        return None
    node = _unwrap(node)
    if not isinstance(node, h5py.Dataset):
        raise ValueError("identity/policy metadata is not a MATLAB character vector")
    _vector_size(node, 4_096)
    if node.dtype == np.dtype("uint32") and node.attrs.get("MATLAB_class") in (b"string", "string"):
        pointer = np.asarray(node[()]).reshape(-1)
        if len(pointer) != 6 or pointer[:4].tolist() != [0xDD000000, 2, 1, 1] or pointer[5] != 1:
            raise ValueError("unsupported MATLAB MCOS scalar string pointer")
        path = Path(node.file.filename)
        table = _mcos_strings(str(path), path.stat().st_mtime_ns, path.stat().st_size)
        if int(pointer[4]) not in table:
            raise ValueError("MCOS original string identity has no verified object binding")
        text = table[int(pointer[4])]
    elif node.dtype.kind in "ui" and node.attrs.get("MATLAB_class") in (b"char", "char"):
        values = np.asarray(node[()]).reshape(-1)
        text = "".join(chr(int(value)) for value in values if value)
    elif node.dtype.kind in "SU":
        values = np.asarray(node[()]).reshape(-1)
        text = "".join(value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in values)
    else:
        raise ValueError("identity metadata needs explicit original characters")
    return text.strip() or None


@lru_cache(maxsize=16)
def _mcos_strings(path: str, modification_ns: int, file_bytes: int) -> dict[int, str]:
    """Decode only original scalar string records, never MATLAB classes/code.

    The MCOS object/property table, rather than a guessed reference offset,
    resolves each object ID.  The format was checked against the original
    batch storage and the primary matio MCOS format implementation:
    https://github.com/tbeu/matio/blob/master/src/mcos.c
    """
    del modification_ns, file_bytes  # Immutable-file cache invalidation keys.
    with h5py.File(path, "r", rdcc_nbytes=1024**2) as handle:
        mcos = _child(_child(handle, "#subsystem#"), "MCOS")
        _vector_size(mcos, 2_000)
        node = _ref_at(mcos, 0)
        if not isinstance(node, h5py.Dataset) or node.dtype != np.dtype("uint8"):
            raise ValueError("unsupported MCOS metadata storage")
        _vector_size(node, 1024**2)
        blob = np.asarray(node[()]).reshape(-1).tobytes()
        if len(blob) < 40 or len(blob) % 4:
            raise ValueError("invalid bounded MCOS metadata header")
        words = np.frombuffer(blob, dtype="<u4")
        if words[0] != 2 or words[1] > 128:
            raise ValueError("unsupported MCOS format/string table")
        offsets = [int(value) for value in words[2:8]]
        if offsets != sorted(offsets) or offsets[0] < 40 or offsets[-1] > len(blob):
            raise ValueError("invalid MCOS region offsets")
        names = blob[40:offsets[0]].split(b"\0")[:int(words[1])]
        classes = np.frombuffer(blob[offsets[0]:offsets[1]], dtype="<u4")
        objects = np.frombuffer(blob[offsets[2]:offsets[3]], dtype="<u4")
        if len(classes) % 4 or len(objects) % 6 or len(objects) > 12_000:
            raise ValueError("unsupported MCOS object/class table shape")
        classes, objects = classes.reshape(-1, 4), objects.reshape(-1, 6)
        properties, cursor = {}, offsets[1] + 8
        while cursor < offsets[2]:
            if cursor + 16 > offsets[2]:
                raise ValueError("truncated MCOS scalar string property")
            prop = np.frombuffer(blob[cursor:cursor + 16], dtype="<u4")
            if prop[0] != 1 or prop[1] < 1 or prop[1] > len(names) or names[int(prop[1]) - 1] != b"any" or prop[2] != 1:
                raise ValueError("only primitive MCOS scalar string properties supported")
            properties[len(properties) + 1] = int(prop[3]) + 2
            cursor += 16
        result = {}
        for object_id, obj in enumerate(objects[1:], 1):
            class_id, save_id = int(obj[0]), int(obj[3])
            if class_id < 1 or class_id >= len(classes):
                raise ValueError("MCOS string object has invalid original class ID")
            name_id = int(classes[class_id, 1])
            if name_id < 1 or name_id > len(names) or names[name_id - 1] != b"string" or save_id not in properties:
                raise ValueError("MCOS object is not a verified primitive string")
            value_node = _ref_at(mcos, properties[save_id])
            if not isinstance(value_node, h5py.Dataset) or value_node.dtype != np.dtype("uint64"):
                raise ValueError("unsupported MCOS original string payload")
            _vector_size(value_node, 1_029)
            value = np.asarray(value_node[()]).reshape(-1)
            if len(value) < 5 or value[:4].tolist() != [1, 2, 1, 1] or value[4] > 4_096 or len(value) != 5 + (int(value[4]) + 3)//4:
                raise ValueError("invalid MCOS scalar UTF-16 payload")
            result[object_id] = value[5:].astype("<u8").tobytes()[:int(value[4])*2].decode("utf-16-le", errors="strict")
        return result


def _number(node: Any | None) -> str | None:
    if node is None:
        return None
    node = _unwrap(node)
    if isinstance(node, h5py.Dataset) and node.dtype.kind in "ifu" and node.size == 1:
        value = float(node[()])
        if np.isfinite(value) and value.is_integer():
            return str(int(value))
    return _text(node)


def _numeric(node: Any | None, *, limit: int) -> np.ndarray:
    node = _unwrap(node)
    if not isinstance(node, h5py.Dataset) or node.dtype.kind not in "ifu":
        raise ValueError("measurement must be a primitive numeric MATLAB vector")
    _vector_size(node, limit)
    return np.asarray(node[()], dtype=float).reshape(-1)


def _open(path: Path, stack: ExitStack) -> h5py.File:
    if path.suffix.lower() not in {".mat", ".h5", ".hdf5"} or not h5py.is_hdf5(path):
        raise ValueError("streaming parser requires MATLAB 7.3/HDF5; no pickle or full-batch fallback")
    if path.stat().st_size > 4 * 1024**3:
        raise ValueError("corrected MATLAB file exceeds 4 GiB budget")
    return stack.enter_context(h5py.File(path, "r", rdcc_nbytes=4 * 1024**2))


def _path_map(paths: Iterable[str | Path]) -> dict[str, Path]:
    result = {}
    for raw in paths:
        path = Path(raw).resolve()
        matches = [date for date in BATCH_IDS if date in path.name]
        if len(matches) != 1 or matches[0] in result:
            raise ValueError("unique original corrected batch dates required in filenames")
        result[matches[0]] = path
    return result


def inventory_matr_hdf5(paths: Iterable[str | Path], *, identity_mapping: Mapping[str, Mapping[str, Any]] | None = None, raw_sha256: Mapping[str, str] | None = None, repair_continuations: bool = True) -> dict[str, Any]:
    """Read original identity fields only, before summary/curve/target parsing.

    An external barcode mapping must explicitly attest an original-record
    binding, include an evidence reference, and match a channel when the raw
    MAT contains one.  Merely mapping struct position to channel is rejected.
    """
    files, records = _path_map(paths), []
    mappings = identity_mapping or {}
    with ExitStack() as stack:
        for batch_id, path in files.items():
            views = _batch_views(_open(path, stack))
            for index, view in enumerate(views):
                record_id = f"{batch_id}:record-{index + 1}"
                barcode = next((_text(view.field(key)) for key in ("barcode", "cell_id", "cellId") if view.field(key) is not None), None)
                channel = next((_number(view.field(key)) for key in ("channel", "channel_id", "channelId") if view.field(key) is not None), None)
                policy = next((_text(view.field(key)) for key in ("policy_readable", "policy") if view.field(key) is not None), "unknown")
                evidence, basis = f"{path}#batch/{index + 1}/barcode", "original_corrected_mat_barcode"
                if not barcode:
                    mapping = mappings.get(record_id, {})
                    if not mapping.get("verified_original_mapping") or not mapping.get("evidence_ref") or not mapping.get("barcode") or mapping.get("mapping_basis") == "index_equals_channel":
                        raise ValueError(f"{record_id}: original barcode missing; verified original mapping required")
                    if channel is not None and str(mapping.get("original_channel")) != channel:
                        raise ValueError(f"{record_id}: original channel disagrees with verified identity mapping")
                    barcode, evidence, basis = str(mapping["barcode"]), str(mapping["evidence_ref"]), "verified_external_original_record_mapping"
                canonical = barcode.strip().casefold()
                records.append({"source_id": "matr", "source_record_id": record_id, "physical_cell_id": f"matr:{canonical}", "source_cell_id": barcode, "source_identity": canonical, "batch_id": batch_id, "batch_index_zero": index, "batch_index_one": index + 1, "original_channel": channel, "protocol_id": policy or "unknown", "source_protocol_id": policy or "unknown", "identity_basis": basis, "identity_verified": True, "barcode_verified": True, "physical_cycles_known": True, "identity_evidence": evidence, "namespace": "experimental", "chemistry": "LFP", "nominal_capacity_Ah": 1.1, "manufacturer_model": "A123 Systems APR18650M1A"})
    by_record = {(record["batch_id"], record["batch_index_zero"]): record for record in records}
    joins = []
    if repair_continuations:
        for index, (first, second) in enumerate(CONTINUATIONS):
            a, b = by_record.get((BATCH_IDS[0], first)), by_record.get((BATCH_IDS[1], second))
            if not a or not b or a["source_identity"] != b["source_identity"]:
                raise ValueError("all five author continuation pairs require matching verified original identity")
            joins.append({"first_record_id": a["source_record_id"], "second_record_id": b["source_record_id"], "physical_cell_id": a["physical_cell_id"], "expected_second_raw_cycle_count": AUTHOR_APPEND_COUNTS[index], "author_evidence": AUTHOR_SOURCE})
    groups = {}
    for record in records:
        groups.setdefault(record["physical_cell_id"], []).append(record["source_record_id"])
    expected_duplicates = {frozenset((join["first_record_id"], join["second_record_id"])) for join in joins}
    if any(len(group) > 1 and frozenset(group) not in expected_duplicates for group in groups.values()):
        raise ValueError("duplicate physical identity outside the five verified continuation pairs")
    provenance = [{"source_id": "matr", "path": str(path), "bytes": path.stat().st_size, "sha256": (raw_sha256 or {}).get(str(path)) or sha256_file(path), "parser_version": PARSER_VERSION, "origin": "real_experimental", "scope": "complete official corrected MATLAB batch"} for path in files.values()]
    return {"schema_version": "matr-identity-inventory-v2", "records": records, "continuations": joins, "sources": provenance, "identity_created_before_numeric_targets": True, "batch_position_is_not_channel": True, "author_source": AUTHOR_SOURCE, "author_source_sha256": AUTHOR_SOURCE_SHA256}


def inventory_identity_frame(inventory: Mapping[str, Any]) -> pd.DataFrame:
    """Canonical physical identity catalog for the caller's preregistered split."""
    return pd.DataFrame(inventory["records"]).drop_duplicates("physical_cell_id").reset_index(drop=True)


def author_paper_selection(records: list[dict[str, Any]], *, exclude_unfinished_batch1: bool = True, require_all_batches: bool = True) -> dict[str, Any]:
    """Apply the actual author's sequential positions; retain full audit log."""
    batches = {batch: sorted([row for row in records if row["batch_id"] == batch], key=lambda row: row["batch_index_zero"]) for batch in BATCH_IDS}
    if require_all_batches and any(not batches[batch] for batch in BATCH_IDS):
        raise ValueError("paper selection requires all three complete corrected batches")
    removed = [{"source_record_id": f"{BATCH_IDS[2]}:record-38", "reason": "author_original_record38_collection_problem_channel46"}]
    b3 = [row for row in batches[BATCH_IDS[2]] if row["batch_index_zero"] != 37]
    if require_all_batches and (len(batches[BATCH_IDS[0]]), len(batches[BATCH_IDS[1]]), len(b3)) != (46, 43, 45):
        raise ValueError("paper selection requires all original records after the five verified joins and one collection exclusion")
    for row in b3:
        if row["terminal_capacity_Ah"] > .885:
            removed.append({"source_record_id": row["source_record_id"], "reason": "author_batch3_terminal_capacity_gt_0.885Ah"})
    b3 = [row for row in b3 if not row["terminal_capacity_Ah"] > .885]
    noisy_positions = {2, 39, 40}
    if require_all_batches and len(b3) <= max(noisy_positions):
        raise ValueError("author sequential noise indices unavailable; batch scope or identity repair incomplete")
    for position, row in enumerate(b3):
        if position in noisy_positions:
            removed.append({"source_record_id": row["source_record_id"], "reason": "author_noise_position_after_terminal_filter", "filtered_index_one": position + 1})
    b3 = [row for position, row in enumerate(b3) if position not in noisy_positions]
    b1 = batches[BATCH_IDS[0]]
    if exclude_unfinished_batch1:
        optional = {8, 10, 12, 13, 22}
        for row in b1:
            if row["batch_index_zero"] in optional:
                removed.append({"source_record_id": row["source_record_id"], "reason": "author_optional_unfinished_batch1_exclusion"})
        b1 = [row for row in b1 if row["batch_index_zero"] not in optional]
    combined = b1 + batches[BATCH_IDS[1]] + b3
    primary_count = len(b1) + len(batches[BATCH_IDS[1]])
    test_positions_one = set(range(1, primary_count + 1, 2)) | {84}
    order = [{"combined_index_one": position, "physical_cell_id": row["physical_cell_id"], "source_record_id": row["source_record_id"], "author_split": "primary_test" if position in test_positions_one else "train" if position <= primary_count else "secondary_test"} for position, row in enumerate(combined, 1)]
    return {"schema_version": "matr-verified-author-selection-v2", "status": "verified_author_rules_applied", "source_url": AUTHOR_SOURCE, "source_sha256": AUTHOR_SOURCE_SHA256, "optional_unfinished_batch1_excluded": exclude_unfinished_batch1, "selection_order": order, "physical_cell_ids": [row["physical_cell_id"] for row in combined], "counts": {"batch1": len(b1), "batch2": len(batches[BATCH_IDS[1]]), "batch3": len(b3), "total": len(combined)}, "exclusions": removed, "paper_output_convention": "first_below_0.88_summary_position_if_terminal_below_else_raw_cycle_count_plus_one", "survival_output_convention": "strict_0.88Ah_threshold_with_right_censoring"}


def _cycle_views(view: _Struct) -> list[_Struct]:
    node = view.field("cycles")
    if isinstance(node, h5py.Group):
        count = _struct_count(node, "t")
        return [_Struct(node, index, count) for index in range(count)]
    if isinstance(node, h5py.Dataset) and h5py.check_dtype(ref=node.dtype):
        return [_Struct(_unwrap(_ref_at(node, index))) for index in range(_vector_size(node, 200_000))]
    raise ValueError("raw cycles must be an original MATLAB struct array")


def parse_matr_hdf5(paths: Iterable[str | Path], inventory: Mapping[str, Any], *, max_segments_per_cell: int = 32, reference_cycle: int = 10, landmark_cycles: tuple[int, ...] = (10, 100), max_points_per_segment: int = 200_000, max_total_points: int = 20_000_000, author_paper_selection_enabled: bool = True, exclude_unfinished_batch1: bool = True, enforce_author_append_counts: bool = True, selected_physical_ids: Iterable[str] | None = None) -> ParsedDataset:
    """Parse summaries and a prefix of native curves without batch materialization.

    Call ``inventory_matr_hdf5`` and freeze the split before this function.
    Returned survival targets use repaired physical cycles and never the
    author's separate last-plus-one output convention.
    """
    if not 0 <= max_segments_per_cell <= 32 or not 2 <= max_points_per_segment <= 200_000 or max_total_points <= 0:
        raise ValueError("bounded raw-curve budgets required")
    if not inventory.get("identity_created_before_numeric_targets"):
        raise ValueError("identity inventory must precede measurement/target parsing")
    files = _path_map(paths)
    expected_paths = {row["path"] for row in inventory["sources"]}
    if {str(path) for path in files.values()} != expected_paths:
        raise ValueError("raw paths differ from frozen identity inventory")
    if any(Path(row["path"]).stat().st_size != row["bytes"] for row in inventory["sources"]):
        raise ValueError("raw bytes changed after frozen identity inventory")
    allowed = set(selected_physical_ids) if selected_physical_ids is not None else None
    raw_records, exclusions, segments, used_points = [], [], [], 0
    with ExitStack() as stack:
        views = {batch: _batch_views(_open(path, stack)) for batch, path in files.items()}
        for identity in inventory["records"]:
            if allowed is not None and identity["physical_cell_id"] not in allowed:
                continue
            # The author's known collection failure is excluded independently
            # of outcome filtering. Its identity stays in the preregistration.
            if identity["batch_id"] == BATCH_IDS[2] and identity["batch_index_zero"] == 37:
                exclusions.append({"source_record_id": identity["source_record_id"], "reason": "author_original_record38_collection_problem_channel46", "retained_identity_only": True})
                continue
            view = views[identity["batch_id"]][identity["batch_index_zero"]]
            original_barcode = _text(view.field("barcode"))
            if original_barcode and original_barcode.strip().casefold() != identity["source_identity"]:
                raise ValueError("original barcode differs from frozen identity inventory")
            summary = view.field("summary")
            if not isinstance(summary, h5py.Group):
                raise ValueError("summary must be a MATLAB struct")
            summary_view = _Struct(summary)
            numbers = _numeric(summary_view.field("cycle"), limit=100_000)
            capacity = _numeric(summary_view.field("QDischarge"), limit=100_000)
            if len(numbers) != len(capacity) or not len(numbers) or not np.isfinite(numbers).all() or np.any(np.diff(numbers) <= 0):
                raise ValueError(f"{identity['source_record_id']}: inconsistent/nonmonotonic physical summary cycles")
            raw_cycles = _cycle_views(view)
            if len(raw_cycles) != len(numbers):
                raise ValueError(f"{identity['source_record_id']}: raw cycle count differs from original summary")
            valid = np.isfinite(numbers) & np.isfinite(capacity) & (capacity > 0)
            if not valid.any():
                exclusions.append({"source_record_id": identity["source_record_id"], "reason": "no_measurable_positive_capacity"})
                continue
            rows = [{"physical_cell_id": identity["physical_cell_id"], "source_id": "matr", "source_record_id": identity["source_record_id"], "source_cycle_index": float(number), "source_summary_index_one": index + 1, "cycle_index": float(number), "capacity_Ah": float(measured), "physical_cycles_known": True, "nominal_capacity_Ah": 1.1, "soh_nominal": float(measured) / 1.1, "chemistry": "LFP", "protocol_id": identity["protocol_id"], "batch_id": identity["batch_id"], "diagnostic": True, "observed_at": float(number), "available_at": float(number), "time_basis": "original_corrected_summary_cycle", "raw_ref": f"{files[identity['batch_id']]}#batch/{identity['batch_index_one']}/summary", "quality_flags": ["capacity_above_150percent_nominal"] if measured > 1.65 else []} for index, (number, measured) in enumerate(zip(numbers, capacity)) if valid[index]]
            for original_key, column in (("QCharge", "charge_capacity_Ah"), ("IR", "source_internal_resistance"), ("Tmax", "temperature_max_C"), ("Tmin", "temperature_min_C"), ("Tavg", "temperature_mean_C"), ("chargetime", "source_charge_time_min")):
                node = summary_view.field(original_key)
                if node is None:
                    continue
                values = _numeric(node, limit=100_000)
                if len(values) != len(numbers):
                    raise ValueError(f"{identity['source_record_id']}: {original_key} summary length mismatch")
                for row in rows:
                    value = values[row["source_summary_index_one"] - 1]
                    row[column] = float(value) if np.isfinite(value) else None
            invalid = np.flatnonzero(~valid)
            exclusions.extend({"source_record_id": identity["source_record_id"], "source_summary_index_one": int(index + 1), "reason": "nonfinite_or_nonpositive_capacity_cycle"} for index in invalid)
            raw_records.append({**identity, "cycles": rows, "source_cycle_numbers": numbers, "capacity_vector": capacity, "raw_cycle_count": len(raw_cycles), "terminal_capacity_Ah": float(capacity[-1]), "raw_cycle_views": raw_cycles, "path": str(files[identity["batch_id"]]), "cycle_offset": 0.})
        lookup = {record["source_record_id"]: record for record in raw_records}
        removed = set()
        for join in inventory["continuations"]:
            first, second = lookup.get(join["first_record_id"]), lookup.get(join["second_record_id"])
            if not first and not second and allowed is not None:
                continue
            if not first or not second:
                raise ValueError("continuing physical cell requires both measurable source parts")
            if enforce_author_append_counts and second["raw_cycle_count"] != join["expected_second_raw_cycle_count"]:
                raise ValueError("continuation original cycle count differs from verified author append count")
            previous, following = first["cycles"][-1], second["cycles"][0]
            difference = abs(previous["capacity_Ah"] - following["capacity_Ah"])
            if difference > .1:
                raise ValueError("continuation failed measured capacity continuity")
            start, end = following["cycle_index"], previous["cycle_index"]
            offset = 0. if start == end + 1 else end + 1 - start if start in (0., 1.) else None
            if offset is None:
                raise ValueError("continuation has unexplained physical cycle gap")
            second["cycle_offset"] = offset
            for row in second["cycles"]:
                row["cycle_index"] += offset
                row["observed_at"] = row["available_at"] = row["cycle_index"]
            first["cycles"] += second["cycles"]
            first["capacity_vector"] = np.concatenate((first["capacity_vector"], second["capacity_vector"]))
            first["raw_cycle_count"] += second["raw_cycle_count"]
            first["terminal_capacity_Ah"] = second["terminal_capacity_Ah"]
            first["continuation_verified"] = True
            first["capacity_continuity_Ah"] = difference
            first["parts"] = [first.copy(), second]
            removed.add(second["source_record_id"])
        records = [record for record in raw_records if record["source_record_id"] not in removed]
        paper = author_paper_selection(records, exclude_unfinished_batch1=exclude_unfinished_batch1) if author_paper_selection_enabled else None
        selected_paper = set(paper["physical_cell_ids"]) if paper else set()
        identities, cycle_rows, target_rows = [], [], []
        for record in records:
            physical_id = record["physical_cell_id"]
            frame = pd.DataFrame(record["cycles"])
            if np.any(np.diff(frame.cycle_index) <= 0):
                raise ValueError("repaired physical cell has duplicate/nonmonotonic cycles")
            reference_rows = frame[(frame.cycle_index >= reference_cycle) & (frame.capacity_Ah <= 1.65)]
            reference = reference_rows.iloc[0] if not reference_rows.empty else None
            identities.append({key: value for key, value in record.items() if key in inventory["records"][0]} | {"continuation_verified": bool(record.get("continuation_verified")), "source_record_ids": [part["source_record_id"] for part in record.get("parts", [record])], "paper_reproduction": physical_id in selected_paper if paper else None, "survival_all_valid": True, "reference_capacity_Ah": float(reference.capacity_Ah) if reference is not None else None, "reference_cutoff": float(reference.cycle_index) if reference is not None else None})
            cycle_rows.extend(record["cycles"])
            survival = build_survival_target(frame.cycle_index, frame.capacity_Ah, threshold_Ah=.88, target_definition_id="matr-corrected-physical-nominal-80pct-0.88Ah-v2", inclusive=False)
            target_rows.append({"physical_cell_id": physical_id, "source_id": "matr", "target_basis": "1.1Ah_nominal_80percent", "label_source": "original_corrected_QDischarge", **survival})
            if reference is not None:
                target_rows.extend({"physical_cell_id": physical_id, "source_id": "matr", "cycle_index": float(row.cycle_index), "target_name": "soh", "value": float(row.capacity_Ah/reference.capacity_Ah), "unit": "ratio", "target_definition_id": "matr-corrected-frozen-visible-cycle10-reference-soh-v2", "target_basis": "first_valid_capacity_at_or_after_original_physical_cycle10", "reference_capacity_Ah": float(reference.capacity_Ah), "reference_cutoff": float(reference.cycle_index), "observed_at": float(row.cycle_index), "available_at": float(row.cycle_index), "label_status": "available", "label_source": row.raw_ref} for row in frame.itertuples() if row.cycle_index >= reference.cycle_index)
            if paper and physical_id in selected_paper:
                q = record["capacity_vector"]
                event = bool(np.isfinite(q[-1]) and q[-1] < .88)
                hits = np.flatnonzero(q < .88)
                target_rows.append({"physical_cell_id": physical_id, "source_id": "matr", "target_name": "author_paper_output", "value": int(hits[0] + 1) if event and len(hits) else int(record["raw_cycle_count"] + 1), "unit": "summary_position", "target_definition_id": "matr-author-paper-output-convention-v2", "target_basis": "author_original_LoadData_example", "is_survival_event": event, "last_plus_one_convention": not event, "label_status": "available", "label_source": AUTHOR_SOURCE, "observed_at": float(frame.cycle_index.iloc[-1]), "available_at": float(frame.cycle_index.iloc[-1])})
            # Original prefix plus preregistered cycle landmarks. Selection
            # depends on physical cycle ID, never capacity or model outcome.
            candidates = [(part, index, view) for part in record.get("parts", [record]) for index, view in enumerate(part["raw_cycle_views"])]
            landmark_positions = [position for position, (part, index, _) in enumerate(candidates) if part["source_cycle_numbers"][index] + part["cycle_offset"] in landmark_cycles]
            chosen = set(landmark_positions[:max_segments_per_cell])
            for position in range(len(candidates)):
                if len(chosen) >= max_segments_per_cell:
                    break
                chosen.add(position)
            for position in sorted(chosen):
                part, index, view = candidates[position]
                try:
                    t, voltage, current = (_numeric(view.field(key), limit=max_points_per_segment) for key in ("t", "V", "I"))
                    temperature = _numeric(view.field("T"), limit=max_points_per_segment) if view.field("T") is not None else np.full(len(t), np.nan)
                    if len(t) < 2 or len({len(t), len(voltage), len(current), len(temperature)}) != 1 or not np.isfinite(np.column_stack((t, voltage, current))).all() or np.any(np.diff(t) <= 0):
                        raise ValueError("invalid_native_curve_lengths_or_time")
                    extra_signals = {}
                    for key, column in (("Qd", "discharge_capacity_Ah"), ("Qc", "charge_capacity_Ah")):
                        node = view.field(key)
                        if node is not None:
                            values = _numeric(node, limit=max_points_per_segment)
                            if len(values) != len(t):
                                raise ValueError("native_capacity_signal_length_mismatch")
                            extra_signals[column] = [float(value) if np.isfinite(value) else None for value in values]
                except ValueError as error:
                    if "budget" in str(error) or "linked" in str(error):
                        raise
                    exclusions.append({"source_record_id": part["source_record_id"], "raw_cycle_index_one": index + 1, "reason": str(error)})
                    continue
                used_points += len(t)
                if used_points > max_total_points:
                    raise ValueError("selected raw curves exceed total resource budget")
                # Struct order is tied to the actual summary vector; source
                # cycles may start at 0 or 1 and are never invented from index.
                source_number = float(part["source_cycle_numbers"][index])
                cycle_number = source_number + part["cycle_offset"]
                segments.append({"segment_id": f"{physical_id}:corrected-{part['batch_id']}-{index + 1}", "physical_cell_id": physical_id, "cell_id": physical_id, "source_id": "matr", "cycle_index": cycle_number, "source_cycle_index": source_number, "physical_cycles_known": True, "observed_at": cycle_number, "available_at": cycle_number, "time_s": (t*60).tolist(), "voltage_V": voltage.tolist(), "current_A": current.tolist(), "temperature_C": [float(value) if np.isfinite(value) else None for value in temperature], "phase": ["charge" if value > .05 else "discharge" if value < -.05 else "rest" for value in current], "time_unit": "s", "source_time_unit": "min", "time_basis": "repaired_original_corrected_summary_cycle", "chemistry": "LFP", "protocol_id": record["protocol_id"], "source_protocol_id": record["source_protocol_id"], "sensor_level": "cell", "provenance": "real_experimental", "raw_ref": f"{part['path']}#batch/{part['batch_index_one']}/cycles/{index + 1}", "quality_flags": [], "sample_count": len(t), "reference_capacity_Ah": float(reference.capacity_Ah) if reference is not None else None, "reference_cutoff": float(reference.cycle_index) if reference is not None else None, "efficiency_label_status": "unavailable", **extra_signals})
    present = {row["physical_cell_id"] for row in identities}
    for identity in inventory["records"]:
        if identity["physical_cell_id"] in present:
            continue
        identities.append({**identity, "continuation_verified": False, "source_record_ids": [row["source_record_id"] for row in inventory["records"] if row["physical_cell_id"] == identity["physical_cell_id"]], "paper_reproduction": False if paper else None, "survival_all_valid": False, "reference_capacity_Ah": None, "reference_cutoff": None, "identity_only_reason": "source_collection_failure_or_unmeasurable_or_outside_declared_measurement_scope"})
        present.add(identity["physical_cell_id"])
    provenance = [{**row, "parser_version": PARSER_VERSION, "identity_inventory_before_measurement": True, "curve_selection": "original_prefix_plus_preregistered_physical_cycle_landmarks", "curve_landmarks": list(landmark_cycles), "max_segments_per_cell": max_segments_per_cell, "selected_raw_points": used_points, "author_paper_selection": paper} for row in inventory["sources"]]
    return ParsedDataset(pd.DataFrame(identities), pd.DataFrame(cycle_rows), pd.DataFrame(segments), pd.DataFrame(target_rows), exclusions + (paper["exclusions"] if paper else []), provenance)
