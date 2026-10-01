"""Separate, exploratory fault benchmark for the published CH generated data.

No result from this module describes generalization to a real vehicle fleet.
Native statistics are fitted independently per chemistry; generation parents
are unknown, so the conservative published VIN root is only a proxy identity.
The exported GBDT is a validated numerical JSON recipe, never executable state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_curve

FAULT_CLASSES = ("high_resistance", "low_capacity", "normal", "self_discharge")
FEATURE_NAMES = tuple(
    f"{column}_{stat}"
    for column in (
        "MAX_CELL_VOLT", "MAX_TEMP", "MIN_CELL_VOLT", "MIN_TEMP",
        "SOC", "SUM_CURRENT", "SUM_VOLTAGE", "TIME",
    )
    for stat in ("mean", "std")
)
NAMESPACE = "demo_synthetic"
ORIGIN = "public_generated"
SOURCE = "ch_batterygen"
SCHEMA = "ch-generated-fault-gbdt-v2"
LIMITATION = (
    "Exploratory published-generated benchmark only. Original generator mother "
    "identities are unavailable; conservative shared VIN roots do not establish "
    "clean source independence or real-fleet generalization."
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(reference: str, manifest_path: Path) -> Path:
    path = Path(reference)
    if path.is_absolute() and path.exists():
        return path
    for candidate in (manifest_path.parent / path, manifest_path.parent / path.name):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"generated data bundle member missing: {path.name}")


@dataclass
class GeneratedDataset:
    rows: pd.DataFrame
    manifest_path: Path
    manifest_sha256: str
    split_sha256: str
    allow_exploratory_final: bool

    def subset(self, split: str) -> pd.DataFrame:
        if split == "final" and not self.allow_exploratory_final:
            raise ValueError("final is sealed; pass explicit exploratory-final authorization")
        if split not in {"train", "dev", "calibration", "final"}:
            raise ValueError("unknown split")
        return self.rows.loc[self.rows["split"].eq(split)].copy()


def load_generated_dataset(
    manifest_path: str | Path, *, allow_exploratory_final: bool = False,
) -> GeneratedDataset:
    """Verify the separate generated bundle and enforce its frozen root split."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("namespace") != NAMESPACE:
        raise ValueError("CH generated benchmark requires demo_synthetic namespace")
    sources = manifest.get("sources", [])
    if not sources or any(r.get("source_id") != SOURCE or r.get("origin") != ORIGIN for r in sources):
        raise ValueError("CH benchmark accepts only public_generated CH sources")
    tables = {}
    for name in ("identity_map", "segments", "targets"):
        entry = manifest["tables"][name]
        path = _resolve(entry["path"], manifest_path)
        if _sha256(path) != entry["sha256"]:
            raise ValueError(f"generated table checksum mismatch: {name}")
        # Ignore full waveform arrays here: this benchmark uses only the
        # published native summary statistics and their provenance columns.
        columns = (["physical_cell_id", "source_id", "root_scenario_id", "chemistry", "segment_id", "cycle_index", "provenance"] + list(FEATURE_NAMES)) if name == "segments" else None
        tables[name] = pd.read_parquet(path, columns=columns)
        if len(tables[name]) != entry["rows"]:
            raise ValueError(f"generated table row count mismatch: {name}")
    identities, segments, targets = (tables[k] for k in ("identity_map", "segments", "targets"))
    for frame in (identities, segments, targets):
        if frame.empty or not frame["source_id"].eq(SOURCE).all():
            raise ValueError("mixed or empty source table")
    if not identities["namespace"].eq(NAMESPACE).all():
        raise ValueError("mixed synthetic namespaces")
    if not segments["provenance"].eq(ORIGIN).all() or not targets["origin"].eq(ORIGIN).all():
        raise ValueError("mixed generated origins")
    if identities["physical_cell_id"].duplicated().any() or segments["segment_id"].duplicated().any():
        raise ValueError("duplicate generated identities or segments")
    targets = targets.loc[targets["target_name"].eq("fault")].copy()
    if targets["segment_id"].duplicated().any() or not targets["label_status"].eq("available").all():
        raise ValueError("fault labels must be available and unique per segment")
    if not set(targets["class_name"]).issubset(FAULT_CLASSES):
        raise ValueError("unknown published generated fault class")
    required = ["physical_cell_id", "source_id", "root_scenario_id", "chemistry", "segment_id", "cycle_index"]
    absent = set(required + list(FEATURE_NAMES)) - set(segments.columns)
    if absent:
        raise ValueError(f"native generated statistics missing: {sorted(absent)}")
    rows = segments[required + list(FEATURE_NAMES)].merge(
        targets[["segment_id", "physical_cell_id", "class_name"]],
        on=["segment_id", "physical_cell_id"], how="left", validate="one_to_one",
    )
    if rows["class_name"].isna().any() or len(rows) != len(targets):
        raise ValueError("generated labels do not cover exactly the observed segments")
    expected = identities.set_index("physical_cell_id")
    for row in rows.itertuples():
        if row.physical_cell_id not in expected.index:
            raise ValueError("segment identity absent from identity map")
        record = expected.loc[row.physical_cell_id]
        if row.root_scenario_id != record["root_scenario_id"] or row.chemistry != record["chemistry"]:
            raise ValueError("segment chemistry/root identity mismatch")
        if not isinstance(row.root_scenario_id, str) or not row.root_scenario_id:
            raise ValueError("conservative root identity required")
    split_path = _resolve(manifest["split_manifest"], manifest_path)
    split = json.loads(split_path.read_text(encoding="utf-8"))
    if split.get("group_column") != "root_scenario_id":
        raise ValueError("generated split must isolate conservative root_scenario_id")
    assignments = split["assignments"]
    rows["split"] = rows["physical_cell_id"].map(assignments)
    if not rows["split"].isin(["train", "dev", "calibration", "final"]).all():
        raise ValueError("generated split assignment missing or invalid")
    if rows.groupby("root_scenario_id")["split"].nunique().gt(1).any():
        raise ValueError("conservative VIN root leaks across splits")
    if rows.groupby(["root_scenario_id", "chemistry"])["class_name"].nunique().gt(1).any():
        raise ValueError("one root/chemistry has inconsistent generated class labels")
    root_assignments = split.get("root_assignments", {})
    if any(root_assignments.get(r.root_scenario_id) != r.split for r in rows.itertuples()):
        raise ValueError("physical split disagrees with frozen root assignments")
    rows["label"] = rows["class_name"].map(dict(zip(FAULT_CLASSES, range(len(FAULT_CLASSES)))))
    if not allow_exploratory_final:
        rows = rows.loc[~rows["split"].eq("final")].copy()
    return GeneratedDataset(rows.reset_index(drop=True), manifest_path, _sha256(manifest_path), _sha256(split_path), allow_exploratory_final)


