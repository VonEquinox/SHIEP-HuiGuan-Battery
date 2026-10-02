"""Aggregate joint experiment receipts and render comparison figures."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "battery_platform/research/joint_xjtu_matr"
OUT = BASE / "summary"


def v2_final_metrics(run_root: Path) -> dict:
    values: dict[str, dict[str, dict[str, list[float]]]] = {}
    for path in sorted(run_root.glob("M*_joint_seed*/final_metrics.json")):
        seed = path.parent.name.rsplit("seed", 1)[-1]
        data = json.loads(path.read_text())
        for domain, payload in data["metrics"].items():
            head = payload["heads"]["soh"]
            if head.get("status") != "evaluated":
                continue
            source = domain.split("::", 1)[0]
            values.setdefault(source, {}).setdefault(seed, {"mae": [], "rmse": []})
            values[source][seed]["mae"].append(float(head["mae"]) * 100)
            values[source][seed]["rmse"].append(float(head["rmse"]) * 100)
    return {
        source: {
            "mae_pp_mean": float(np.mean([np.mean(v["mae"]) for v in metrics.values()])),
            "mae_pp_sd": float(np.std([np.mean(v["mae"]) for v in metrics.values()], ddof=1)) if len(metrics) > 1 else 0.0,
            "rmse_pp_mean": float(np.mean([np.mean(v["rmse"]) for v in metrics.values()])),
            "rmse_pp_sd": float(np.std([np.mean(v["rmse"]) for v in metrics.values()], ddof=1)) if len(metrics) > 1 else 0.0,
            "seeds": len(metrics),
        }
        for source, metrics in values.items()
    }


def external_final(path: Path, method: str | None = None) -> dict:
    data = json.loads(path.read_text())
    values: dict[str, dict[str, list[float]]] = {}
    for row in data["methods"]:
        if method is not None and row["method"] != method:
            continue
        for source, metrics in row["final_scores"].items():
            values.setdefault(source, {"mae": [], "rmse": []})
            values[source]["mae"].append(metrics["cell_mae_pp"])
            values[source]["rmse"].append(metrics["cell_rmse_pp"])
    return {
        source: {
            "mae_pp_mean": float(np.mean(metrics["mae"])),
            "mae_pp_sd": float(np.std(metrics["mae"], ddof=1)) if len(metrics["mae"]) > 1 else 0.0,
            "rmse_pp_mean": float(np.mean(metrics["rmse"])),
            "rmse_pp_sd": float(np.std(metrics["rmse"], ddof=1)) if len(metrics["rmse"]) > 1 else 0.0,
            "seeds": len(metrics["mae"]),
        }
        for source, metrics in values.items()
    }


def external_by_method(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text())
    return {
        method: external_final(path, method=method)
        for method in sorted({row["method"] for row in data["methods"]})
    }


def add_delta(reference: dict, candidate: dict) -> dict:
    """Return candidate-reference deltas and relative reduction by source."""
    result = {}
    for source, ref_metrics in reference.items():
        cand_metrics = candidate.get(source)
        if not cand_metrics:
            continue
        ref = ref_metrics["mae_pp_mean"]
        cand = cand_metrics["mae_pp_mean"]
        result[source] = {
            "delta_mae_pp": cand - ref,
            "relative_error_reduction": (ref - cand) / ref if ref else None,
        }
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    models = {
        "M1_joint": v2_final_metrics(BASE / "runs/xjtu_matr_m1_final"),
        "M2_joint": v2_final_metrics(BASE / "runs/xjtu_matr_m2_final"),
    }
    # Split the external receipt by method while preserving the same summary shape.
    external = json.loads((BASE / "baselines/source_aware_final_20261002.json").read_text())
    for method in ("mlp", "lstm", "lightgbm"):
        models[method.upper() + "_JOINT"] = external_final(
            BASE / "baselines/source_aware_final_20261002.json", method=method
        )

    xjtu_only = {
        "M1": v2_final_metrics(BASE / "runs/xjtu_only_m1_final"),
        "M2": v2_final_metrics(BASE / "runs/xjtu_only_m2_final"),
    }
    transfer_by_method = external_by_method(BASE / "baselines/xjtu_only_transfer_final_20261002.json")
    transfer = external_final(BASE / "baselines/xjtu_only_transfer_final_20261002.json")

    transfer = external_final(BASE / "baselines/xjtu_only_transfer_final_20261002.json")
    # The external_final helper expects method rows; the transfer receipt has the same schema.
    summary = {
        "scope": "XJTU+MATR final comparison; XJTU final is historically exposed and protected -5 cells remain sealed",
        "models": models,
        "xjtu_only": xjtu_only,
        "joint_vs_xjtu_only_delta": {
            "M1": add_delta(xjtu_only["M1"], models["M1_joint"]),
            "M2": add_delta(xjtu_only["M2"], models["M2_joint"]),
        },
        "xjtu_only_transfer": transfer,
        "xjtu_only_transfer_by_method": transfer_by_method,
        "joint_baseline_vs_m1_delta": {
            method: add_delta(models["M1_joint"], models[method])
            for method in ("MLP_JOINT", "LSTM_JOINT", "LIGHTGBM_JOINT")
        },
        "data_scale": {
            "xjtu_full": {"objects": 21, "rows": 168},
            "xjtu_matr_full": {"objects": 56, "rows": 448},
            "xjtu_development_nonfinal": {"objects": 18, "rows": 144},
            "xjtu_matr_development_nonfinal": {"objects": 47, "rows": 376},
            "full_multiplier": 56 / 21,
            "development_multiplier": 47 / 18,
            "train_multiplier": 28 / 11,
        },
    }
    (OUT / "joint_benchmark_summary_20261002.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    # Final MAE comparison.  Error bars are seed SD; all values are percentage points.
    labels = ["M1\njoint", "M2\njoint", "MLP\njoint", "LSTM\njoint", "LightGBM\njoint"]
    keys = ["M1_joint", "M2_joint", "MLP_JOINT", "LSTM_JOINT", "LIGHTGBM_JOINT"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for ax, source, title in zip(axes, ("xjtu", "matr"), ("XJTU comparison final", "MATR comparison final")):
        means, errors = [], []
        for key in keys:
            record = summary["models"][key].get(source, {"mae_pp_mean": np.nan, "mae_pp_sd": 0})
            means.append(record["mae_pp_mean"]); errors.append(record["mae_pp_sd"])
        ax.bar(np.arange(len(labels)), means, yerr=errors, capsize=4, color=["#184e77", "#76c893", "#f4a261", "#e76f51", "#e9c46a"])
        ax.set_title(title); ax.set_ylabel("cell-macro MAE (SOH percentage points)")
        ax.set_xticks(np.arange(len(labels)), labels); ax.grid(axis="y", alpha=.25)
    fig.savefig(OUT / "final_mae_comparison.png", dpi=180)
    plt.close(fig)

    # MATR transfer diagnostic: the XJTU-only bars are deliberately OOD,
    # while the joint bars use the source-aware adapter and MATR train rows.
    transfer_labels = ["MLP", "LSTM", "LightGBM"]
    transfer_keys = ["mlp", "lstm", "lightgbm"]
    xjtu_only_values = [summary["xjtu_only_transfer_by_method"][k]["matr"]["mae_pp_mean"] for k in transfer_keys]
    joint_values = [summary["models"][k]["matr"]["mae_pp_mean"] for k in ("MLP_JOINT", "LSTM_JOINT", "LIGHTGBM_JOINT")]
    fig, ax = plt.subplots(figsize=(8, 4.8), constrained_layout=True)
    positions = np.arange(len(transfer_labels))
    width = 0.36
    ax.bar(positions - width / 2, xjtu_only_values, width, label="XJTU-only → MATR OOD", color="#adb5bd")
    ax.bar(positions + width / 2, joint_values, width, label="XJTU+MATR source-aware", color="#277da1")
    ax.set_xticks(positions, transfer_labels)
    ax.set_ylabel("MATR cell-macro MAE (SOH percentage points)")
    ax.set_title("MATR transfer diagnostic")
    ax.grid(axis="y", alpha=.25)
    ax.legend(frameon=False)
    fig.savefig(OUT / "matr_transfer_comparison.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    labels = ["XJTU\nfull", "XJTU+MATR\nfull", "XJTU\nnon-final", "XJTU+MATR\nnon-final"]
    values = [21, 56, 18, 47]
    bars = ax.bar(labels, values, color=["#90be6d", "#277da1", "#f9c74f", "#f9844a"])
    ax.set_ylabel("independent model objects / cells")
    ax.set_title("Dataset expansion by modelled physical object")
    ax.grid(axis="y", alpha=.25)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + .8, str(value), ha="center")
    fig.savefig(OUT / "dataset_scale_comparison.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
