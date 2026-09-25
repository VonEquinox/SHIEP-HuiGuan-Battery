#!/usr/bin/env python3
"""Bounded SOH development comparison on explicit canonical cell CSVs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from model_lab.data.window_dataset import DEFAULT_DERIVED_FEATURES, PrefixWindowDataset, eligible_indices, fit_scaler, load_canonical_csv, split_cell_indices
from model_lab.modeling.cada import CADA, CPMLPLike, MLPMatched, MLPRegressor


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def metric_rows(rows: list[dict[str, object]]) -> dict[str, float]:
    if not rows:
        return {"mae_pct": float("nan"), "rmse_pct": float("nan"), "cell_macro_mae_pct": float("nan"), "cell_macro_rmse_pct": float("nan")}
    errors = np.array([float(r["prediction"]) - float(r["target"]) for r in rows], dtype=np.float64) * 100
    by_cell: dict[str, list[float]] = {}
    for row, err in zip(rows, errors):
        by_cell.setdefault(str(row["cell_id"]), []).append(float(err))
    return {"mae_pct": float(np.mean(np.abs(errors))), "rmse_pct": float(np.sqrt(np.mean(errors**2))), "cell_macro_mae_pct": float(np.mean([np.mean(np.abs(v)) for v in by_cell.values()])), "cell_macro_rmse_pct": float(np.mean([np.sqrt(np.mean(np.array(v)**2)) for v in by_cell.values()]))}


def vectorize(batch: dict[str, object]) -> np.ndarray:
    current = batch["current"].numpy()
    reference = batch["reference"].numpy()
    history = batch["history"].numpy()
    mask = batch["history_mask"].numpy()
    denom = np.maximum(mask.sum(axis=1, keepdims=True), 1)
    mean = (history * mask[..., None]).sum(axis=1) / denom
    slope = history[:, -1] - history[:, 0]
    return np.concatenate([current, reference, current - reference, mean, slope, mask.mean(axis=1, keepdims=True)], axis=1)


def collect(ds: PrefixWindowDataset, indices: list[int], batch_size: int = 64) -> tuple[np.ndarray, np.ndarray, list[dict[str, object]]]:
    loader = DataLoader(torch.utils.data.Subset(ds, indices), batch_size=batch_size, shuffle=False, num_workers=0)
    features, targets, rows = [], [], []
    for batch in loader:
        features.append(vectorize(batch))
        targets.append(batch["target"].numpy())
        for cell, cycle, row_index, target, provenance in zip(batch["cell_id"], batch["cycle_id"].tolist(), batch["row_index"].tolist(), batch["target"].tolist(), batch["label_provenance"]):
            rows.append({"cell_id": cell, "cycle_id": int(cycle), "row_index": int(row_index), "target": float(target), "label_provenance": provenance})
    return np.concatenate(features), np.concatenate(targets), rows


def torch_predict(model: nn.Module, ds: PrefixWindowDataset, indices: list[int], device: torch.device) -> list[dict[str, object]]:
    loader = DataLoader(torch.utils.data.Subset(ds, indices), batch_size=32, shuffle=False, num_workers=0)
    output = []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            prediction = model(batch["current"].to(device), batch["reference"].to(device), batch["history"].to(device), batch["history_mask"].to(device), batch["quality_gate"].to(device)).detach().cpu().numpy()
            for cell, cycle, row_index, target, pred, provenance in zip(batch["cell_id"], batch["cycle_id"].tolist(), batch["row_index"].tolist(), batch["target"].tolist(), prediction.tolist(), batch["label_provenance"]):
                output.append({"cell_id": cell, "cycle_id": int(cycle), "row_index": int(row_index), "target": float(target), "prediction": float(pred), "label_provenance": provenance})
    return output


def write_predictions(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["cell_id", "cycle_id", "row_index", "target", "prediction", "label_provenance"])
        writer.writeheader(); writer.writerows(rows)


def train_neural(name: str, model: nn.Module, train_ds: PrefixWindowDataset, val_ds: PrefixWindowDataset, out: Path, seed: int, epochs: int, device: torch.device, target_mean: float = 0.0, target_std: float = 1.0) -> tuple[dict[str, object], list[dict[str, object]]]:
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    criterion = nn.MSELoss()
    train_indices = list(range(len(train_ds)))
    val_indices = list(range(len(val_ds)))
    loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    history: list[dict[str, object]] = []
    best_mae = float("inf")
    best_path = out / f"{name}-seed{seed}-best.pt"
    last_path = out / f"{name}-seed{seed}-last.pt"
    for epoch in range(epochs):
        model.train(); losses = []
        for batch in loader:
            optimizer.zero_grad(set_to_none=True)
            prediction = model(batch["current"].to(device), batch["reference"].to(device), batch["history"].to(device), batch["history_mask"].to(device), batch["quality_gate"].to(device))
            loss = criterion((prediction - target_mean) / target_std, (batch["target"].to(device) - target_mean) / target_std)
            if not torch.isfinite(loss):
                raise ValueError(f"non-finite loss in {name} epoch {epoch}")
            loss.backward(); optimizer.step(); losses.append(float(loss.detach().cpu()))
        val_rows = torch_predict(model, val_ds, val_indices, device)
        val_metric = metric_rows(val_rows)
        record = {"epoch": epoch, "train_loss": float(np.mean(losses)), **val_metric}
        history.append(record)
        torch.save({"model": model.state_dict(), "seed": seed, "name": name, "epoch": epoch, "target_scaling": [target_mean, target_std], "in_features": train_ds.dim}, last_path)
        if val_metric["cell_macro_mae_pct"] < best_mae:
            best_mae = val_metric["cell_macro_mae_pct"]
            torch.save({"model": model.state_dict(), "seed": seed, "name": name, "epoch": epoch, "target_scaling": [target_mean, target_std], "in_features": train_ds.dim}, best_path)
    (out / f"{name}-seed{seed}-history.json").write_text(json.dumps(history, indent=2) + "\n")
    if not best_path.is_file():
        raise ValueError("No finite validation checkpoint was produced")
    model.load_state_dict(torch.load(best_path, map_location=device, weights_only=True)["model"])
    rows = torch_predict(model, val_ds, val_indices, device)
    return {**metric_rows(rows), "parameters": sum(p.numel() for p in model.parameters()), "best_checkpoint": str(best_path), "last_checkpoint": str(last_path), "history": str(out / f"{name}-seed{seed}-history.json")}, rows


def main(args: argparse.Namespace) -> int:
    torch.set_num_threads(min(4, torch.get_num_threads()))
    paths = sorted(Path().glob(args.data_glob))
    if not paths:
        raise SystemExit(f"no CSV paths matched {args.data_glob!r}")
    cells = load_canonical_csv(paths, feature_allowlist=DEFAULT_DERIVED_FEATURES)
    train_cells, val_cells, test_cells = split_cell_indices(cells)
    scaler = fit_scaler(cells, train_cells)
    train_ds = PrefixWindowDataset(cells, eligible_indices(cells, train_cells), scaler)
    val_ds = PrefixWindowDataset(cells, eligible_indices(cells, val_cells), scaler)
    test_ds = PrefixWindowDataset(cells, eligible_indices(cells, test_cells), scaler)
    if not len(train_ds) or not len(val_ds):
        raise SystemExit("need train and validation cells with finite capacity rows")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    source_hashes = {str(path): sha256_file(path) for path in paths}
    split = {"train": [cells[i].cell_id for i in train_cells], "validation": [cells[i].cell_id for i in val_cells], "test": [cells[i].cell_id for i in test_cells], "scaler": {"mean": scaler["mean"].tolist(), "std": scaler["std"].tolist()}, "feature_columns": list(cells[0].feature_columns), "reference": "first observed capacity; early-calibrated SOH", "source_hashes": source_hashes, "status": "development split; test frozen and not evaluated"}
    (out / "split.json").write_text(json.dumps(split, indent=2) + "\n")
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    results: list[dict[str, object]] = []
    train_x, train_y, _ = collect(train_ds, list(range(len(train_ds))))
    val_x, val_y, val_rows = collect(val_ds, list(range(len(val_ds))))
    from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from joblib import dump
    from model_lab.modeling.cada import TargetScaledRegressor
    estimators = {
        "ridge": Ridge(alpha=1.0),
        "hist_gradient_boosting": HistGradientBoostingRegressor(max_iter=50, max_leaf_nodes=15, random_state=0),
        "extra_trees": ExtraTreesRegressor(n_estimators=50, max_depth=8, random_state=0, n_jobs=1),
    }
    baseline_models = {"dummy_mean": np.full(len(val_y), float(np.mean(train_y)))}
    for name, estimator in estimators.items():
        estimator.fit(train_x, train_y)
        baseline_models[name] = estimator.predict(val_x)
        dump(estimator, out / f"{name}.joblib")
    for name, predictions in baseline_models.items():
        rows = [{**row, "prediction": float(pred)} for row, pred in zip(val_rows, predictions)]
        write_predictions(out / f"predictions-{name}.csv", rows)
        results.append({"model": name, "seed": 0, "device": "cpu", "status": "smoke", **metric_rows(rows)})
    for seed in [int(x) for x in args.seeds.split(",")]:
        seed_all(seed)
        for name, model in [("mlp_current_only", MLPRegressor(train_ds.dim)), ("mlp_matched", MLPMatched(train_ds.dim)), ("cpmlp_like", CPMLPLike(train_ds.dim)), ("cada_v0", CADA(train_ds.dim))]:
            try:
                target_mean = float(np.mean(train_y)) if args.standardize_target else 0.0
                target_std = max(float(np.std(train_y)), 1e-6) if args.standardize_target else 1.0
                if args.standardize_target:
                    model = TargetScaledRegressor(model, target_mean, target_std)
                metrics, rows = train_neural(name, model, train_ds, val_ds, out, seed, args.epochs, device, target_mean, target_std)
                write_predictions(out / f"predictions-{name}-seed{seed}.csv", rows)
                results.append({"model": name, "seed": seed, "device": str(device), "status": "smoke", **metrics})
            except Exception as exc:  # preserve failure evidence and continue bounded comparison
                results.append({"model": name, "seed": seed, "device": str(device), "status": "failed", "error": repr(exc)})
    config = {"created_at": now(), "data_glob": args.data_glob, "source_hashes": source_hashes, "cell_count": len(cells), "feature_count": train_ds.dim, "feature_columns": list(cells[0].feature_columns), "epochs": args.epochs, "seeds": [int(x) for x in args.seeds.split(",")], "torch_threads": torch.get_num_threads(), "num_workers": 0, "batch_size": 32, "device": str(device), "mps_built": torch.backends.mps.is_built(), "mps_available": torch.backends.mps.is_available(), "label_provenance": sorted({p for cell in cells for p in cell.label_provenance}), "primary_soh_metric": "not_primary_unknown_author_derived_capacity", "test_evaluation": "not_run_until_model_freeze", "models": ["dummy_mean", "ridge", "hist_gradient_boosting", "extra_trees", "mlp_current_only", "mlp_matched", "cpmlp_like", "cada_v0"]}
    config["standardize_target"] = args.standardize_target
    config["target_scaler_fit_scope"] = "training cells only"
    config["reported_checkpoint"] = "best_validation_cell_macro_mae"
    config["code_hashes"] = {str(p): sha256_file(p) for p in [Path(__file__), Path("model_lab/modeling/cada.py"), Path("model_lab/data/window_dataset.py")]}
    (out / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (out / "summary.json").write_text(json.dumps({"config": config, "split": split, "results": results}, indent=2) + "\n")
    print(json.dumps({"config": config, "split": split, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-glob", required=True)
    parser.add_argument("--out", default="model_lab/reports/dev_run")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--standardize-target", action="store_true", help="Fit target mean/std on training cells only for all neural models")
    raise SystemExit(main(parser.parse_args()))
