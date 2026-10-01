"""Run the separate CH published-generated exploratory multiclass benchmark.

python -m model_lab.scripts.v2.benchmark_generated --config <yaml>
Final remains sealed unless --allow-exploratory-final is explicitly supplied.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import yaml

from model_lab.modeling.v2.generated_fault import (
    LIMITATION, NAMESPACE, ORIGIN, evaluate_generated_split,
    load_generated_dataset, train_chemistry_models,
)
from model_lab.scripts.v2.common import code_version, write_json


def aggregate_seed_metrics(runs: list[dict], splits: list[str]) -> dict:
    result = {}
    for split in splits:
        result[split] = {}
        for chemistry in runs[0]["metrics"][split]:
            if chemistry in {"split", "final_policy"}:
                continue
            result[split][chemistry] = {}
            for name in ("macro_auprc", "macro_auprc_all_four_classes", "multiclass_brier", "multiclass_log_loss", "top_label_ece_10_bins"):
                values = [r["metrics"][split][chemistry].get(name) for r in runs]
                valid = [float(v) for v in values if v is not None]
                result[split][chemistry][name] = {
                    "mean": float(np.mean(valid)) if valid else None,
                    "std_across_seeds": float(np.std(valid, ddof=1)) if len(valid) > 1 else None,
                    "values": values, "seeds_with_metric": len(valid),
                }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="model_lab/configs/generated_fault_v2.yaml")
    parser.add_argument("--manifest", help="Override prepared generated data bundle")
    parser.add_argument("--output-dir")
    parser.add_argument("--allow-exploratory-final", action="store_true", help="Explicitly open final only as exploratory generated evidence; never use it for model selection")
    args = parser.parse_args(argv)
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if config.get("namespace") != NAMESPACE or config.get("origin") != ORIGIN:
        raise ValueError("benchmark config must explicitly identify separate public-generated namespace")
    seeds = config.get("seeds", [0, 1, 2])
    if seeds != [0, 1, 2]:
        raise ValueError("generated V2 benchmark requires the preregistered three seeds 0, 1, 2")
    dataset = load_generated_dataset(args.manifest or config["dataset_manifest"], allow_exploratory_final=args.allow_exploratory_final)
    output = Path(args.output_dir or config["output_dir"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    splits = ["train", "dev"] + (["final"] if args.allow_exploratory_final else [])
    versions = code_version()
    runs = []
    for seed in seeds:
        run_dir = output / f"seed{seed}"
        recipe = train_chemistry_models(dataset, seed=seed, **config.get("gbdt", {}))
        write_json(run_dir / "model.json", recipe)
        # Evaluate the serialized/reloaded numerical recipe actually shipped.
        reloaded = json.loads((run_dir / "model.json").read_text(encoding="utf-8"))
        metrics, predictions = {}, {}
        for split in splits:
            metrics[split], predictions[split] = evaluate_generated_split(dataset, reloaded, split)
        run = {
            "seed": seed, "namespace": NAMESPACE, "origin": ORIGIN,
            "evidence_status": "exploratory_generated_only", "limitation": LIMITATION,
            "model_path": str(run_dir / "model.json"), "metrics": metrics,
            "code_version": versions, "fit_split": "train", "calibration_split": "calibration",
        }
        write_json(run_dir / "metrics.json", run)
        write_json(run_dir / "landmark_predictions.json", predictions)
        runs.append(run)
        print(json.dumps({"seed": seed, "status": "complete", "dev_macro_auprc": metrics["dev"]["pooled_conservative_VIN"].get("macro_auprc")}), flush=True)
    counts = {
        split: {"segment_rows": len(dataset.subset(split)), "conservative_VIN_roots": int(dataset.subset(split)["root_scenario_id"].nunique())}
        for split in ["train", "dev", "calibration"] + (["final"] if args.allow_exploratory_final else [])
    }
    summary = {
        "schema_version": "ch-generated-fault-benchmark-v2", "created_at": datetime.now(timezone.utc).isoformat(),
        "namespace": NAMESPACE, "origin": ORIGIN, "source_id": "ch_batterygen",
        "seeds": seeds, "independent_unit": "conservative shared published VIN root; generator mother identity unknown",
        "dataset_manifest": str(dataset.manifest_path), "dataset_manifest_sha256": dataset.manifest_sha256,
        "split_manifest_sha256": dataset.split_sha256, "counts": counts,
        "final_status": "opened_exploratory_only" if args.allow_exploratory_final else "sealed_not_scored",
        "selection_policy": "fixed hyperparameters and seeds; no final or calibration rows used to fit GBDT",
        "primary_metric": "macro AUPRC on evaluable classes at one first frozen charge landmark per VIN",
        "metric_limitation": "Missing classes have null AUPRC; all-four-class macro is null unless all four are evaluable. Seed spread is not an independent-VIN confidence interval.",
        "evidence_status": "exploratory_generated_only", "limitation": LIMITATION,
        "aggregate_metrics": aggregate_seed_metrics(runs, splits), "runs": runs, "code_version": versions,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps({"summary": str(output / "summary.json"), "final_status": summary["final_status"], "namespace": NAMESPACE, "origin": ORIGIN}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
