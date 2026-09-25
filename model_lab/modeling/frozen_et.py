"""Bounded 71D partial-charge SOH inference for a locally trusted ET artifact."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler


FEATURE_DIM = 71
TEMPERATURE_COLUMNS = np.r_[48:64, 69]
REQUIRED_COLUMNS = np.array([i for i in range(FEATURE_DIM) if i not in set(TEMPERATURE_COLUMNS)])


def load_champion(path: str | Path) -> dict:
    artifact = joblib.load(path)
    if artifact.get("schema") != "xjtu_71d_partial_cc_v1" or len(artifact.get("models", [])) != 3:
        raise ValueError("incompatible frozen champion")
    for key in ("median", "mean", "scale", "train_min", "train_max"):
        if np.asarray(artifact[key]).shape != (FEATURE_DIM,):
            raise ValueError(f"invalid {key} shape")
    return artifact


def validate_inputs(current: np.ndarray, reference: np.ndarray,
                    log_window_ratio: np.ndarray, max_rows: int = 8192):
    x = np.asarray(current, dtype=np.float32)
    r = np.asarray(reference, dtype=np.float32)
    q = np.asarray(log_window_ratio, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != FEATURE_DIM or r.shape != x.shape:
        raise ValueError("expected matched N x 71 current/reference arrays")
    if q.shape != (len(x),) or not 0 < len(x) <= max_rows:
        raise ValueError("invalid or unbounded row count")
    if not np.isfinite(q).all() or np.max(np.abs(q)) > 20:
        raise ValueError("invalid observed charge ratio")
    for name, view in (("current", x), ("reference", r)):
        if not np.isfinite(view[:, REQUIRED_COLUMNS]).all():
            raise ValueError(f"nonfinite required {name} features")
        if np.isinf(view[:, TEMPERATURE_COLUMNS]).any():
            raise ValueError(f"infinite {name} temperatures")
        if np.any(view[:, [66, 70]] <= 0):
            raise ValueError(f"nonpositive observed {name} current")
        if np.any(view[:, 16:32] < -1e-4):
            raise ValueError(f"negative {name} charge fractions")
    return x, r, q


def predict_soh(current: np.ndarray, reference: np.ndarray,
                log_window_ratio: np.ndarray, artifact: dict) -> np.ndarray:
    """Return SOH only; callers supply pre-cutoff, schema-matched observations."""
    x, r, q = validate_inputs(current, reference, log_window_ratio)
    median = np.asarray(artifact["median"])
    mean = np.asarray(artifact["mean"])
    scale = np.asarray(artifact["scale"])
    if np.any(scale <= 0) or not np.isfinite(scale).all():
        raise ValueError("invalid train-only scaler")
    scaler = StandardScaler()
    scaler.mean_ = mean
    scaler.scale_ = scale
    scaler.var_ = scale ** 2
    scaler.n_features_in_ = FEATURE_DIM
    scaler.n_samples_seen_ = len(artifact["models"])
    x = scaler.transform(np.where(np.isfinite(x), x, median)).astype(np.float32)
    r = scaler.transform(np.where(np.isfinite(r), r, median)).astype(np.float32)
    z = np.concatenate((x, r, x-r, q.astype(np.float32)[:, None]), axis=1)
    logs = [artifact["target_mu"] + artifact["target_scale"] * model.predict(z)
            for model in artifact["models"]]
    result = np.exp(np.mean(logs, axis=0))
    if not np.isfinite(result).all() or np.any(result <= 0):
        raise ValueError("invalid model output")
    return result


def outside_training_range(current: np.ndarray, reference: np.ndarray,
                           log_window_ratio: np.ndarray, artifact: dict) -> dict:
    x, r, _ = validate_inputs(current, reference, log_window_ratio)
    lo = np.asarray(artifact["train_min"]); hi = np.asarray(artifact["train_max"])
    observed = np.stack((x, r), axis=1)
    finite = np.isfinite(observed)
    outside = finite & ((observed < lo) | (observed > hi))
    return {"rows_with_any_outside_feature": int(outside.any(axis=(1, 2)).sum()),
            "total_rows": len(x), "outside_feature_fraction": float(outside.sum() / finite.sum()),
            "per_feature_outside_counts": outside.sum(axis=(0, 1)).astype(int).tolist()}
