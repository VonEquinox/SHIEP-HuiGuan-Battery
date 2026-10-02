"""Run a small pre-registered H-M1 development/feedback comparison.

The broad grid is archived separately.  This runner fixes a short list before
reading its scores, includes source-balanced and cell-balanced training, and
never loads the final comparison bundle.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from model_lab.modeling.v2.contracts import load_dataset, sha256_file
from optimize_m1_development import BUNDLE, fit_predict


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "battery_platform/research/joint_xjtu_matr/optimization/hm1_selected_development_20261002.json"


CONFIGS = [
    {"name": "source_residual_extra_d8_l1", "variant": "source_plus_domain_residual", "kind": "extra_trees", "n_estimators": 80, "depth": 8, "min_leaf": 1, "residual_weight": 1.0},
    {"name": "source_residual_extra_d8_l2", "variant": "source_plus_domain_residual", "kind": "extra_trees", "n_estimators": 80, "depth": 8, "min_leaf": 2, "residual_weight": 1.0},
    {"name": "source_extra_d8_l1", "variant": "source", "kind": "extra_trees", "n_estimators": 80, "depth": 8, "min_leaf": 1, "residual_weight": 0.0},
    {"name": "source_residual_extra_unlimited_l1", "variant": "source_plus_domain_residual", "kind": "extra_trees", "n_estimators": 80, "depth": 0, "min_leaf": 1, "residual_weight": 1.0},
    {"name": "source_residual_gbdt_d3_l2", "variant": "source_plus_domain_residual", "kind": "gbdt", "n_estimators": 160, "depth": 3, "min_leaf": 2, "residual_weight": 1.0},
    {"name": "source_residual_gbdt_d3_l5", "variant": "source_plus_domain_residual", "kind": "gbdt", "n_estimators": 160, "depth": 3, "min_leaf": 5, "residual_weight": 1.0},
]


def main() -> None:
    manifest, arrays = load_dataset(BUNDLE)
    forbidden = {"final", "final-test", "sealed", "protected"}
    found = {row.get("split") for row in manifest["rows"] if row.get("split") in forbidden}
    if found:
        raise RuntimeError(f"development runner received forbidden rows: {sorted(found)}")
    rows = manifest["rows"]
    x = arrays["features"].astype(np.float32)
    y = arrays["y_soh"].astype(np.float64)
    split = np.asarray([row["split"] for row in rows])
    cells = np.asarray([row["physical_cell_id"] for row in rows])
    sources = np.asarray([row["source_id"] for row in rows])
    domains = np.asarray(["::".join(str(row.get(key)) for key in ("source_id", "chemistry", "protocol_id")) for row in rows])
    results = []
    for config in CONFIGS:
        for weighting in ("cell", "source_cell_balanced"):
            for seed in (0, 1, 2):
                metrics, models = fit_predict(
                    x, y, split, cells, sources, domains,
                    config["variant"], config["kind"], seed,
                    config["n_estimators"], config["depth"], config["min_leaf"],
                    config["residual_weight"], weighting=weighting,
                )
                results.append({**config, "weighting": weighting, "seed": seed, "metrics": metrics, "models": models})
                print(config["name"], weighting, seed, metrics["dev"]["xjtu"]["mae_pp"], metrics["dev"]["matr"]["mae_pp"], flush=True)
    receipt = {
        "scope": "H-M1 selected development/feedback comparison; final excluded",
        "bundle": str(BUNDLE),
        "bundle_sha256": sha256_file(BUNDLE),
        "final_labels_used_for_selection": False,
        "selection_split": "dev",
        "calibration_role": "stability-only feedback; not used to select the reported development winner",
        "xjtu_dev_reference_mlp_mae_pp": 0.7297388163511473,
        "matr_dev_reference_mlp_mae_pp": 5.330279534841793,
        "current_m1_dev_reference": {"xjtu_mae_pp": 0.6095458466379114, "matr_mae_pp": 1.7021475435912425},
        "configs": CONFIGS,
        "results": results,
    }
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"results": len(results), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
