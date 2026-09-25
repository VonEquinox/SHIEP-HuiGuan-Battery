"""Pure, bounded-memory helpers for the official XJTU MAT schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


RAW_FIELDS = ("system_time", "relative_time_min", "voltage_V", "current_A", "capacity_Ah", "power_Wh", "temperature_C", "description")
SUMMARY_FIELDS = ("charge_capacity_Ah", "discharge_capacity_Ah", "charge_power_Wh", "discharge_power_Wh", "charge_median_voltage", "discharge_median_voltage", "charge_mean_voltage", "discharge_mean_voltage", "cycle_life", "description")


@dataclass(frozen=True)
class WindowResult:
    valid: bool
    reason: str
    elapsed_min: np.ndarray
    current_A: np.ndarray
    temperature_rel_C: np.ndarray
    incremental_charge_Ah: np.ndarray
    voltage_grid_V: np.ndarray
    finite_mask: np.ndarray
    duration_min: float
    charge_Ah: float
    segment_index: int | None
    source_start_index: int | None
    source_end_index: int | None


def as_float_1d(value: Any) -> np.ndarray:
    """Convert one MATLAB numeric vector to a float64 1-D view."""
    arr = np.asarray(value).reshape(-1)
    return arr.astype(np.float64, copy=False)


def as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "SU":
            return "".join(str(x) for x in value.reshape(-1)).strip()
        if value.size == 1:
            return as_text(value.reshape(-1)[0])
    return str(value).strip()


def description_family(description: str) -> str:
    text = description.lower()
    if "test capacity" in text or "rpt" in text or "reference performance" in text:
        return "diagnostic"
    return "routine"


def split_time_segments(relative_time_min: np.ndarray) -> tuple[list[slice], int]:
    """Split on non-finite values and time resets; preserve original order."""
    t = np.asarray(relative_time_min, dtype=np.float64).reshape(-1)
    if not len(t):
        return [], 0
    breaks = np.flatnonzero(~np.isfinite(t[:-1]) | ~np.isfinite(t[1:]) | (np.diff(t) <= 0)) + 1
    starts = np.r_[0, breaks]
    ends = np.r_[breaks, len(t)]
    segments = [slice(int(start), int(end)) for start, end in zip(starts, ends) if end - start >= 2]
    return segments, max(0, len(starts) - 1)


def _empty_result(reason: str, points: int, lower: float, upper: float) -> WindowResult:
    return WindowResult(False, reason, np.full(points, np.nan), np.full(points, np.nan), np.full(points, np.nan), np.full(points, np.nan), np.linspace(lower, upper, points), np.zeros((points, 4), dtype=np.uint8), float("nan"), float("nan"), None, None, None)


def _contiguous_runs(mask: np.ndarray) -> Iterable[tuple[int, int]]:
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.r_[np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1, len(mask)]
    for start in starts:
        end_candidates = ends[ends > start]
        if len(end_candidates):
            yield int(start), int(end_candidates[0])


def build_cc_window(cycle: dict[str, Any], lower: float = 3.7, upper: float = 4.1, points: int = 64, positive_current_A: float = 0.05) -> WindowResult:
    """Extract one fixed CC voltage window without crossing resets or phases.

    Interpolation is confined to a monotonic voltage run inside one contiguous
    time segment. The full charge/discharge trajectory is never sorted.
    """
    try:
        t = as_float_1d(cycle["relative_time_min"])
        v = as_float_1d(cycle["voltage_V"])
        current = as_float_1d(cycle["current_A"])
        temp = as_float_1d(cycle["temperature_C"])
    except (KeyError, TypeError, ValueError):
        return _empty_result("missing_required_signal", points, lower, upper)
    n = min(len(t), len(v), len(current), len(temp))
    if n < 4:
        return _empty_result("too_short", points, lower, upper)
    t, v, current, temp = t[:n], v[:n], current[:n], temp[:n]
    segments, reset_count = split_time_segments(t)
    if not segments:
        return _empty_result("no_monotonic_time_segment", points, lower, upper)
    grid = np.linspace(lower, upper, points)
    for segment_index, segment in enumerate(segments):
        local_t, local_v, local_i, local_temp = t[segment], v[segment], current[segment], temp[segment]
        finite = np.isfinite(local_t) & np.isfinite(local_v) & np.isfinite(local_i)
        # Keep points bracketing the voltage limits. Filtering to [lower, upper]
        # first incorrectly requires exact floating-point boundary samples.
        candidate = finite & (local_i > positive_current_A)
        for start, end in _contiguous_runs(candidate):
            if end - start < 4:
                continue
            vv, tt, ii, tempv = local_v[start:end], local_t[start:end], local_i[start:end], local_temp[start:end]
            upper_hits = np.flatnonzero(vv >= upper)
            if not len(upper_hits) or vv[0] > lower:
                continue
            cutoff = int(upper_hits[0])
            lower_hits = np.flatnonzero(vv[:cutoff + 1] <= lower)
            if not len(lower_hits):
                continue
            begin = int(lower_hits[-1])
            vv, tt, ii, tempv = vv[begin:cutoff + 1], tt[begin:cutoff + 1], ii[begin:cutoff + 1], tempv[begin:cutoff + 1]
            if len(vv) < 4 or np.any(np.diff(tt) <= 0):
                continue
            # This task is explicitly a CC observation, not an arbitrary dynamic
            # charge. Check only the visible prefix, never later current values.
            if float(np.std(ii) / max(np.mean(ii), 1e-8)) > 0.1:
                continue
            if np.max(np.maximum.accumulate(vv) - vv) > 0.05:
                continue
            # First-passage voltage representation: retain successive record-high
            # samples in chronological order. Small measurement reversals do not
            # erase a valid charge. Do not sort samples across time/phase resets.
            keep = np.r_[True, vv[1:] > np.maximum.accumulate(vv)[:-1]]
            unique_idx = np.flatnonzero(keep)
            unique_v = vv[unique_idx]
            if len(unique_v) < 4 or unique_v[0] > lower or unique_v[-1] < upper:
                continue
            t_grid = np.interp(grid, unique_v, tt[unique_idx])
            i_grid = np.interp(grid, unique_v, ii[unique_idx])
            valid_temp = np.isfinite(tempv[unique_idx])
            if valid_temp.sum() >= 2 and valid_temp[0] and valid_temp[-1]:
                temp_grid = np.interp(grid, unique_v[valid_temp], tempv[unique_idx][valid_temp])
            else:
                temp_grid = np.full(points, np.nan)
            elapsed = t_grid - t_grid[0]
            # Integrate every visible raw time sample before resampling, rather
            # than approximating Coulomb counting from only 64 grid points.
            raw_q = np.r_[0.0, np.cumsum(0.5 * (ii[1:] + ii[:-1]) * np.diff(tt) / 60.0)]
            q = np.interp(t_grid, tt, raw_q)
            q -= q[0]
            finite_mask = np.stack([np.isfinite(elapsed), np.isfinite(i_grid), np.isfinite(temp_grid), np.isfinite(q)], axis=1).astype(np.uint8)
            valid = bool(finite_mask[:, [0, 1, 3]].all() and q[-1] > 0 and elapsed[-1] > 0)
            reason = "ok" if finite_mask.all() else "temperature_missing_masked"
            return WindowResult(valid, reason if valid else "invalid_time_or_charge", elapsed, i_grid, temp_grid - temp_grid[0], q, grid, finite_mask, float(elapsed[-1]), float(q[-1]), segment_index, int(segment.start + start + begin), int(segment.start + start + cutoff))
    reason = "time_reset_or_nonmonotonic_voltage" if reset_count else "cc_window_unavailable"
    return _empty_result(reason, points, lower, upper)


def finite_summary_label(summary: dict[str, Any], cycle_index_zero: int) -> float:
    values = as_float_1d(summary.get("discharge_capacity_Ah", []))
    if cycle_index_zero < 0 or cycle_index_zero >= len(values):
        return float("nan")
    value = float(values[cycle_index_zero])
    return value if np.isfinite(value) and value > 0 else float("nan")


def measured_discharge_audit(cycle: dict[str, Any], summary_capacity: float) -> dict[str, Any]:
    """Independent Coulomb-count check, kept in label metadata, never inputs."""
    t = as_float_1d(cycle.get("relative_time_min", []))
    i = as_float_1d(cycle.get("current_A", []))
    if len(t) != len(i) or len(t) < 2:
        return {"status": "unavailable"}
    best = 0.0
    for segment in split_time_segments(t)[0]:
        st, si = t[segment], i[segment]
        for a, b in _contiguous_runs(np.isfinite(st) & np.isfinite(si) & (si < -0.05)):
            if b-a >= 2:
                measured = float(-np.trapezoid(si[a:b], st[a:b]) / 60.0)
                best = max(best, measured)
    if best <= 0 or not np.isfinite(summary_capacity):
        return {"status": "unavailable", "integrated_discharge_Ah": best}
    return {"status": "checked", "integrated_discharge_Ah": best, "summary_discharge_Ah": summary_capacity, "relative_difference": abs(best-summary_capacity)/summary_capacity}


def audit_summary(summary: dict[str, Any], cycle_count: int, diagnostic_indices: list[int]) -> dict[str, Any]:
    report: dict[str, Any] = {"cycle_count": cycle_count, "summary_keys": sorted(str(k) for k in summary.keys()), "summary_length_mismatches": {}, "diagnostic_count": len(diagnostic_indices), "diagnostic_finite_discharge_capacity_count": 0, "diagnostic_capacity_values_Ah": []}
    for key in SUMMARY_FIELDS:
        if key in summary and key != "description":
            try:
                length = len(as_float_1d(summary[key]))
            except (TypeError, ValueError):
                continue
            if length not in (cycle_count, 1):
                report["summary_length_mismatches"][key] = length
    labels = [finite_summary_label(summary, i) for i in diagnostic_indices]
    report["diagnostic_finite_discharge_capacity_count"] = int(np.isfinite(labels).sum())
    report["diagnostic_capacity_values_Ah"] = [float(x) if np.isfinite(x) else None for x in labels]
    report["cycle_life_is_label_only"] = True
    return report
