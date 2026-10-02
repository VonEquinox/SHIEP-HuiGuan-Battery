"""Freeze and retrain F01 six-channel models; never reuse old model weights.

This executable rebuilds H-M1, M1 and M2 on the replacement development bundle,
one model compute process at a time. It records scalar-feature changes first;
only a changed scalar input requests a new MLP comparator. Old comparison
numbers are historical references, never scores from old weights on new inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import yaml

from battery_platform.research import run_hm1_quantile_development as hm1
from model_lab.modeling.v2.contracts import load_dataset, sha256_file


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "battery_platform/research/f01_channel_validity_20261002_qualified"
BUNDLE = BASE / "bundles/combined/features.json"
OLD = ROOT / "battery_platform/research/joint_xjtu_matr/bundles/development/combined/features.json"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def safe_load(path):
    metadata = json.loads(path.read_text())
    if any(row["split"] not in {"train", "dev", "calibration"} for row in metadata["rows"]):
        raise ValueError("F01 retraining refuses non-development rows before loading arrays")
    return load_dataset(path)


def signature(row):
    return row["source_id"], row["physical_cell_id"], row["split"], row["query_time"]


def bind_hm1_exports(manifest):
    """Bind each newly created scalar recipe to this dataset and feature schema."""
    hm_receipt = json.loads(hm1.OUT.read_text())
    hm_receipt["feature_schema"] = manifest["schema_version"]
    hm_receipt["finding"] = "F01"
    hm_receipt["historical_references_role"] = "pre-fix historical reference only; never reusing historical weights"
    hm_receipt["references"].pop("historical_final_mlp_xjtu_mae_pp", None)
    hm_receipt["preprocessing_version"] = "f01-scalar-train-median-mean-scale-v1"
    hm_receipt["input_kind"] = "30D statistics with explicit missing flags; sequence channels not consumed"
    for result in hm_receipt["results"]:
        model_path = Path(result["model"])
        if not model_path.is_relative_to(BASE):
            raise ValueError("refuse binding a model outside the new F01 research version")
        record = json.loads(model_path.read_text())
        if record.get("feature_schema") not in {None, manifest["schema_version"]}:
            raise ValueError("refuse changing an already bound feature schema")
        record.update(
            feature_schema=manifest["schema_version"], data_version=manifest["data_version"],
            dataset_manifest_sha256=sha256_file(BUNDLE),
            arrays_sha256=manifest["arrays_sha256"], n_features=30,
            input_kind=hm_receipt["input_kind"],
            preprocessing_version=hm_receipt["preprocessing_version"],
            feature_builder_sha256=sha256_file(ROOT / "model_lab/modeling/v2/features.py"),
        )
        write_json(model_path, record)
        result["model_sha256"] = sha256_file(model_path)
    write_json(hm1.OUT, hm_receipt)


def historical_artifact_hashes():
    oldbase = ROOT / "battery_platform/research/joint_xjtu_matr"
    paths = [OLD, OLD.parent / "features.npz", oldbase / "optimization/hm1_quantile_development_20261002.json"]
    paths += sorted((oldbase / "optimization/hm1_quantile_models_20261002").glob("seed*.json"))
    for family, name in (("M1", "xjtu_matr_m1_no_ngboost"), ("M2", "xjtu_matr_m2")):
        for seed in (0, 1, 2):
            run = oldbase / "runs" / name / f"{family}_joint_seed{seed}"
            paths += [run / "run.json", run / "dev_metrics.json", run / ("model.json" if family == "M1" else "weights.npz")]
    return {"scope": "previous development artifacts only; not final numerical arrays",
            "sha256": {str(path.relative_to(ROOT)): sha256_file(path) for path in paths}}


def development_model_comparison():
    def metric(path):
        metrics = json.loads(path.read_text())
        values = {"xjtu": [], "matr": []}
        for domain, result in metrics.items():
            head = result["heads"]["soh"]
            if head["status"] == "evaluated":
                values[domain.split("::")[0]] += [value["mae"] * 100 for value in head["per_object"].values()]
        return {source: float(np.mean(value)) for source, value in values.items()}

    def aggregate(values):
        return {source: {"mean_mae_pp": float(np.mean([value[source] for value in values])),
                         "sample_std_mae_pp": float(np.std([value[source] for value in values], ddof=1)),
                         "seeds_mae_pp": [value[source] for value in values]} for source in ("xjtu", "matr")}

    oldbase = ROOT / "battery_platform/research/joint_xjtu_matr"
    models = {}
    for family, oldrun in (("M1", "xjtu_matr_m1_no_ngboost"), ("M2", "xjtu_matr_m2")):
        models[family] = {}
        for version, path in (("old5channel", oldbase / "runs" / oldrun), ("new6channel", BASE / "runs" / family)):
            models[family][version] = aggregate([metric(path / f"{family}_joint_seed{seed}" / "dev_metrics.json")
                                                for seed in (0, 1, 2)])
    models["H-M1"] = {}
    for version, path in (("old5channel", oldbase / "optimization/hm1_quantile_development_20261002.json"),
                          ("new6channel", hm1.OUT)):
        receipt = json.loads(path.read_text())
        models["H-M1"][version] = aggregate([{source: row["metrics"]["dev"][source]["mae_pp"]
                                              for source in ("xjtu", "matr")} for row in receipt["results"]])
    return {"finding": "F01", "unit": "SOH percentage points",
            "aggregation": "mean within physicalcell then source cellmacro; across3seeds mean±sampleSD",
            "selection_split": "dev", "old_schema": "battery_features_v2", "new_schema": "battery_features_v2_channel_validity_1",
            "model_weights_reused": False, "historical_final_or_protected_scored": False,
            "same_frozen_population_and_targets": True, "features_scalar_30D_unchanged": True,
            "MLP_reference_role": "historical scalar30D development comparator; unmodified scalarfeatures/labels/own preprocessing recipe",
            "models": models,
            "M2_interpretation": "6channel encoder/input transform retrained; XJTUdegrades,MATRimproves; not selected and not causal evidence for missingtemperature impact"}


def main():
    global BASE, BUNDLE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=BASE)
    args = parser.parse_args()
    BASE = args.output_dir.resolve()
    if not BASE.is_relative_to(ROOT / "battery_platform/research"):
        raise ValueError("F01 research outputs must stay under battery_platform/research")
    BUNDLE = BASE / "bundles/combined/features.json"
    receipt_path = BASE / "retraining_receipt.json"
    if receipt_path.exists():
        raise FileExistsError("immutable F01 retraining already exists")
    manifest, arrays = safe_load(BUNDLE)
    old_manifest, old_arrays = safe_load(OLD)
    before = historical_artifact_hashes()
    write_json(BASE / "historical_artifact_hashes_before.json", before)
    if manifest["schema_version"] == old_manifest["schema_version"]:
        raise ValueError("replacement feature schema must be independently versioned")
    old_index = {signature(row): i for i, row in enumerate(old_manifest["rows"])}
    indices = np.asarray([old_index[signature(row)] for row in manifest["rows"]])
    if len(indices) != len(old_index):
        raise ValueError("F01 correction changed the frozen development population")
    scalar_delta = arrays["features"] - old_arrays["features"][indices]
    changed = np.any(scalar_delta != 0, axis=1)
    changes = {
        "row_count": len(indices), "changed_scalar_rows": int(changed.sum()),
        "scalar_max_abs_change": float(np.max(np.abs(scalar_delta))),
        "changed_feature_indices": np.flatnonzero(np.any(scalar_delta != 0, axis=0)).tolist(),
        "target_max_abs_change": float(np.max(np.abs(arrays["y_soh"] - old_arrays["y_soh"][indices]))),
        "new_sequence_channels": arrays["sequences"].shape[-1],
        "old_sequence_channels": old_arrays["sequences"].shape[-1],
        "same_frozen_physical_population": True,
        "old_weights_used_with_new_features": False,
    }
    write_json(BASE / "feature_input_diff.json", changes)
    if changes["target_max_abs_change"] != 0:
        raise ValueError("F01 feature correction must preserve target labels")
    # The supplied current H-M1 structure stays frozen: no new parameter search.
    hm1.BUNDLE = BUNDLE
    hm1.OUT = BASE / "hm1_quantile_development.json"
    hm1.MODEL_DIR = BASE / "hm1_quantile_models"
    if hm1.MODEL_DIR.exists():
        raise FileExistsError("H-M1 corrected weights already exist")
    hm1.main()
    bind_hm1_exports(manifest)
    configs = BASE / "configs"
    configs.mkdir(exist_ok=False)
    for family in ("M1", "M2"):
        old_config = ROOT / f"battery_platform/research/joint_xjtu_matr/configs/xjtu_matr_{family.lower()}.yaml"
        config = yaml.safe_load(old_config.read_text())
        config["dataset_manifest"] = str(BUNDLE.relative_to(ROOT))
        config["output_dir"] = str((BASE / "runs" / family).relative_to(ROOT))
        config["development_only"] = True
        config_path = configs / f"{family.lower()}_development.yaml"
        config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        subprocess.run([sys.executable, "-m", "model_lab.scripts.v2.train", "--config", str(config_path)],
                       cwd=ROOT, check=True)
    results = {}
    for family in ("M1", "M2"):
        results[family] = []
        for seed in (0, 1, 2):
            run = BASE / "runs" / family / f"{family}_joint_seed{seed}"
            record = json.loads((run / "run.json").read_text())
            results[family].append({
                "seed": seed, "status": record["status"], "feature_schema": record["feature_schema"],
                "channels": record.get("spec", {}).get("channels"),
                "model_sha256": record["model_sha256"],
                "dev_metrics_sha256": sha256_file(run / "dev_metrics.json"),
                "final_accessed": record["final_accessed"],
            })
    if changes["changed_scalar_rows"]:
        raise RuntimeError("scalar features changed: train a same-bundle MLP comparator before declaring comparisons valid")
    after = historical_artifact_hashes()
    after["historical_artifacts_unchanged"] = before["sha256"] == after["sha256"]
    if not after["historical_artifacts_unchanged"]:
        raise ValueError("historical development artifacts changed during F01 retraining")
    write_json(BASE / "historical_artifact_hashes_after.json", after)
    write_json(BASE / "development_model_comparison.json", development_model_comparison())
    write_json(receipt_path, {
        "finding": "F01", "feature_schema": manifest["schema_version"],
        "bundle_sha256": sha256_file(BUNDLE), "source_bundle_sha256": sha256_file(OLD),
        "selection_split": "dev", "final_labels_accessed": False, "protected_labels_accessed": False,
        "new_weights_for_new_feature_version": True, "historical_metrics_overwritten": False,
        "input_diff": changes, "families_retrained": ["H-M1", "M1", "M2"],
        "same_bundle_mlp_retraining": "not required: unchanged scalar 30D input and targets; old MLP metric remains historical",
        "seeds": [0, 1, 2], "split_rows": dict(Counter(r["split"] for r in manifest["rows"])),
        "hm1_receipt_sha256": sha256_file(hm1.OUT), "model_runs": results,
        "no_model_family_selected_against_final_feedback": True,
    })
    print(receipt_path)


if __name__ == "__main__":
    main()