def first_landmarks(rows: pd.DataFrame) -> pd.DataFrame:
    """First published charge snippet per conservative VIN and chemistry."""
    return rows.sort_values(["root_scenario_id", "chemistry", "cycle_index", "segment_id"]).drop_duplicates(
        ["root_scenario_id", "chemistry"], keep="first",
    )


def _matrix(rows: pd.DataFrame, features: tuple[str, ...] = FEATURE_NAMES) -> np.ndarray:
    values = rows.loc[:, list(features)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    values[~np.isfinite(values)] = np.nan
    return values


def _weights(rows: pd.DataFrame) -> np.ndarray:
    counts = rows["root_scenario_id"].value_counts()
    weights = rows["root_scenario_id"].map(lambda root: 1 / counts[root]).to_numpy()
    return weights / weights.mean()


def _tree_recipe(estimator: Any) -> dict[str, Any]:
    tree = estimator.tree_
    return {
        "left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
        "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
        "value": tree.value.reshape(tree.node_count, -1)[:, 0].tolist(),
    }


def _validate_tree(tree: dict[str, Any], width: int) -> None:
    names = ("left", "right", "feature", "threshold", "value")
    if set(tree) != set(names) or any(not isinstance(tree[k], list) for k in names):
        raise ValueError("invalid numerical tree recipe")
    n = len(tree["left"])
    if n < 1 or n > 100_000 or any(len(tree[k]) != n for k in names):
        raise ValueError("invalid numerical tree dimensions")
    if any(type(v) not in (int, float) for k in ("threshold", "value") for v in tree[k]):
        raise ValueError("tree thresholds and values must be JSON numbers")
    if not np.isfinite(np.asarray(tree["threshold"] + tree["value"], dtype=float)).all():
        raise ValueError("nonfinite numerical tree")
    reachable = set()
    pending = [0]
    while pending:
        node = pending.pop()
        if node in reachable or not 0 <= node < n:
            raise ValueError("tree has cycles, shared children or invalid child")
        reachable.add(node)
        left, right, feature = (tree[k][node] for k in ("left", "right", "feature"))
        if any(type(v) is not int for v in (left, right, feature)):
            raise ValueError("tree indexes must be integers")
        if left == right == -1:
            continue
        if not (0 <= left < n and 0 <= right < n and 0 <= feature < width):
            raise ValueError("tree child or feature out of bounds")
        pending.extend((left, right))
    if len(reachable) != n:
        raise ValueError("tree contains unreachable nodes")


def _tree_predict(tree: dict[str, Any], values: np.ndarray) -> np.ndarray:
    nodes = np.zeros(len(values), dtype=int)
    left, right, features, thresholds, leaves = (np.asarray(tree[k]) for k in ("left", "right", "feature", "threshold", "value"))
    # Recipes are validated on construction. The finite bound also prevents an
    # accidentally mutated in-memory recipe from looping forever.
    for _ in range(len(left)):
        active = left[nodes] >= 0
        if not active.any():
            return leaves[nodes]
        ix = np.flatnonzero(active)
        current = nodes[ix]
        nodes[ix] = np.where(values[ix, features[current]] <= thresholds[current], left[current], right[current])
    raise ValueError("tree traversal did not terminate")


class NumericalGBDT:
    """JSON-portable sklearn GBDT prediction with no estimator deserialization."""
    def __init__(self, recipe: dict[str, Any]):
        self.recipe = json.loads(json.dumps(recipe, allow_nan=False))
        recipe = self.recipe
        if recipe.get("kind") != "numerical_multiclass_gbdt" or recipe.get("class_names") != list(FAULT_CLASSES):
            raise ValueError("unsupported generated classifier recipe")
        if any(not isinstance(recipe.get(key), list) or any(type(v) not in (int, float) for v in recipe[key]) for key in ("medians", "initial")):
            raise ValueError("generated medians and logits must be JSON numeric arrays")
        medians = np.asarray(recipe.get("medians"), dtype=float)
        if recipe.get("feature_names") != list(FEATURE_NAMES) or medians.shape != (len(FEATURE_NAMES),) or not np.isfinite(medians).all():
            raise ValueError("invalid generated feature/imputation contract")
        initial = np.asarray(recipe.get("initial"), dtype=float)
        if initial.shape != (len(FAULT_CLASSES),) or not np.isfinite(initial).all():
            raise ValueError("invalid generated initial class logits")
        rate = recipe.get("learning_rate")
        if type(rate) not in (int, float) or not np.isfinite(rate) or not 0 < rate <= 1:
            raise ValueError("invalid generated learning rate")
        stages = recipe.get("trees")
        if not isinstance(stages, list) or not 1 <= len(stages) <= 10_000:
            raise ValueError("invalid generated GBDT stages")
        for stage in stages:
            if not isinstance(stage, list) or len(stage) != len(FAULT_CLASSES):
                raise ValueError("invalid generated class tree dimension")
            for tree in stage:
                _validate_tree(tree, len(FEATURE_NAMES))
        self.medians = medians

    @classmethod
    def fit(cls, rows: pd.DataFrame, *, seed: int = 0, n_estimators: int = 80,
            learning_rate: float = .05, max_depth: int = 2,
            min_samples_leaf: int = 3, subsample: float = .8) -> "NumericalGBDT":
        if rows.empty or not rows["split"].eq("train").all():
            raise ValueError("GBDT may fit only frozen train rows")
        y = rows["label"].to_numpy(dtype=int)
        if set(y) != set(range(len(FAULT_CLASSES))):
            raise ValueError("generated training chemistry must support all four fault classes")
        values = _matrix(rows)
        medians = np.array([np.median(column[np.isfinite(column)]) if np.isfinite(column).any() else 0. for column in values.T])
        values = np.where(np.isnan(values), medians, values)
        model = GradientBoostingClassifier(
            random_state=seed, n_estimators=n_estimators, learning_rate=learning_rate,
            max_depth=max_depth, min_samples_leaf=min_samples_leaf, subsample=subsample,
        ).fit(values, y, sample_weight=_weights(rows))
        exported = cls({
            "kind": "numerical_multiclass_gbdt", "class_names": list(FAULT_CLASSES),
            "feature_names": list(FEATURE_NAMES), "medians": medians.tolist(),
            "initial": np.log(model.init_.class_prior_).tolist(),
            "learning_rate": float(model.learning_rate),
            "trees": [[_tree_recipe(tree) for tree in stage] for stage in model.estimators_],
        })
        if not np.allclose(model.predict_proba(values), exported.predict_proba(rows), atol=1e-9):
            raise ValueError("generated GBDT JSON inference differs from live estimator")
        return exported

    def predict_logits(self, rows: pd.DataFrame) -> np.ndarray:
        values = _matrix(rows)
        # sklearn's trees cast incoming features to float32 before comparison.
        values = np.where(np.isnan(values), self.medians, values).astype(np.float32)
        logits = np.tile(self.recipe["initial"], (len(rows), 1)).astype(float)
        for stage in self.recipe["trees"]:
            logits += self.recipe["learning_rate"] * np.column_stack([_tree_predict(tree, values) for tree in stage])
        return logits

    def predict_proba(self, rows: pd.DataFrame, *, temperature: float = 1.) -> np.ndarray:
        if not np.isfinite(temperature) or temperature <= 0:
            raise ValueError("temperature must be finite and positive")
        return softmax(self.predict_logits(rows) / temperature, axis=1)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.recipe, allow_nan=False))


