"""Development-only optimization for a source-aware hierarchical M1 candidate.

This file intentionally never opens a final bundle.  It compares structural
variants on the immutable development bundle and records every candidate,
including candidates that fail the two-source gate.  The candidate is a
quantile-tree M1 family: target normalization is source-specific, while the
tree sharing level is varied between protocol/domain, source and global.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor

from model_lab.modeling.v2.contracts import load_dataset, sha256_file


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "battery_platform/research/joint_xjtu_matr/bundles/development/combined/features.json"
OUT = ROOT / "battery_platform/research/joint_xjtu_matr/optimization"


def cell_macro(y: np.ndarray, p: np.ndarray, cells: np.ndarray, sources: np.ndarray) -> dict:
    result = {}
    for source in ("xjtu", "matr"):
        source_mask = sources == source
        values = []
        rmses = []
        per_cell = []
        for cell in sorted(set(cells[source_mask])):
            mask = source_mask & (cells == cell)
            error = (p[mask] - y[mask]) * 100.0
            values.append(float(np.abs(error).mean()))
            rmses.append(float(np.sqrt(np.mean(error * error))))
            per_cell.append({"cell": cell, "mae_pp": values[-1], "rmse_pp": rmses[-1], "rows": int(mask.sum())})
        result[source] = {
            "objects": len(values),
            "mae_pp": float(np.mean(values)) if values else None,
            "rmse_pp": float(np.mean(rmses)) if rmses else None,
            "per_cell": per_cell,
        }
    return result


def normalize_features(x: np.ndarray, train: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    median = np.nanmedian(np.where(np.isfinite(x[train]), x[train], np.nan), axis=0)
    median = np.where(np.isfinite(median), median, 0.0)
    x = np.where(np.isfinite(x), x, median)
    mean = x[train].mean(axis=0)
    scale = x[train].std(axis=0)
    scale[scale < 1e-6] = 1.0
    return ((x - mean) / scale).astype(np.float32)


def source_target(y: np.ndarray, sources: np.ndarray, train: np.ndarray):
    means, scales = {}, {}
    for source in ("xjtu", "matr"):
        values = np.log(y[train & (sources == source)])
        means[source] = float(values.mean())
        scales[source] = float(max(values.std(), 0.02))
    mu = np.asarray([means[s] for s in sources], dtype=np.float64)
    sd = np.asarray([scales[s] for s in sources], dtype=np.float64)
    return (np.log(y) - mu) / sd, means, scales


def estimator(kind: str, seed: int, n_estimators: int, depth: int, min_leaf: int):
    if kind == "gbdt":
        return GradientBoostingRegressor(
            loss="quantile", alpha=0.5, random_state=seed,
            n_estimators=n_estimators, max_depth=depth, min_samples_leaf=min_leaf,
            learning_rate=0.03,
        )
    if kind == "extra_trees":
        return ExtraTreesRegressor(
            n_estimators=n_estimators, max_depth=None if depth == 0 else depth,
            min_samples_leaf=min_leaf, random_state=seed, n_jobs=1,
        )
    if kind == "random_forest":
        return RandomForestRegressor(
            n_estimators=n_estimators, max_depth=None if depth == 0 else depth,
            min_samples_leaf=min_leaf, random_state=seed, n_jobs=1,
        )
    raise ValueError(kind)


def fit_predict(
    x: np.ndarray,
    y: np.ndarray,
    split: np.ndarray,
    cells: np.ndarray,
    sources: np.ndarray,
    domains: np.ndarray,
    variant: str,
    kind: str,
    seed: int,
    n_estimators: int,
    depth: int,
    min_leaf: int,
    residual_weight: float,
    weighting: str = "cell",
):
    train, dev, calibration = split == "train", split == "dev", split == "calibration"
    target, means, scales = source_target(y, sources, train)
    x_norm = normalize_features(x, train)
    domain_one_hot = np.column_stack([domains == d for d in sorted(set(domains))]).astype(np.float32)
    source_one_hot = np.column_stack([sources == s for s in ("xjtu", "matr")]).astype(np.float32)
    shared_x = np.concatenate([x_norm, source_one_hot], axis=1)
    weights = np.ones(train.sum(), dtype=np.float64)
    unique, inverse, counts = np.unique(cells[train], return_inverse=True, return_counts=True)
    weights = 1.0 / counts[inverse]
    weights = weights / weights.mean()
    all_weights = np.zeros(len(y), dtype=np.float64)
    all_weights[train] = weights
    if weighting == "source_cell_balanced":
        # Equalize source totals after cell balancing so the shared head
        # optimizes the reported source-macro objective.
        for source in ("xjtu", "matr"):
            source_mask = train & (sources == source)
            source_sum = all_weights[source_mask].sum()
            if source_sum > 0:
                all_weights[source_mask] *= 0.5 / source_sum
        all_weights[train] /= all_weights[train].mean()
    elif weighting != "cell":
        raise ValueError(weighting)

    models = []
    prediction = np.zeros(len(y), dtype=np.float64)

    if variant == "domain":
        groups = domains
    elif variant == "source":
        groups = sources
    elif variant == "global":
        groups = np.asarray(["global"] * len(y))
    elif variant == "source_plus_domain_residual":
        groups = sources
    else:
        raise ValueError(variant)

    for group in sorted(set(groups)):
        fit_mask = train & (groups == group)
        if fit_mask.sum() < max(8, min_leaf * 2):
            continue
        base = estimator(kind, seed, n_estimators, depth, min_leaf)
        if variant == "global":
            base_x = shared_x[fit_mask]
        else:
            base_x = x_norm[fit_mask]
        base.fit(base_x, target[fit_mask], sample_weight=all_weights[fit_mask])
        pred_x = shared_x if variant == "global" else x_norm
        base_prediction = base.predict(pred_x)
        if variant != "source_plus_domain_residual":
            prediction += np.where(groups == group, base_prediction, 0.0)
        else:
            prediction += np.where(groups == group, base_prediction, 0.0)
        models.append({"group": group, "n_train": int(fit_mask.sum())})

    if variant == "source_plus_domain_residual":
        # Shrunk domain residuals around a source-level shared head.  The
        # residual is fit in the same source-normalized log-SOH coordinate.
        for domain in sorted(set(domains)):
            domain_train = train & (domains == domain)
            source = sources[domain_train][0] if domain_train.any() else None
            source_train = train & (sources == source)
            if not domain_train.any() or domain_train.sum() < max(8, min_leaf * 2):
                continue
            source_model = estimator(kind, seed, n_estimators, depth, min_leaf)
            source_model.fit(x_norm[source_train], target[source_train], sample_weight=all_weights[source_train])
            source_fit = source_model.predict(x_norm[source_train])
            residual_y = target[source_train] - source_fit
            domain_model = estimator("gbdt", seed, max(20, n_estimators // 2), max(1, depth - 1), min_leaf)
            domain_model.fit(x_norm[source_train], residual_y, sample_weight=all_weights[source_train])
            residual = domain_model.predict(x_norm)
            prediction += np.where(domains == domain, residual_weight * residual, 0.0)
            models.append({"residual_domain": domain, "n_train": int(domain_train.sum())})

    # Convert source-normalized log predictions to SOH ratio.
    pred = np.asarray([np.exp(means[s] + scales[s] * value) for s, value in zip(sources, prediction)])
    metrics = {}
    for name, mask in (("dev", dev), ("calibration", calibration)):
        metrics[name] = cell_macro(y[mask], pred[mask], cells[mask], sources[mask])
    return metrics, models


def main() -> None:
    manifest, arrays = load_dataset(BUNDLE)
    forbidden = {"final", "final-test", "sealed", "protected"}
    found = {row.get("split") for row in manifest["rows"] if row.get("split") in forbidden}
    if found:
        raise RuntimeError(f"development-only optimizer received forbidden rows: {sorted(found)}")
    rows = manifest["rows"]
    x = arrays["features"].astype(np.float32)
    y = arrays["y_soh"].astype(np.float64)
    split = np.asarray([row["split"] for row in rows])
    cells = np.asarray([row["physical_cell_id"] for row in rows])
    sources = np.asarray([row["source_id"] for row in rows])
    domains = np.asarray([
        "::".join(str(row.get(key)) for key in ("source_id", "chemistry", "protocol_id"))
        for row in rows
    ])
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = []
    for variant in ("domain", "source", "global", "source_plus_domain_residual"):
        for kind in ("gbdt", "extra_trees", "random_forest"):
            for n_estimators in (40, 80, 160):
                for depth in ((1, 2, 3) if kind == "gbdt" else (0, 4, 8)):
                    for min_leaf in (1, 2, 3, 5):
                        if kind != "gbdt" and n_estimators != 80:
                            continue
                        for residual_weight in ((0.0, 0.25, 0.5, 0.75, 1.0) if variant == "source_plus_domain_residual" else (0.0,)):
                            for seed in (0, 1, 2):
                                metrics, models = fit_predict(
                                    x, y, split, cells, sources, domains,
                                    variant, kind, seed, n_estimators, depth,
                                    min_leaf, residual_weight,
                                )
                                record = {
                                    "variant": variant, "kind": kind, "seed": seed,
                                    "n_estimators": n_estimators, "depth": depth,
                                    "min_leaf": min_leaf, "residual_weight": residual_weight,
                                    "metrics": metrics, "models": models,
                                }
                                candidates.append(record)
                                if len(candidates) % 100 == 0:
                                    print(f"evaluated {len(candidates)} candidates", flush=True)
    receipt = {
        "scope": "development-only H-M1 structural optimization; final excluded",
        "bundle": str(BUNDLE), "bundle_sha256": sha256_file(BUNDLE),
        "final_labels_used_for_selection": False,
        "forbidden_splits": ["final", "final-test", "sealed", "protected"],
        "selection_metric": "mean of source cell-macro dev MAE; calibration reported separately",
        "candidate_count": len(candidates), "candidates": candidates,
    }
    (OUT / "hm1_development_candidates_20261002.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({"candidate_count": len(candidates), "output": str(OUT / "hm1_development_candidates_20261002.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
