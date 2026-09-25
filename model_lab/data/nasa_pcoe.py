"""Versioned NASA PCoE archive, chronology, and measured-capacity audit helpers."""
from __future__ import annotations

import hashlib
import io
import re
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import numpy as np

from model_lab.data.physical_curve_features import curve_features
from model_lab.data.xjtu_raw import build_cc_window


PARSER_VERSION = "nasa_pcoe_prefix_v1_conservative_temperature"
MAX_NESTED_BYTES = 128 * 1024 * 1024
MAX_MAT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
CELL_NAME = re.compile(r"B\d{4}\.mat$", re.IGNORECASE)


def safe_member(info: zipfile.ZipInfo, limit: int) -> None:
    path = PurePosixPath(info.filename)
    if (path.is_absolute() or ".." in path.parts or "\\" in info.filename
            or info.file_size > limit or info.file_size < 0):
        raise ValueError(f"unsafe or oversized ZIP member: {info.filename}")
    mode = (info.external_attr >> 16) & 0xffff
    if stat.S_IFMT(mode) == stat.S_IFLNK:
        raise ValueError(f"symlink ZIP member: {info.filename}")
    if info.compress_size and info.file_size / info.compress_size > 100:
        raise ValueError(f"excessive ZIP expansion: {info.filename}")


def archive_inventory(path: Path) -> dict:
    records = {}; readmes = []; total = 0; mat_members = 0
    with zipfile.ZipFile(path) as outer:
        outer_zips = [item for item in outer.infolist() if item.filename.lower().endswith(".zip")]
        if len(outer_zips) != 6:
            raise ValueError("expected six nested NASA archives")
        for parent in outer.infolist():
            safe_member(parent, MAX_NESTED_BYTES)
            total += parent.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("archive expansion budget exceeded")
            if parent.is_dir():
                continue
            if parent not in outer_zips:
                raise ValueError(f"unexpected outer member: {parent.filename}")
            with zipfile.ZipFile(io.BytesIO(outer.read(parent))) as nested:
                for item in nested.infolist():
                    safe_member(item, MAX_MAT_BYTES)
                    total += item.file_size
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("nested archive expansion budget exceeded")
                    if item.is_dir():
                        continue
                    raw = nested.read(item)
                    entry = {"archive": parent.filename, "member": item.filename,
                             "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    if item.filename.lower().endswith(".txt"):
                        readmes.append(entry)
                        continue
                    if not CELL_NAME.fullmatch(PurePosixPath(item.filename).name):
                        raise ValueError(f"unexpected nested member: {item.filename}")
                    mat_members += 1
                    cell_id = PurePosixPath(item.filename).stem.upper()
                    records.setdefault(cell_id, []).append(entry)
    conflicts = {cell: copies for cell, copies in records.items()
                 if len({copy["sha256"] for copy in copies}) != 1}
    if conflicts:
        raise ValueError(f"conflicting physical cell bytes: {sorted(conflicts)}")
    return {"parser_version": PARSER_VERSION, "mat_members": mat_members,
            "distinct_cells": len(records), "expanded_bytes_checked": total,
            "duplicate_cells": {cell: entries for cell, entries in records.items() if len(entries) > 1},
            "readmes": readmes, "cells": records}


def matlab_start(value) -> datetime:
    parts = np.asarray(value, dtype=float).reshape(-1)
    if len(parts) != 6 or not np.isfinite(parts).all():
        raise ValueError("invalid MATLAB operation timestamp")
    year, month, day, hour, minute = map(int, parts[:5])
    if any(abs(parts[j] - int(parts[j])) > 1e-8 for j in range(5)):
        raise ValueError("noninteger MATLAB date fields")
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc) + timedelta(seconds=float(parts[5]))


def as_vector(data: dict, key: str) -> np.ndarray:
    return np.asarray(data[key], dtype=np.float64).reshape(-1)


def nasa_charge_view(operation: dict) -> tuple[np.ndarray | None, float | None, dict]:
    """Return exact XJTU 71D order, masking any temperature gap conservatively."""
    data = operation["data"]
    try:
        t = as_vector(data, "Time") / 60.
        v = as_vector(data, "Voltage_measured")
        current = as_vector(data, "Current_measured")
        if not (len(t) == len(v) == len(current)):
            return None, None, {"reason": "unequal_charge_signal_lengths"}
        temperature = np.full(len(t), np.nan)
        if "Temperature_measured" in data:
            provided = as_vector(data, "Temperature_measured")
            temperature[:min(len(t), len(provided))] = provided[:len(t)]
    except (KeyError, TypeError, ValueError):
        return None, None, {"reason": "missing_or_invalid_charge_signal"}
    mapped = {"relative_time_min": t, "voltage_V": v, "current_A": current,
              "temperature_C": temperature}
    window = build_cc_window(mapped)
    if not window.valid:
        return None, None, {"reason": window.reason}
    first = int(window.source_start_index); last = int(window.source_end_index)
    if not (0 <= first < last < len(t)):
        return None, None, {"reason": "invalid_prefix_cutoff"}
    temperature_gap = not np.isfinite(temperature[first:last+1]).all()
    if temperature_gap:
        window.temperature_rel_C[:] = np.nan
        window.finite_mask[:, 2] = 0
    fraction = (3.7-v[first]) / (v[first+1]-v[first]) if v[first+1] > v[first] else np.nan
    if not np.isfinite(fraction) or not -1e-6 <= fraction <= 1+1e-6:
        return None, None, {"reason": "invalid_lower_bracket"}
    absolute_temp = temperature[first] + fraction*(temperature[first+1]-temperature[first])
    if temperature_gap:
        absolute_temp = np.nan
    lower_current = current[first] + fraction*(current[first+1]-current[first])
    channels = np.stack((window.elapsed_min, window.incremental_charge_Ah,
                         window.current_A, window.temperature_rel_C), axis=1)
    flat = np.concatenate((channels.reshape(-1), np.isfinite(channels).reshape(-1))).astype(np.float32)[None, :]
    features = np.concatenate((curve_features(flat)[0], [absolute_temp, lower_current])).astype(np.float32)
    return features, float(window.charge_Ah), {"reason": "ok", "source_start_index": first,
        "source_end_index": last, "window_charge_Ah": float(window.charge_Ah),
        "temperature_missing_in_prefix": bool(temperature_gap),
        "parser_version": PARSER_VERSION}


