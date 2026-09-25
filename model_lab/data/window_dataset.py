from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


DEFAULT_DERIVED_FEATURES = (
    "voltage mean", "voltage std", "voltage kurtosis", "voltage skewness", "CC Q", "CC charge time", "voltage slope", "voltage entropy",
    "current mean", "current std", "current kurtosis", "current skewness", "CV Q", "CV charge time", "current slope", "current entropy",
)
FORBIDDEN_FEATURE_TOKENS = ("capacity", "soh", "pcl", "rul", "eol", "cycle_life", "cyclelife", "life", "future", "label", "target")


@dataclass(frozen=True)
class CellTable:
    cell_id: str
    frame: pd.DataFrame
    feature_columns: tuple[str, ...]
    values: np.ndarray
    capacity: np.ndarray
    label_provenance: tuple[str, ...]


def _validate_feature_names(feature_columns: Sequence[str], available: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(feature_columns)
    missing = [name for name in selected if name not in available]
    if missing:
        raise ValueError(f"feature allowlist contains missing columns: {missing}")
    forbidden = [name for name in selected if any(token in name.lower().replace(" ", "_") for token in FORBIDDEN_FEATURE_TOKENS)]
    if forbidden:
        raise ValueError(f"target/derived fields cannot be input features: {forbidden}")
    if not selected:
        raise ValueError("explicit non-empty feature allowlist is required")
    return selected


def load_canonical_csv(paths: Iterable[Path], feature_allowlist: Sequence[str] | None = None) -> list[CellTable]:
    ordered_paths = sorted(Path(path) for path in paths)
    if not ordered_paths:
        raise ValueError("no canonical cells")
    cells: list[CellTable] = []
    seen_ids: set[str] = set()
    for path in ordered_paths:
        frame = pd.read_csv(path)
        if "capacity" not in frame.columns:
            raise ValueError(f"{path} lacks capacity target")
        if "cycle_id" not in frame.columns:
            frame["cycle_id"] = np.arange(len(frame), dtype=np.int64)
        frame = frame.sort_values("cycle_id", kind="stable").reset_index(drop=True)
        cell_id = str(frame["cell_id"].iloc[0]) if "cell_id" in frame else path.stem
        if not cell_id or cell_id in seen_ids:
            raise ValueError(f"duplicate or empty physical cell_id: {cell_id!r}")
        seen_ids.add(cell_id)
        if feature_allowlist is None:
            raise ValueError("feature_allowlist/schema is required; automatic numeric-column selection is disabled")
        selected = _validate_feature_names(feature_allowlist, frame.columns)
        if not np.isfinite(float(frame.loc[0, "capacity"])) or float(frame.loc[0, "capacity"]) <= 0:
            raise ValueError(f"{path} has invalid first observed reference capacity")
        values = frame.loc[:, selected].to_numpy(dtype=np.float32, copy=True)
        capacity = frame.loc[:, "capacity"].to_numpy(dtype=np.float64, copy=True)
        provenance = tuple(frame["label_provenance"].fillna("unknown").astype(str)) if "label_provenance" in frame else tuple("unknown" for _ in range(len(frame)))
        cells.append(CellTable(cell_id=cell_id, frame=frame, feature_columns=selected, values=values, capacity=capacity, label_provenance=provenance))
    if any(cells[0].feature_columns != cell.feature_columns for cell in cells):
        raise ValueError("all cells must expose the same explicit feature schema")
    return cells


class PrefixWindowDataset(Dataset):
    """Build one prefix window on demand from cached per-cell arrays."""

    def __init__(self, cells: list[CellTable], indices: list[tuple[int, int]], scaler: dict[str, np.ndarray], history: int = 32) -> None:
        self.cells, self.indices, self.scaler, self.history = cells, indices, scaler, history
        self.dim = len(cells[0].feature_columns)
        self._normalized: list[np.ndarray] = []
        self._finite: list[np.ndarray] = []
        for table in cells:
            finite = np.isfinite(table.values)
            normalized = (np.where(finite, table.values, scaler["mean"]) - scaler["mean"]) / scaler["std"]
            self._normalized.append(normalized.astype(np.float32, copy=False))
            self._finite.append(finite.astype(np.float32, copy=False))

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, item: int) -> dict[str, torch.Tensor | str | int]:
        cell_idx, row_idx = self.indices[item]
        table = self.cells[cell_idx]
        values = self._normalized[cell_idx]
        finite = self._finite[cell_idx]
        current = values[row_idx]
        ref = values[0]
        start = max(0, row_idx - self.history)
        past = values[start:row_idx]
        past_finite = finite[start:row_idx]
        temporal_mask = np.ones(len(past), dtype=np.float32)
        if len(past) < self.history:
            padded = np.zeros((self.history, self.dim), dtype=np.float32)
            padded[-len(past):] = past if len(past) else 0
            padded_finite = np.zeros((self.history, self.dim), dtype=np.float32)
            padded_finite[-len(past):] = past_finite if len(past) else 0
            mask_full = np.zeros(self.history, dtype=np.float32)
            mask_full[-len(past):] = temporal_mask if len(past) else 0
            past, past_finite, temporal_mask = padded, padded_finite, mask_full
        else:
            past, past_finite, temporal_mask = past[-self.history:], past_finite[-self.history:], temporal_mask[-self.history:]
        capacity = float(table.capacity[row_idx])
        reference_capacity = float(table.capacity[0])
        if not np.isfinite(reference_capacity) or reference_capacity <= 0:
            raise ValueError(f"invalid early-calibrated reference for cell {table.cell_id}")
        target = capacity / reference_capacity if np.isfinite(capacity) else np.nan
        quality_gate = np.array([float((past_finite * temporal_mask[:, None]).mean())], dtype=np.float32)
        return {"current": torch.from_numpy(current), "reference": torch.from_numpy(ref), "history": torch.from_numpy(past), "history_mask": torch.from_numpy(temporal_mask), "feature_mask": torch.from_numpy(past_finite), "quality_gate": torch.from_numpy(quality_gate), "target": torch.tensor(target, dtype=torch.float32), "label_provenance": table.label_provenance[row_idx], "cell_id": table.cell_id, "cycle_id": int(table.frame.loc[row_idx, "cycle_id"]), "row_index": row_idx}


