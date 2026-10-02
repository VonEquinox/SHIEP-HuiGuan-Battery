"""One-time final evaluation for fixed MLP/LSTM/LightGBM 30D baselines.

The final bundle is loaded only after the train-only scaler and dev-based
early-stopping epoch/iteration have been fixed.  The script never uses final
labels for selection and writes an immutable JSON receipt.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from lightgbm import LGBMRegressor, early_stopping

from model_lab.modeling.v2.contracts import load_dataset, sha256_file


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "battery_platform/research/joint_xjtu_matr/bundles/final_comparison/combined/features.json"
OUT = ROOT / "battery_platform/research/joint_xjtu_matr/baselines/source_aware_final_20261002.json"
SEEDS = (0, 1, 2)


def cell_weights(cells: np.ndarray) -> np.ndarray:
    _, inv, counts = np.unique(cells, return_inverse=True, return_counts=True)
    weights = 1.0 / counts[inv]
    return weights / weights.mean()


def scores(y: np.ndarray, p: np.ndarray, cells: np.ndarray, sources: np.ndarray) -> dict:
    out: dict[str, dict] = {}
    for source in ("xjtu", "matr"):
        mask = sources == source
        per_cell = []
        for cell in sorted(set(cells[mask])):
            cmask = mask & (cells == cell)
            err = (p[cmask] - y[cmask]) * 100.0
            per_cell.append({
                "cell": str(cell),
                "rows": int(cmask.sum()),
                "mae_pp": float(np.abs(err).mean()),
                "rmse_pp": float(np.sqrt(np.mean(err * err))),
            })
        out[source] = {
            "cells": len(per_cell),
            "rows": int(mask.sum()),
            "cell_mae_pp": float(np.mean([r["mae_pp"] for r in per_cell])),
            "cell_rmse_pp": float(np.mean([r["rmse_pp"] for r in per_cell])),
            "per_cell": per_cell,
        }
    return out


class MLP(torch.nn.Module):
    def __init__(self, width: int):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(width, 128), torch.nn.ReLU(),
            torch.nn.Linear(128, 64), torch.nn.ReLU(),
            torch.nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)[:, 0]


class LSTM(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.rnn = torch.nn.LSTM(1, 32, batch_first=True)
        self.head = torch.nn.Sequential(
            torch.nn.Linear(34, 32), torch.nn.ReLU(), torch.nn.Linear(32, 1)
        )

    def forward(self, x: torch.Tensor, domain: torch.Tensor) -> torch.Tensor:
        hidden = self.rnn(x.unsqueeze(-1))[0][:, -1]
        return self.head(torch.cat((hidden, domain), dim=1))[:, 0]


def prepare():
    manifest, arrays = load_dataset(BUNDLE)
    rows = manifest["rows"]
    x = arrays["features"].astype(np.float32)
    y = arrays["y_soh"].astype(float)
    split = np.asarray([r["split"] for r in rows])
    cells = np.asarray([r["physical_cell_id"] for r in rows])
    sources = np.asarray([r["source_id"] for r in rows])
    train = split == "train"
    median = np.nanmedian(np.where(np.isfinite(x[train]), x[train], np.nan), axis=0)
    x = np.where(np.isfinite(x), x, median)
    mean = x[train].mean(axis=0)
    std = x[train].std(axis=0)
    std[std < 1e-6] = 1.0
    x = (x - mean) / std
    domain = np.column_stack((sources == "xjtu", sources == "matr")).astype(np.float32)
    mlp_x = np.concatenate((x, domain), axis=1).astype(np.float32)
    log_mu, log_sd = {}, {}
    for source in ("xjtu", "matr"):
        values = np.log(y[train & (sources == source)])
        log_mu[source] = float(values.mean())
        log_sd[source] = float(max(values.std(), 0.02))
    target = np.asarray([
        (np.log(v) - log_mu[s]) / log_sd[s] for v, s in zip(y, sources)
    ], dtype=np.float32)
    return manifest, x, mlp_x, domain, y, target, split, cells, sources, log_mu, log_sd


def fit_neural(kind, x, mlp_x, domain, target, y, split, cells, sources, log_mu, log_sd, seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.set_num_threads(1)
    train, dev, final = split == "train", split == "dev", split == "final"
    model = MLP(mlp_x.shape[1]) if kind == "mlp" else LSTM()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.001)
    tx = torch.tensor(mlp_x[train] if kind == "mlp" else x[train], dtype=torch.float32)
    td = torch.tensor(domain[train], dtype=torch.float32)
    ty = torch.tensor(target[train], dtype=torch.float32)
    weights = torch.tensor(cell_weights(cells[train]), dtype=torch.float32)
    best_score, best_state, best_epoch, stale = float("inf"), None, 0, 0
    for epoch in range(1, 301):
        model.train(); optimizer.zero_grad(set_to_none=True)
        out = model(tx) if kind == "mlp" else model(tx, td)
        loss = (((out - ty) ** 2) * weights).mean(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); optimizer.step()
        if epoch % 5:
            continue
        model.eval()
        with torch.no_grad():
            dx = torch.tensor(mlp_x[dev] if kind == "mlp" else x[dev], dtype=torch.float32)
            dd = torch.tensor(domain[dev], dtype=torch.float32)
            pred = model(dx) if kind == "mlp" else model(dx, dd)
            pred = np.asarray([
                np.exp(log_mu[s] + log_sd[s] * value)
                for s, value in zip(sources[dev], pred.numpy())
            ])
        score = scores(y[dev], pred, cells[dev], sources[dev])["xjtu"]["cell_mae_pp"]
        score += scores(y[dev], pred, cells[dev], sources[dev])["matr"]["cell_mae_pp"]
        if score < best_score - 1e-9:
            best_score, best_epoch = score, epoch
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 5
        if stale >= 60:
            break
    model.load_state_dict(best_state); model.eval()
    with torch.no_grad():
        fx = torch.tensor(mlp_x[final] if kind == "mlp" else x[final], dtype=torch.float32)
        fd = torch.tensor(domain[final], dtype=torch.float32)
        output = model(fx) if kind == "mlp" else model(fx, fd)
    prediction = np.asarray([
        np.exp(log_mu[s] + log_sd[s] * value)
        for s, value in zip(sources[final], output.numpy())
    ])
    return {"method": kind, "seed": seed, "dev_selected_epochs": best_epoch,
            "dev_selection_score_sum_pp": best_score,
            "final_scores": scores(y[final], prediction, cells[final], sources[final])}


def fit_lightgbm(mlp_x, target, y, split, cells, sources, log_mu, log_sd, seed):
    train, dev, final = split == "train", split == "dev", split == "final"
    model = LGBMRegressor(
        n_estimators=800, learning_rate=0.03, num_leaves=31,
        min_child_samples=12, reg_lambda=0.5, random_state=seed,
        verbosity=-1, n_jobs=1,
    )
    weights = cell_weights(cells[train])
    model.fit(mlp_x[train], target[train], sample_weight=weights,
              eval_set=[(mlp_x[dev], target[dev])],
              callbacks=[early_stopping(60, verbose=False)])
    values = model.predict(mlp_x[final], num_iteration=model.best_iteration_)
    prediction = np.asarray([
        np.exp(log_mu[s] + log_sd[s] * value)
        for s, value in zip(sources[final], values)
    ])
    return {"method": "lightgbm", "seed": seed,
            "dev_selected_iterations": int(model.best_iteration_ or 800),
            "final_scores": scores(y[final], prediction, cells[final], sources[final])}


def main():
    manifest, x, mlp_x, domain, y, target, split, cells, sources, mu, sd = prepare()
    results = []
    for kind in ("mlp", "lstm"):
        for seed in SEEDS:
            results.append(fit_neural(kind, x, mlp_x, domain, target, y, split, cells, sources, mu, sd, seed))
    for seed in SEEDS:
        results.append(fit_lightgbm(mlp_x, target, y, split, cells, sources, mu, sd, seed))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "scope": "one-time historical-exposed XJTU comparison final plus MATR final",
        "bundle": str(BUNDLE), "bundle_sha256": sha256_file(BUNDLE),
        "final_rows": int((split == "final").sum()),
        "final_objects": sorted(set(cells[split == "final"])),
        "selection_split": "dev", "final_labels_used_for_selection": False,
        "methods": results,
    }
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