def fit_temperature(model: NumericalGBDT, rows: pd.DataFrame) -> dict[str, Any]:
    if not rows.empty and not rows["split"].eq("calibration").all():
        raise ValueError("probability calibration may use only isolated calibration rows")
    landmarks = first_landmarks(rows)
    counts = {c: int(landmarks["class_name"].eq(c).sum()) for c in FAULT_CLASSES}
    if len(landmarks) < 2 or landmarks["label"].nunique() < 2:
        return {"status": "unavailable", "temperature": 1., "reason": "too_few_calibration_VINs_or_classes", "class_counts": counts, "independent_vins": len(landmarks)}
    logits = model.predict_logits(landmarks)
    y = landmarks["label"].to_numpy(dtype=int)
    objective = lambda log_temperature: float(-np.log(np.clip(softmax(logits / np.exp(log_temperature), axis=1)[np.arange(len(y)), y], 1e-15, 1)).mean())
    result = minimize_scalar(objective, bounds=(np.log(.25), np.log(8.)), method="bounded")
    if not result.success:
        raise ValueError("temperature calibration optimization failed")
    return {
        "status": "fitted", "kind": "scalar_temperature_scaling", "temperature": float(np.exp(result.x)),
        "fit_split": "calibration", "class_counts": counts, "independent_vins": len(landmarks),
        "root_scenario_ids": sorted(landmarks["root_scenario_id"].unique().tolist()),
        "missing_calibration_classes": [c for c, count in counts.items() if not count],
        "limitation": "Small generated calibration set; no population calibration claim.",
    }


