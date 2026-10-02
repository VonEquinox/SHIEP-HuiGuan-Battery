"""Fit the frozen H-M1 source-residual quantile candidate on development only.

H-M1 pools all protocols within each source to reduce the small-XJTU protocol
head variance.  It fits a source-level q05/q50/q95 gradient-boosting backbone,
then a shrunken source residual stage.  The residual stage is a source adapter
and is intentionally not described as a separate protocol head.  Final rows
are rejected before loading arrays.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from model_lab.modeling.v2.baselines import gb_to_dict, predict_gb
from model_lab.modeling.v2.contracts import load_dataset, sha256_file


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "battery_platform/research/joint_xjtu_matr/bundles/development/combined/features.json"
OUT = ROOT / "battery_platform/research/joint_xjtu_matr/optimization/hm1_quantile_development_20261002.json"
MODEL_DIR = OUT.parent / "hm1_quantile_models_20261002"
SEEDS = (0, 1, 2)
QUANTILES = (0.05, 0.5, 0.95)
N_ESTIMATORS = 160
DEPTH = 3
MIN_LEAF = 5
RESIDUAL_ESTIMATORS = 80
RESIDUAL_DEPTH = 2
RESIDUAL_WEIGHT = 1.0


def preprocess(x: np.ndarray, train: np.ndarray):
    x = np.asarray(x, dtype=np.float64)
    median = np.nanmedian(np.where(np.isfinite(x[train]), x[train], np.nan), axis=0)
    median = np.where(np.isfinite(median), median, 0.0)
    x = np.where(np.isfinite(x), x, median)
    mean = x[train].mean(axis=0)
    scale = x[train].std(axis=0)
    scale[scale < 1e-6] = 1.0
    return ((x - mean) / scale).astype(np.float32), {
        "median": median.tolist(), "mean": mean.tolist(), "scale": scale.tolist()
    }


def apply_preprocessor(x: np.ndarray, state: dict) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    median = np.asarray(state["median"], dtype=np.float64)
    mean = np.asarray(state["mean"], dtype=np.float64)
    scale = np.asarray(state["scale"], dtype=np.float64)
    x = np.where(np.isfinite(x), x, median)
    return ((x - mean) / scale).astype(np.float32)


def weights(cells: np.ndarray, train: np.ndarray) -> np.ndarray:
    values = cells[train]
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    result = np.zeros(len(cells), dtype=np.float64)
    result[train] = 1.0 / counts[inverse]
    result[train] /= result[train].mean()
    return result


def source_normalization(y: np.ndarray, sources: np.ndarray, train: np.ndarray):
    means, scales = {}, {}
    for source in ("xjtu", "matr"):
        values = np.log(y[train & (sources == source)])
        means[source] = float(values.mean())
        scales[source] = float(max(values.std(), 0.02))
    mu = np.asarray([means[s] for s in sources], dtype=np.float64)
    sd = np.asarray([scales[s] for s in sources], dtype=np.float64)
    return (np.log(y) - mu) / sd, means, scales


def macro_metrics(y, prediction, quantiles, cells, sources, mask):
    q50 = prediction[:, 1]
    result = {}
    for source in ("xjtu", "matr"):
        source_mask = mask & (sources == source)
        maes, rmses, coverages, widths, per_cell = [], [], [], [], []
        for cell in sorted(set(cells[source_mask])):
            cmask = source_mask & (cells == cell)
            error = (q50[cmask] - y[cmask]) * 100.0
            lower = prediction[cmask, 0]
            upper = prediction[cmask, 2]
            maes.append(float(np.abs(error).mean()))
            rmses.append(float(np.sqrt(np.mean(error * error))))
            coverages.append(float(np.mean((y[cmask] >= lower) & (y[cmask] <= upper))))
            widths.append(float(np.mean((upper - lower) * 100.0)))
            per_cell.append({
                "cell": cell, "rows": int(cmask.sum()),
                "mae_pp": maes[-1], "rmse_pp": rmses[-1],
                "coverage_90": coverages[-1], "width_pp": widths[-1],
            })
        result[source] = {
            "objects": len(maes),
            "mae_pp": float(np.mean(maes)), "rmse_pp": float(np.mean(rmses)),
            "coverage_90": float(np.mean(coverages)), "width_pp": float(np.mean(widths)),
            "per_cell": per_cell,
        }
    return result


def fit_seed(x, y, split, cells, sources, seed):
    train = split == "train"
    x_norm, preprocessing = preprocess(x, train)
    target, means, scales = source_normalization(y, sources, train)
    sample_weights = weights(cells, train)
    model_record = {"seed": seed, "quantiles": {}, "residuals": {}}
    prediction = np.full((len(y), 3), np.nan, dtype=np.float64)
    for source in ("xjtu", "matr"):
        source_train = train & (sources == source)
        source_indices = np.flatnonzero(source_train)
        model_record["quantiles"][source] = {}
        model_record["residuals"][source] = {}
        for q_index, q in enumerate(QUANTILES):
            base = GradientBoostingRegressor(
                loss="quantile", alpha=q, random_state=seed,
                n_estimators=N_ESTIMATORS, max_depth=DEPTH,
                min_samples_leaf=MIN_LEAF, learning_rate=0.03,
            )
            base.fit(x_norm[source_train], target[source_train], sample_weight=sample_weights[source_train])
            base_train = base.predict(x_norm[source_train])
            residual_target = target[source_train] - base_train
            residual = GradientBoostingRegressor(
                loss="quantile", alpha=q, random_state=seed,
                n_estimators=RESIDUAL_ESTIMATORS, max_depth=RESIDUAL_DEPTH,
                min_samples_leaf=MIN_LEAF, learning_rate=0.03,
            )
            residual.fit(x_norm[source_train], residual_target, sample_weight=sample_weights[source_train])
            source_mask = sources == source
            prediction[source_mask, q_index] = (
                np.asarray([means[source] for _ in range(source_mask.sum())])
            )
            values = predict_gb(gb_to_dict(base), x_norm[source_mask])
            correction = predict_gb(gb_to_dict(residual), x_norm[source_mask])
            prediction[source_mask, q_index] = np.exp(
                means[source] + scales[source] * (values + RESIDUAL_WEIGHT * correction)
            )
            model_record["quantiles"][source][str(q)] = gb_to_dict(base)
            model_record["residuals"][source][str(q)] = gb_to_dict(residual)
        prediction[source_mask] = np.sort(prediction[source_mask], axis=1)
    metrics = {
        split_name: macro_metrics(y, prediction, QUANTILES, cells, sources, split == split_name)
        for split_name in ("dev", "calibration")
    }
    model_record["source_log_mean"] = means
    model_record["source_log_scale"] = scales
    model_record["preprocessing"] = preprocessing
    return prediction, metrics, model_record


def replay_record(x: np.ndarray, sources: np.ndarray, record: dict) -> np.ndarray:
    """Replay the exported numerical recipe and return sorted q05/q50/q95."""
    x_norm = apply_preprocessor(x, record["preprocessing"])
    prediction = np.full((len(x), 3), np.nan, dtype=np.float64)
    for source in ("xjtu", "matr"):
        mask = sources == source
        for q_index, q in enumerate(QUANTILES):
            base = predict_gb(record["quantiles"][source][str(q)], x_norm[mask])
            correction = predict_gb(record["residuals"][source][str(q)], x_norm[mask])
            prediction[mask, q_index] = np.exp(
                record["source_log_mean"][source]
                + record["source_log_scale"][source]
                * (base + RESIDUAL_WEIGHT * correction)
            )
        prediction[mask] = np.sort(prediction[mask], axis=1)
    return prediction


def main() -> None:
    manifest, arrays = load_dataset(BUNDLE)
    rows = manifest["rows"]
    forbidden = {"final", "final-test", "sealed", "protected"}
    found = {row.get("split") for row in rows if row.get("split") in forbidden}
    if found:
        raise RuntimeError(f"H-M1 development run received forbidden rows: {sorted(found)}")
    x = arrays["features"].astype(np.float32)
    y = arrays["y_soh"].astype(np.float64)
    split = np.asarray([row["split"] for row in rows])
    cells = np.asarray([row["physical_cell_id"] for row in rows])
    sources = np.asarray([row["source_id"] for row in rows])
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for seed in SEEDS:
        prediction, metrics, model_record = fit_seed(x, y, split, cells, sources, seed)
        model_path = MODEL_DIR / f"seed{seed}.json"
        model_path.write_text(json.dumps(model_record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        replayed = replay_record(x, sources, model_record)
        replay_error = float(np.max(np.abs(replayed - prediction)))
        results.append({
            "seed": seed, "metrics": metrics, "model": str(model_path),
            "model_sha256": sha256_file(model_path),
            "replay_max_abs_soh": replay_error,
        })
        print(seed, metrics["dev"]["xjtu"]["mae_pp"], metrics["dev"]["matr"]["mae_pp"], flush=True)
    receipt = {
        "scope": "H-M1 source-residual quantile prototype; development/feedback only",
        "bundle": str(BUNDLE), "bundle_sha256": sha256_file(BUNDLE),
        "final_labels_used_for_selection": False, "selection_split": "dev",
        "calibration_role": "stability-only feedback; no final selection",
        "architecture": {
            "source_pooled_backbone": True, "source_residual_stage": True,
            "source_normalized_log_soh": True, "quantiles": list(QUANTILES),
            "n_estimators": N_ESTIMATORS, "depth": DEPTH, "min_leaf": MIN_LEAF,
            "residual_estimators": RESIDUAL_ESTIMATORS, "residual_depth": RESIDUAL_DEPTH,
            "residual_weight": RESIDUAL_WEIGHT, "weighting": "cell-balanced",
        },
        "references": {
            "joint_mlp_dev_xjtu_mae_pp": 0.7297388163511473,
            "joint_mlp_dev_matr_mae_pp": 5.330279534841793,
            "current_m1_dev_xjtu_mae_pp": 0.6095458466379114,
            "current_m1_dev_matr_mae_pp": 1.7021475435912425,
            "historical_final_mlp_xjtu_mae_pp": 0.633793572584788,
        },
        "results": results,
    }
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(OUT), "seeds": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
