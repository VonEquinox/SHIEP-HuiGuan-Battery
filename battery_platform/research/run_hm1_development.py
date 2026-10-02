"""Development-only search for a hierarchical, source-adapted M1 model.

This file deliberately cannot score a ``final`` row.  It is a research driver
for the next M1 design and is kept outside ``model_lab`` so the historical V2
implementation remains immutable.  The intended workflow is:

1. run this script against the development bundle;
2. choose one configuration using development rows and the preregistered
   MATR/XJTU gates;
3. freeze the configuration and implement the export/inference recipe;
4. fit the frozen recipe and evaluate the final bundle exactly once.

The candidate model is H-M1 (hierarchical M1): a source-normalised shared
quantile gradient-boosting head, a shrunken per-domain residual head, and an
optional visible-capacity anchor.  The source/domain indicators are inputs,
not labels.  The residual head is deliberately low-capacity because several
XJTU domains have only a few independent training cells.

This script is an experiment specification and development runner, not a
production model exporter.  It writes only development metrics and a JSON
receipt.  It must never be pointed at a bundle containing final rows.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from model_lab.modeling.v2.features import fit_preprocessor, preprocess

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = ROOT / "battery_platform/research/joint_xjtu_matr/bundles/development/combined/features.json"
DEFAULT_OUTPUT = ROOT / "battery_platform/research/joint_xjtu_matr/hm1_development"


@dataclass(frozen=True)
class Candidate:
    """One preregistered H-M1 configuration."""

    n_estimators: int
    specialist_learning_rate: float
    learning_rate: float
    max_depth: int
    min_samples_leaf: int
    residual_estimators: int
    residual_learning_rate: float
    residual_shrink: float
    shared_shrink: float
    anchor_shrink: float

    @property
    def name(self) -> str:
        values = (
            self.n_estimators,
            self.specialist_learning_rate,
            self.max_depth,
            self.min_samples_leaf,
            self.residual_estimators,
            self.residual_shrink,
            self.shared_shrink,
            self.anchor_shrink,
        )
        return "h-m1-" + "-".join(str(v).replace(".", "p") for v in values)


# Keep this grid small enough for a local development run.  It varies model
# capacity and the two safety mechanisms independently; it does not inspect
# any final label.  The selected config is written to the receipt.
CANDIDATES = tuple(
    Candidate(n, .10, lr, depth, leaf, rn, .03, rs, shared, anchor)
    for n in (80, 120)
    for lr in (.03,)
    for depth in (1, 2)
    for leaf in (3, 6)
    for rn in (20,)
    for rs in (0.15, 0.30)
    for shared in (0.0, 0.05, 0.10, 0.15)
    for anchor in (0.0, 0.15)
)


def _load_dataset(path: Path) -> tuple[dict, dict[str, np.ndarray]]:
    """Load and enforce the development-only boundary."""

    manifest = json.loads(path.read_text())
    rows = manifest.get("rows", [])
    splits = {row.get("split") for row in rows}
    if "final" in splits or "final-test" in splits or "sealed" in splits or "protected" in splits:
        raise ValueError(
            "H-M1 development runner refuses bundles containing final/sealed rows; "
            f"found splits={sorted(splits)}"
        )
    arrays_path = path.parent / manifest["arrays_file"]
    arrays = dict(np.load(arrays_path, allow_pickle=False))
    if len(rows) != len(arrays["features"]):
        raise ValueError("manifest/array row count mismatch")
    return manifest, arrays


def _object_weights(cells: np.ndarray) -> np.ndarray:
    """Equalise each independent battery cell, not each landmark row."""

    _, inverse, counts = np.unique(cells, return_inverse=True, return_counts=True)
    values = 1.0 / counts[inverse]
    return values / values.mean()


def _score(y: np.ndarray, prediction: np.ndarray, cells: np.ndarray, sources: np.ndarray) -> dict:
    """Cell-macro SOH error in percentage points."""

    output: dict[str, dict[str, float | int]] = {}
    for source in ("all", "xjtu", "matr"):
        mask = np.ones(len(y), dtype=bool) if source == "all" else sources == source
        if not mask.any():
            output[source] = {"cells": 0, "cell_mae_pp": None, "cell_rmse_pp": None}
            continue
        maes: list[float] = []
        rmses: list[float] = []
        for cell in sorted(set(cells[mask])):
            row_mask = mask & (cells == cell)
            error = (prediction[row_mask] - y[row_mask]) * 100.0
            maes.append(float(np.abs(error).mean()))
            rmses.append(float(np.sqrt(np.mean(error**2))))
        output[source] = {
            "cells": len(maes),
            "cell_mae_pp": float(np.mean(maes)),
            "cell_rmse_pp": float(np.mean(rmses)),
        }
    return output


def _domain_key(row: dict) -> str:
    return "::".join(str(row.get(key)) for key in ("source_id", "chemistry", "protocol_id"))


def _prepare(manifest: dict, arrays: dict[str, np.ndarray]) -> dict:
    """Build standardised statistics plus source/domain indicators.

    The only statistics fitted here are from the training rows.  The raw
    capacity feature is retained solely for the optional anchor and is never
    fitted on dev rows.
    """

    rows = manifest["rows"]
    features = arrays["features"].astype(np.float64)
    labels = arrays["y_soh"].astype(np.float64)
    split = np.asarray([row["split"] for row in rows])
    cells = np.asarray([row["physical_cell_id"] for row in rows])
    sources = np.asarray([row["source_id"] for row in rows])
    domains = np.asarray([_domain_key(row) for row in rows])
    train = split == "train"
    if not train.any():
        raise ValueError("development bundle has no training rows")

    # Reuse the frozen V2 train-only transform so a zero-shrink H-M1 branch is
    # numerically comparable with the existing M1.  There are no NaNs in the
    # current statistics bundle; if a future bundle introduces one, the
    # shared V2 preprocessor remains the single place to define its handling.
    transform = fit_preprocessor(
        arrays["features"], arrays["sequences"], arrays["sequence_mask"], np.flatnonzero(train)
    )
    transformed = preprocess(arrays, transform)["features"].astype(np.float64)
    features_filled = features.copy()
    finite = np.isfinite(features_filled)
    if not finite.all():
        median = np.nanmedian(np.where(finite[train], features_filled[train], np.nan), axis=0)
        features_filled = np.where(finite, features_filled, np.where(np.isfinite(median), median, 0.0))
    statistics = transformed

    domain_levels = sorted(set(domains))
    source_levels = sorted(set(sources))
    domain_one_hot = np.column_stack([(domains == level) for level in domain_levels]).astype(np.float64)
    source_one_hot = np.column_stack([(sources == level) for level in source_levels]).astype(np.float64)
    model_features = np.column_stack((statistics, source_one_hot, domain_one_hot))

    log_y = np.log(np.clip(labels, 1e-6, None))
    source_mu: dict[str, float] = {}
    source_sd: dict[str, float] = {}
    for source in source_levels:
        values = log_y[train & (sources == source)]
        if len(values) < 8:
            raise ValueError(f"not enough legal SOH rows for source normalisation: {source}")
        source_mu[source] = float(values.mean())
        source_sd[source] = float(max(values.std(), 0.02))
    z = np.asarray([(log_y[i] - source_mu[sources[i]]) / source_sd[sources[i]] for i in range(len(rows))])

    # Feature 11 is recent_capacity_relative_to_reference in the V2 30D view.
    # Keep a bounded log anchor.  It is only blended into a prediction when a
    # candidate explicitly asks for it, and its source statistics come from
    # train rows only.
    anchor_ratio = np.clip(features_filled[:, 11], 0.55, 1.25)
    anchor_log = np.log(anchor_ratio)
    anchor_z = np.asarray(
        [(anchor_log[i] - source_mu[sources[i]]) / source_sd[sources[i]] for i in range(len(rows))]
    )

    return {
        "rows": rows,
        "features": model_features,
        "raw_features": features_filled,
        "labels": labels,
        "z": z,
        "log_y": log_y,
        "anchor_z": anchor_z,
        "anchor_log": anchor_log,
        "split": split,
        "cells": cells,
        "sources": sources,
        "domains": domains,
        "source_mu": source_mu,
        "source_sd": source_sd,
        "domain_levels": domain_levels,
        "source_levels": source_levels,
    }


class HM1:
    """In-memory H-M1 candidate used only for development comparison."""

    def __init__(self, candidate: Candidate, seed: int):
        self.candidate = candidate
        self.seed = seed
        self.quantiles: dict[float, GradientBoostingRegressor] = {}
        self.specialists: dict[str, GradientBoostingRegressor] = {}
        self.residual: dict[str, GradientBoostingRegressor] = {}
        self.train_domains: set[str] = set()

    def fit(self, data: dict) -> "HM1":
        train = data["split"] == "train"
        specialist_x = data["features"][train, :30]
        shared_x = data["features"][train]
        target = data["z"][train]
        log_target = data["log_y"][train]
        weights = _object_weights(data["cells"][train])
        self.train_domains = set(data["domains"][train])
        c = self.candidate

        # The specialist median is the current M1 inductive bias: one small
        # tree ensemble per source/chemistry/protocol domain, trained in the
        # original log-SOH space.  Keeping it as an explicit branch means a
        # zero shared/residual/anchor shrink exactly recovers the safe M1
        # baseline while allowing development-only searches to add a pooled
        # prior when it helps.
        train_domains = data["domains"][train]
        for domain in sorted(self.train_domains):
            domain_train = train_domains == domain
            model = GradientBoostingRegressor(
                loss="quantile",
                alpha=0.5,
                n_estimators=c.n_estimators,
                learning_rate=c.specialist_learning_rate,
                max_depth=c.max_depth,
                min_samples_leaf=c.min_samples_leaf,
                random_state=self.seed,
            )
            model.fit(specialist_x[domain_train], log_target[domain_train], sample_weight=weights[domain_train])
            self.specialists[domain] = model

        for quantile in (0.05, 0.5, 0.95):
            model = GradientBoostingRegressor(
                loss="quantile",
                alpha=quantile,
                n_estimators=c.n_estimators,
                learning_rate=c.learning_rate,
                max_depth=c.max_depth,
                min_samples_leaf=c.min_samples_leaf,
                random_state=self.seed,
            )
            model.fit(shared_x, target, sample_weight=weights)
            self.quantiles[quantile] = model

        # Fit a low-capacity residual correction per domain.  Shrinkage is
        # applied at prediction time; this keeps tiny domains from replacing
        # the shared model with a high-variance branch.
        median_prediction = np.empty(len(specialist_x), dtype=float)
        for domain, model in self.specialists.items():
            domain_train = train_domains == domain
            median_prediction[domain_train] = model.predict(specialist_x[domain_train])
        for domain in sorted(self.train_domains):
            domain_train = train_domains == domain
            if domain_train.sum() < 12:
                continue
            residual = log_target[domain_train] - median_prediction[domain_train]
            mask = train & (data["domains"] == domain)
            model = GradientBoostingRegressor(
                loss="huber",
                n_estimators=c.residual_estimators,
                learning_rate=c.residual_learning_rate,
                max_depth=1,
                min_samples_leaf=max(3, min(c.min_samples_leaf, int(mask.sum() // 4))),
                random_state=self.seed + 101,
            )
            model.fit(data["features"][mask, :30], residual, sample_weight=_object_weights(data["cells"][mask]))
            self.residual[domain] = model
        return self

    def predict_z(self, data: dict, indices: np.ndarray) -> np.ndarray:
        x = data["features"][indices]
        shared_z = self.quantiles[0.5].predict(x)
        specialist_x = x[:, :30]
        source = data["sources"][indices]
        shared_log = np.asarray([shared_z[i] * data["source_sd"][s] + data["source_mu"][s] for i, s in enumerate(source)])
        output = np.full(len(indices), np.nan, dtype=float)
        for domain, model in self.specialists.items():
            mask = data["domains"][indices] == domain
            if mask.any():
                output[mask] = model.predict(specialist_x[mask])
        # Unknown domains are not expected in this frozen bundle; using the
        # shared branch keeps this helper total for development diagnostics.
        known = np.isfinite(output)
        output[~known] = shared_log[~known]
        output = (1.0 - self.candidate.shared_shrink) * output + self.candidate.shared_shrink * shared_log
        for domain, model in self.residual.items():
            mask = data["domains"][indices] == domain
            if mask.any():
                output[mask] += self.candidate.residual_shrink * model.predict(specialist_x[mask])
        if self.candidate.anchor_shrink:
            output = (1.0 - self.candidate.anchor_shrink) * output + self.candidate.anchor_shrink * data["anchor_log"][indices]
        return output

    def predict(self, data: dict, indices: np.ndarray) -> np.ndarray:
        return np.exp(self.predict_z(data, indices))


def _reference_gates() -> dict:
    """Return development references without touching a final bundle."""

    m1_paths = sorted((ROOT / "battery_platform/research/joint_xjtu_matr/runs/xjtu_matr_m1_no_ngboost").glob("M1_joint_seed*/dev_metrics.json"))
    mlp_path = ROOT / "battery_platform/research/joint_xjtu_matr/baselines/development/v2_30d_domain_20261002.json"
    mlp_values = []
    if mlp_path.exists():
        baseline = json.loads(mlp_path.read_text())
        by_seed = {}
        for row in baseline.get("rows", []):
            if row.get("method") == "mlp" and row.get("part") == "dev":
                score = row.get("scores", {}).get("xjtu", {}).get("cell_mae_pp")
                if score is not None:
                    by_seed[row["seed"]] = float(score)
        mlp_values = list(by_seed.values())
    if not m1_paths:
        return {
            "m1_dev_xjtu_mae_pp": None,
            "m1_dev_matr_mae_pp": None,
            "mlp_dev_xjtu_mae_pp": float(np.mean(mlp_values)) if mlp_values else None,
        }
    m1 = [json.loads(path.read_text()) for path in m1_paths]
    xjtu = []
    matr = []
    for metrics in m1:
        xjtu_values = []
        matr_values = []
        for key, head in metrics.items():
            target = xjtu_values if key.startswith("xjtu::") else matr_values
            target.extend(item["mae"] * 100 for item in head["heads"]["soh"].get("per_object", {}).values())
        xjtu.append(float(np.mean(xjtu_values)))
        matr.append(float(np.mean(matr_values)))
    return {
        "m1_dev_xjtu_mae_pp": float(np.mean(xjtu)),
        "m1_dev_matr_mae_pp": float(np.mean(matr)),
        "mlp_dev_xjtu_mae_pp": float(np.mean(mlp_values)) if mlp_values else None,
    }


def run(bundle: Path, output: Path, seeds: Iterable[int], limit: int | None = None) -> dict:
    manifest, arrays = _load_dataset(bundle)
    data = _prepare(manifest, arrays)
    dev = data["split"] == "dev"
    calibration = data["split"] == "calibration"
    if not dev.any():
        raise ValueError("development bundle has no dev rows")
    candidates = CANDIDATES if limit is None else CANDIDATES[:limit]
    reference = _reference_gates()
    records = []
    for candidate in candidates:
        for seed in seeds:
            random.seed(seed)
            np.random.seed(seed)
            model = HM1(candidate, seed).fit(data)
            dev_prediction = model.predict(data, np.flatnonzero(dev))
            dev_scores = _score(data["labels"][dev], dev_prediction, data["cells"][dev], data["sources"][dev])
            calibration_scores = None
            if calibration.any():
                calibration_prediction = model.predict(data, np.flatnonzero(calibration))
                calibration_scores = _score(
                    data["labels"][calibration], calibration_prediction, data["cells"][calibration], data["sources"][calibration]
                )
            records.append(
                {
                    "candidate": asdict(candidate),
                    "candidate_name": candidate.name,
                    "seed": seed,
                    "dev_scores": dev_scores,
                    "calibration_scores": calibration_scores,
                    "final_labels_used": False,
                }
            )

    # Aggregate seeds and rank only after all development scores are written.
    aggregate: dict[str, dict] = {}
    for record in records:
        key = record["candidate_name"]
        item = aggregate.setdefault(key, {"candidate": record["candidate"], "seeds": [], "xjtu": [], "matr": []})
        item["seeds"].append(record["seed"])
        item["xjtu"].append(record["dev_scores"]["xjtu"]["cell_mae_pp"])
        item["matr"].append(record["dev_scores"]["matr"]["cell_mae_pp"])
    for item in aggregate.values():
        item["xjtu_mae_pp_mean"] = float(np.mean(item["xjtu"]))
        item["matr_mae_pp_mean"] = float(np.mean(item["matr"]))
        item["xjtu_mae_pp_sd"] = float(np.std(item["xjtu"], ddof=1)) if len(item["xjtu"]) > 1 else 0.0
        item["matr_mae_pp_sd"] = float(np.std(item["matr"], ddof=1)) if len(item["matr"]) > 1 else 0.0
        # Pre-registered gates: preserve MATR M1 within 0.10 pp while
        # improving XJTU.  ``passed`` is a development claim only.
        item["passed_matr_gate"] = reference["m1_dev_matr_mae_pp"] is None or item["matr_mae_pp_mean"] <= reference["m1_dev_matr_mae_pp"] + 0.10
        xjtu_references = [
            value
            for value in (reference["m1_dev_xjtu_mae_pp"], reference.get("mlp_dev_xjtu_mae_pp"))
            if value is not None
        ]
        item["passed_xjtu_gate"] = not xjtu_references or item["xjtu_mae_pp_mean"] < min(xjtu_references)
    ranked = sorted(aggregate.values(), key=lambda item: (not (item["passed_matr_gate"] and item["passed_xjtu_gate"]), item["xjtu_mae_pp_mean"] + 0.2 * item["matr_mae_pp_mean"]))
    result = {
        "scope": "H-M1 development-only search; final rows forbidden",
        "bundle": str(bundle.resolve()),
        "bundle_sha256": _sha256(bundle),
        "rows": len(manifest["rows"]),
        "split_counts": {split: int(np.sum(data["split"] == split)) for split in sorted(set(data["split"]))},
        "domain_levels": data["domain_levels"],
        "source_target_normalisation": {"mu": data["source_mu"], "sd": data["source_sd"]},
        "reference_gates": reference,
        "candidates": len(candidates),
        "seeds": list(seeds),
        "records": records,
        "aggregate_ranked": ranked,
        "selection_split": "dev",
        "calibration_only_for_stability_report": True,
        "final_labels_used_for_selection": False,
        "warning": "A passing development gate does not establish final performance; freeze first, then evaluate final exactly once.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "hm1_development_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (output / "hm1_development_protocol.json").write_text(json.dumps({
        "candidate_grid": [asdict(candidate) for candidate in candidates],
        "selection_split": "dev",
        "forbidden_splits": ["final", "final-test", "sealed", "protected"],
        "gates": {
            "MATR": "mean cell-MAE <= current M1 dev mean + 0.10 pp",
            "XJTU": "mean cell-MAE < both current M1 and same-bundle MLP development means",
        },
    }, indent=2, ensure_ascii=False))
    return result


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, action="append", default=None)
    parser.add_argument("--limit", type=int, default=None, help="development smoke limit; omit for the preregistered grid")
    args = parser.parse_args()
    seeds = tuple(args.seed) if args.seed else (0, 1, 2)
    result = run(args.bundle, args.output, seeds, args.limit)
    print(json.dumps({"output": str(args.output.resolve()), "candidates": result["candidates"], "top": result["aggregate_ranked"][:3]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