def split_cell_indices(cells: list[CellTable], seed: int = 0) -> tuple[list[int], list[int], list[int]]:
    del seed
    order = sorted(range(len(cells)), key=lambda i: cells[i].cell_id)
    n = len(order)
    if n < 3:
        raise ValueError("at least three independent physical cells are required for train/validation/test")
    n_train = max(1, int(round(n * 0.6)))
    n_val = max(1, int(round(n * 0.2)))
    if n_train + n_val >= n:
        n_train, n_val = n - 2, 1
    return order[:n_train], order[n_train:n_train+n_val], order[n_train+n_val:]


def fit_scaler(cells: list[CellTable], train_ids: list[int]) -> dict[str, np.ndarray]:
    values = np.concatenate([cells[i].values.astype(np.float64, copy=False) for i in train_ids], axis=0)
    mean = np.nanmean(values, axis=0)
    std = np.nanstd(values, axis=0)
    mean[~np.isfinite(mean)] = 0.0
    std[~np.isfinite(std) | (std < 1e-8)] = 1.0
    return {"mean": mean.astype(np.float32), "std": std.astype(np.float32)}


def eligible_indices(cells: list[CellTable], cell_ids: list[int]) -> list[tuple[int, int]]:
    output = []
    for cell_idx in cell_ids:
        for row_idx in range(1, len(cells[cell_idx].capacity)):
            if np.isfinite(float(cells[cell_idx].capacity[row_idx])):
                output.append((cell_idx, row_idx))
    return output
