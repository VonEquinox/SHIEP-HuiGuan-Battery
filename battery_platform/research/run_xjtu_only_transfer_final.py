"""OOD transfer diagnostic: train shared 30D baselines on XJTU only.

MATR predictions are deliberately labeled out-of-domain.  They are useful for
the requested XJTU-only versus XJTU+MATR comparison, but they are not a
production-supported prediction path and do not use MATR labels for tuning.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from lightgbm import LGBMRegressor, early_stopping

from model_lab.modeling.v2.contracts import load_dataset, sha256_file

from run_source_aware_baselines_final import LSTM, MLP, cell_weights, scores

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "battery_platform/research/joint_xjtu_matr/bundles/final_comparison/combined/features.json"
OUT = ROOT / "battery_platform/research/joint_xjtu_matr/baselines/xjtu_only_transfer_final_20261002.json"
SEEDS = (0, 1, 2)


def prepare():
    manifest, arrays = load_dataset(BUNDLE)
    rows = manifest["rows"]
    x = arrays["features"].astype(np.float32)
    y = arrays["y_soh"].astype(float)
    split = np.asarray([r["split"] for r in rows])
    cells = np.asarray([r["physical_cell_id"] for r in rows])
    sources = np.asarray([r["source_id"] for r in rows])
    train = (split == "train") & (sources == "xjtu")
    median = np.nanmedian(np.where(np.isfinite(x[train]), x[train], np.nan), axis=0)
    x = np.where(np.isfinite(x), x, median)
    mean, std = x[train].mean(0), x[train].std(0)
    std[std < 1e-6] = 1.0
    x = (x - mean) / std
    domain = np.column_stack((sources == "xjtu", sources == "matr")).astype(np.float32)
    mlp_x = np.concatenate((x, domain), axis=1).astype(np.float32)
    values = np.log(y[train]); mu, sd = float(values.mean()), float(max(values.std(), 0.02))
    target = ((np.log(y) - mu) / sd).astype(np.float32)
    return manifest, x, mlp_x, domain, y, target, split, cells, sources, mu, sd


def fit_neural(kind, x, mlp_x, domain, target, y, split, cells, sources, mu, sd, seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.set_num_threads(1)
    train = (split == "train") & (sources == "xjtu")
    dev = (split == "dev") & (sources == "xjtu")
    final = split == "final"
    model = MLP(mlp_x.shape[1]) if kind == "mlp" else LSTM()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.001)
    tx = torch.tensor(mlp_x[train] if kind == "mlp" else x[train], dtype=torch.float32)
    td = torch.tensor(domain[train], dtype=torch.float32)
    ty = torch.tensor(target[train], dtype=torch.float32)
    weights = torch.tensor(cell_weights(cells[train]), dtype=torch.float32)
    best, state, epoch_best, stale = float("inf"), None, 0, 0
    for epoch in range(1, 301):
        model.train(); optimizer.zero_grad(set_to_none=True)
        out = model(tx) if kind == "mlp" else model(tx, td)
        loss = (((out - ty) ** 2) * weights).mean(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); optimizer.step()
        if epoch % 5: continue
        model.eval()
        with torch.no_grad():
            dx = torch.tensor(mlp_x[dev] if kind == "mlp" else x[dev], dtype=torch.float32)
            dd = torch.tensor(domain[dev], dtype=torch.float32)
            out = model(dx) if kind == "mlp" else model(dx, dd)
        prediction = np.exp(mu + sd * out.numpy())
        metric = scores(y[dev], prediction, cells[dev], sources[dev])["xjtu"]["cell_mae_pp"]
        if metric < best - 1e-9:
            best, epoch_best, stale = metric, epoch, 0
            state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            stale += 5
        if stale >= 60: break
    model.load_state_dict(state); model.eval()
    with torch.no_grad():
        fx = torch.tensor(mlp_x[final] if kind == "mlp" else x[final], dtype=torch.float32)
        fd = torch.tensor(domain[final], dtype=torch.float32)
        out = model(fx) if kind == "mlp" else model(fx, fd)
    prediction = np.exp(mu + sd * out.numpy())
    return {"method": kind, "seed": seed, "dev_selected_epochs": epoch_best,
            "final_scores": scores(y[final], prediction, cells[final], sources[final])}


def fit_lgbm(mlp_x, target, y, split, cells, sources, mu, sd, seed):
    train = (split == "train") & (sources == "xjtu")
    dev = (split == "dev") & (sources == "xjtu")
    final = split == "final"
    model = LGBMRegressor(n_estimators=800, learning_rate=0.03, num_leaves=31,
                          min_child_samples=12, reg_lambda=0.5, random_state=seed,
                          verbosity=-1, n_jobs=1)
    model.fit(mlp_x[train], target[train], sample_weight=cell_weights(cells[train]),
              eval_set=[(mlp_x[dev], target[dev])],
              callbacks=[early_stopping(60, verbose=False)])
    prediction = np.exp(mu + sd * model.predict(mlp_x[final], num_iteration=model.best_iteration_))
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
        results.append(fit_lgbm(mlp_x, target, y, split, cells, sources, mu, sd, seed))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"scope": "XJTU-only training with MATR OOD transfer diagnostic",
               "bundle": str(BUNDLE), "bundle_sha256": sha256_file(BUNDLE),
               "train_source": "xjtu", "matr_labels_used_for_selection": False,
               "final_objects": sorted(set(cells[split == "final"])), "methods": results}
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