def integrated_discharge(operation: dict, cutoff_v: float = 2.7) -> dict:
    """Integrate negative measured A over seconds through first real crossing."""
    data = operation["data"]
    summary = data.get("Capacity")
    try:
        summary = float(np.asarray(summary, dtype=float).reshape(-1)[0])
    except (TypeError, ValueError, IndexError):
        summary = None
    try:
        t = as_vector(data, "Time")
        v = as_vector(data, "Voltage_measured")
        current = as_vector(data, "Current_measured")
    except (KeyError, TypeError, ValueError):
        return {"status": "missing_discharge_signal", "summary_capacity_Ah": summary}
    if len(t) < 2 or not (len(t) == len(v) == len(current)) or not (
            np.isfinite(t).all() and np.isfinite(v).all() and np.isfinite(current).all()
            and np.all(np.diff(t) > 0)):
        return {"status": "invalid_discharge_signal", "summary_capacity_Ah": summary}
    if v[0] <= cutoff_v:
        return {"status": "starts_at_or_below_2p7", "summary_capacity_Ah": summary}
    negative = np.maximum(-current, 0.)
    terminal = float(np.trapezoid(negative, t) / 3600.)
    hit = np.flatnonzero((v[:-1] > cutoff_v) & (v[1:] <= cutoff_v))
    if not len(hit):
        return {"status": "protocol_terminal_capacity_not_standard_2p7",
                "summary_capacity_Ah": summary, "terminal_integrated_Ah": terminal,
                "min_discharge_voltage_V": float(v.min())}
    index = int(hit[0]); fraction = float((v[index]-cutoff_v)/(v[index]-v[index+1]))
    cross_t = t[index] + fraction*(t[index+1]-t[index])
    cross_i = current[index] + fraction*(current[index+1]-current[index])
    q = float((np.trapezoid(negative[:index+1], t[:index+1]) +
               .5*(negative[index]+max(-cross_i, 0.))*(cross_t-t[index])) / 3600.)
    if not np.isfinite(q) or q <= 0:
        return {"status": "nonpositive_integrated_2p7", "summary_capacity_Ah": summary}
    return {"status": "integrated_2p7", "integrated_2p7_Ah": q,
            "terminal_integrated_Ah": terminal, "summary_capacity_Ah": summary,
            "summary_minus_2p7_relative": (summary-q)/q if summary is not None and np.isfinite(summary) else None,
            "crossing_source_index": index+1, "crossing_time_s": float(cross_t),
            "min_discharge_voltage_V": float(v.min())}


def pair_operations(operations: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pair in recorded order only where strictly increasing starts support it."""
    rows = []; pairs = []; pending = None; latest_start = None
    for index, operation in enumerate(operations):
        kind = str(operation.get("type", "unknown")).lower()
        row = {"operation_index": index+1, "type": kind}
        try:
            start = matlab_start(operation["time"])
            row["start_utc"] = start.isoformat()
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            row.update({"status": "invalid_operation_time", "detail": repr(error)})
            pending = None; rows.append(row); continue
        if latest_start is not None and start <= latest_start:
            row["status"] = "nonmonotonic_operation_start"
            pending = None; rows.append(row); continue
        latest_start = start
        if kind == "charge":
            view, charge, audit = nasa_charge_view(operation)
            row.update(audit)
            row["status"] = "charge_ready" if view is not None else "charge_window_rejected"
            if pending is not None:
                row["superseded_charge_index"] = pending["index"]
            pending = {"index": index+1, "start": start, "view": view, "charge_Ah": charge,
                       "audit": audit} if view is not None else None
        elif kind == "discharge":
            label = integrated_discharge(operation)
            row.update(label)
            row["capacity_status"] = label["status"]
            row["paired_charge_index"] = pending["index"] if pending else None
            if pending is None:
                row["status"] = "unpaired_discharge"
            else:
                row["status"] = label["status"]
                pairs.append({"charge": pending, "discharge_index": index+1,
                              "discharge_start": start, "label": label})
            pending = None
        elif kind == "impedance":
            row["status"] = "intervening_impedance"
        else:
            row["status"] = "unknown_operation_type"
            pending = None
        rows.append(row)
    return rows, pairs


def first_eligible_reference(pairs: list[dict]) -> dict | None:
    return next((pair for pair in pairs if pair["label"]["status"] == "integrated_2p7"), None)