def _binary_ece(probabilities: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    total = 0.
    assignments = np.minimum((probabilities * bins).astype(int), bins - 1)
    for index in range(bins):
        mask = assignments == index
        if mask.any():
            total += mask.mean() * abs(float(probabilities[mask].mean() - labels[mask].mean()))
    return float(total)


def multiclass_metrics(rows: pd.DataFrame, probabilities: np.ndarray) -> dict[str, Any]:
    """Score only one frozen landmark per supplied independent VIN root."""
    probabilities = np.asarray(probabilities, dtype=float)
    if len(rows) == 0:
        return {"status": "unavailable", "reason": "empty_split", "independent_vins": 0}
    if rows["root_scenario_id"].duplicated().any():
        raise ValueError("metrics require one independent VIN landmark per root")
    if probabilities.shape != (len(rows), len(FAULT_CLASSES)) or not np.isfinite(probabilities).all() or (probabilities < 0).any() or not np.allclose(probabilities.sum(axis=1), 1):
        raise ValueError("invalid generated fault probability matrix")
    y = rows["label"].to_numpy(dtype=int)
    if not np.isin(y, np.arange(len(FAULT_CLASSES))).all():
        raise ValueError("invalid generated fault label")
    per_class = {}
    ap_scores = []
    onehot = np.eye(len(FAULT_CLASSES))[y]
    for index, name in enumerate(FAULT_CLASSES):
        label, probability = onehot[:, index], probabilities[:, index]
        positives, negatives = int(label.sum()), int((1 - label).sum())
        record = {
            "positive_VINs": positives, "negative_VINs": negatives,
            "small_positive_support": positives < 5,
            "brier": float(np.mean((probability - label) ** 2)),
            "ece_10_bins": _binary_ece(probability, label),
        }
        if positives and negatives:
            ap = float(average_precision_score(label, probability))
            ap_scores.append(ap)
            fpr, tpr, thresholds = roc_curve(label, probability)
            position = np.flatnonzero(tpr >= .9)[0]
            record.update(status="evaluated", auprc=ap, prevalence=positives / len(rows),
                          false_positive_rate_at_recall_0_9=float(fpr[position]),
                          threshold_at_recall_0_9=float(thresholds[position]))
        else:
            record.update(status="unavailable", auprc=None, reason="no_positive_VINs" if not positives else "no_negative_VINs")
        per_class[name] = record
    confidence = probabilities.max(axis=1)
    correct = (probabilities.argmax(axis=1) == y).astype(float)
    return {
        "status": "evaluated", "independent_vins": len(rows),
        "metric_unit": "first frozen charge landmark per conservative published VIN root",
        "macro_auprc": float(np.mean(ap_scores)) if ap_scores else None,
        "macro_auprc_scope": "classes with both positive and negative independent VINs",
        "macro_auprc_all_four_classes": float(np.mean(ap_scores)) if len(ap_scores) == len(FAULT_CLASSES) else None,
        "evaluable_class_count": len(ap_scores), "per_class": per_class,
        "multiclass_brier": float(np.mean(np.sum((probabilities - onehot) ** 2, axis=1))),
        "multiclass_log_loss": float(-np.log(np.clip(probabilities[np.arange(len(y)), y], 1e-15, 1)).mean()),
        "top_label_ece_10_bins": _binary_ece(confidence, correct),
        "evidence_status": "exploratory_generated_only", "limitation": LIMITATION,
    }


def train_chemistry_models(dataset: GeneratedDataset, *, seed: int, **parameters: Any) -> dict[str, Any]:
    models = {}
    train, calibration = dataset.subset("train"), dataset.subset("calibration")
    for chemistry in sorted(train["chemistry"].unique()):
        local = train.loc[train["chemistry"].eq(chemistry)]
        model = NumericalGBDT.fit(local, seed=seed, **parameters)
        calibrator = fit_temperature(model, calibration.loc[calibration["chemistry"].eq(chemistry)])
        models[chemistry] = {"model": model.to_dict(), "calibration": calibrator,
                             "fit_root_scenario_ids": sorted(local["root_scenario_id"].unique().tolist())}
    return {
        "schema_version": SCHEMA, "namespace": NAMESPACE, "origin": ORIGIN,
        "source_id": SOURCE, "seed": int(seed), "class_names": list(FAULT_CLASSES),
        "feature_names": list(FEATURE_NAMES), "feature_policy": "published native numeric mean/std statistics; train-only median imputation; independent chemistry GBDTs",
        "dataset_manifest_sha256": dataset.manifest_sha256, "split_manifest_sha256": dataset.split_sha256,
        "fit_split": "train", "calibration_split": "calibration", "chemistries": models,
        "evidence_status": "exploratory_generated_only", "limitation": LIMITATION,
    }


def evaluate_generated_split(dataset: GeneratedDataset, recipe: dict[str, Any], split: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if recipe.get("schema_version") != SCHEMA or recipe.get("namespace") != NAMESPACE or recipe.get("origin") != ORIGIN:
        raise ValueError("incompatible generated model recipe")
    if recipe.get("dataset_manifest_sha256") != dataset.manifest_sha256 or recipe.get("split_manifest_sha256") != dataset.split_sha256:
        raise ValueError("generated model belongs to a different frozen data bundle")
    rows = first_landmarks(dataset.subset(split))
    report, predictions = {}, []
    for chemistry, entry in recipe["chemistries"].items():
        local = rows.loc[rows["chemistry"].eq(chemistry)]
        model = NumericalGBDT(entry["model"])
        probabilities = model.predict_proba(local, temperature=entry["calibration"]["temperature"])
        report[chemistry] = multiclass_metrics(local, probabilities)
        for row, probability in zip(local.to_dict("records"), probabilities):
            predictions.append({k: row[k] for k in ("root_scenario_id", "physical_cell_id", "chemistry", "segment_id", "class_name", "label", "split")} | {"probabilities": probability.tolist()})
    if len(predictions) != len(rows):
        raise ValueError("evaluation chemistry not supported by training")
    # Two chemistry views sharing a conservative root are not independent VINs.
    # Average their calibrated probability vectors before the combined score.
    pooled_rows, pooled_probabilities = [], []
    frame = pd.DataFrame(predictions)
    if not frame.empty:
        for root, local in frame.groupby("root_scenario_id", sort=True):
            if local["label"].nunique() != 1:
                raise ValueError("pooled conservative VIN has conflicting labels")
            pooled_rows.append({"root_scenario_id": root, "label": int(local.iloc[0]["label"])})
            pooled_probabilities.append(np.mean(np.asarray(local["probabilities"].tolist()), axis=0))
    report["pooled_conservative_VIN"] = multiclass_metrics(pd.DataFrame(pooled_rows), np.asarray(pooled_probabilities))
    report["split"] = split
    report["final_policy"] = "explicitly opened exploratory final; excluded from selection" if split == "final" else "final remains excluded from selection"
    return report, predictions
