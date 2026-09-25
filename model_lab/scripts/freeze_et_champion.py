"""Freeze the nested-CV ET winner on all 21 development cells, never heldout."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor

from model_lab.modeling.frozen_et import load_champion, predict_soh
from model_lab.scripts.train_nested_cv import ROOT, VIEW, digest, fit_transform, load_development, matched, weights


NESTED = ROOT / "reports/round3/nested/summary.json"
OUT = ROOT / "reports/round3/champion_v3"


def selected_leaf(summary: dict) -> tuple[int, list[int]]:
    values = [int(s["config_values"]["min_samples_leaf"]) for s in summary["selections"]
              if s["method"] == "extra_trees_matched"]
    if len(values) != 3:
        raise ValueError("three nested ET selections required")
    frequency = Counter(values)
    return max(frequency, key=lambda leaf: (frequency[leaf], leaf)), values


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"preserve existing champion: {OUT}")
    data, heldout = load_development(VIEW)
    nested = json.loads(NESTED.read_text())
    if nested.get("failed_runs") or nested.get("no_result"):
        raise ValueError("nested comparison incomplete")
    leaf, fold_leaves = selected_leaf(nested)
    all_train = np.arange(len(data.soh))
    sx, sr, stats = fit_transform(data, all_train)
    z = matched(sx, sr, data.log_ratio)
    logy = np.log(data.soh)
    mu = float(logy.mean()); target_scale = max(float(logy.std()), .02)
    models = []
    for seed in (0, 1, 2):
        model = ExtraTreesRegressor(n_estimators=300, min_samples_leaf=leaf,
                                    random_state=seed, n_jobs=4)
        model.fit(z, (logy-mu)/target_scale, sample_weight=weights(data.cell))
        models.append(model)
    raw = np.concatenate((data.x, data.reference))
    train_min = np.nanmin(np.where(np.isfinite(raw), raw, np.nan), axis=0)
    train_max = np.nanmax(np.where(np.isfinite(raw), raw, np.nan), axis=0)
    artifact = {"schema": "xjtu_71d_partial_cc_v1", "models": models,
                "median": stats["median"], "mean": stats["mean"], "scale": stats["scale"],
                "target_mu": mu, "target_scale": target_scale,
                "train_min": train_min, "train_max": train_max,
                "seeds": [0, 1, 2], "n_estimators": 300, "min_samples_leaf": leaf}
    OUT.mkdir(parents=True)
    path = OUT / "et_champion.joblib"
    joblib.dump(artifact, path)
    reloaded = load_champion(path)
    direct = np.exp(np.mean([mu + target_scale * model.predict(z) for model in models], axis=0))
    confirmed = predict_soh(data.x, data.reference, data.log_ratio, reloaded)
    np.testing.assert_allclose(confirmed, direct, rtol=1e-10, atol=1e-12)
    sources = {"view_bundle": digest(VIEW), "nested_summary": digest(NESTED),
               "nested_host_verification": digest(ROOT / "reports/round3/nested/host_metric_verification.json"),
               "external_protocol": digest(ROOT / "docs/ROUND3_EXTERNAL_PROTOCOL.md"),
               "feature_map": digest(ROOT / "data/physical_curve_features.py"),
               "inference_code": digest(ROOT / "modeling/frozen_et.py"),
               "trainer_code": digest(Path(__file__)),
               "nested_runner_code": digest(ROOT / "scripts/train_nested_cv.py")}
    task = "XJTU 3.7-4.1V RPT-relative SOH, matched 71D view, initial measured diagnostic calibration"
    report = {"scope": "frozen development-only ET; no XJTU holdout scores",
              "task": task, "task_sha256": hashlib.sha256(task.encode()).hexdigest(),
              "source_hashes": sources, "artifact_sha256": digest(path),
              "fold_selected_leaves": fold_leaves, "frozen_leaf": leaf,
              "seeds": [0, 1, 2], "trees_per_seed": 300,
              "train_cells": len(set(data.cell)), "train_rows": len(data.soh),
              "heldout_cells_unscored": heldout,
              "cpu_reload_max_abs_difference": float(np.max(np.abs(confirmed-direct))),
              "development_fit_mae_pp_not_validation": float(np.mean(np.abs((confirmed-data.soh)*100)))}
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
