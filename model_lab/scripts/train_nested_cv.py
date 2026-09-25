"""Round-3 nested cell development evaluation; never scores heldout cells."""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from model_lab.modeling.anchored_conditional import AnchoredConditionalResidual
from model_lab.modeling.conditional_kernel import ConditionalDifferenceKernel
from model_lab.modeling.conditional_reference import FiLMReferencePotential
from model_lab.modeling.embedded_potential import EmbeddedReferenceModel, fit_numeric_bins
from model_lab.modeling.reference_potential import MatchedMLP


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "reports/round2/cv_physical/view_bundle.npz"
FOLDS = ROOT / "reports/round2/cv_physical/preregistration.json"
PROTOCOL = ROOT / "docs/ROUND3_PROTOCOL.md"
OUT = ROOT / "reports/round3/nested"
SEEDS = (0, 1, 2)
DETERMINISTIC = {"ridge_matched", "conditional_kernel"}
METHODS = ("ridge_matched", "extra_trees_matched", "conditional_kernel", "matched_mlp", "tabm_embedded",
           "film_context", "film_no_context", "anchored_conditional")
CONFIGS = {
    "ridge_matched": ({"alpha": .1}, {"alpha": 10.}, {"alpha": 1000.}),
    "extra_trees_matched": ({"min_samples_leaf": 1}, {"min_samples_leaf": 3}, {"min_samples_leaf": 7}),
    "conditional_kernel": ({"alpha": .01, "gamma": .25/142},
                           {"alpha": .1, "gamma": 1/142},
                           {"alpha": 1., "gamma": 4/142}),
    "matched_mlp": tuple({"width": 96, "lr": lr, "weight_decay": .001} for lr in (.0005, .002, .006)),
    "tabm_embedded": tuple({"width": 96, "members": 8, "bins": 16, "lr": lr, "weight_decay": .001} for lr in (.0005, .002, .006)),
    "film_context": tuple({"width": 32, "members": 4, "lr": lr, "weight_decay": .001} for lr in (.0005, .002, .006)),
    "film_no_context": tuple({"width": 32, "members": 4, "lr": lr, "weight_decay": .001} for lr in (.0005, .002, .006)),
    "anchored_conditional": tuple({"width": 24, "rank": 4, "lr": lr, "weight_decay": .01} for lr in (.0005, .002, .006)),
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def state_digest(state: dict) -> str:
    h = hashlib.sha256()
    for key, value in sorted(state.items()):
        h.update(key.encode())
        h.update(value.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


@dataclass
class DevData:
    x: np.ndarray
    reference: np.ndarray
    log_ratio: np.ndarray
    soh: np.ndarray
    cell: np.ndarray
    batch: np.ndarray
    source_row: np.ndarray


def load_development(view: Path) -> tuple[DevData, list[str]]:
    with np.load(view, allow_pickle=False) as raw:
        held = np.asarray(raw["holdout"], dtype=bool)
        dev = np.flatnonzero(~held)
        held_cells = sorted(set(map(str, raw["cell"][held])))
        data = DevData(np.asarray(raw["x"][dev], dtype=np.float32),
                       np.asarray(raw["reference"][dev], dtype=np.float32),
                       np.asarray(raw["log_window_ratio"][dev], dtype=np.float32),
                       np.asarray(raw["soh"][dev], dtype=np.float64),
                       np.asarray(raw["cell"][dev]), np.asarray(raw["protocol"][dev]), dev)
    if data.x.shape[1] != 71 or data.reference.shape != data.x.shape:
        raise ValueError("expected existing 71D view")
    if len(set(data.cell) & set(held_cells)) or len(set(data.cell)) != 21 or len(held_cells) != 3:
        raise ValueError("development/holdout cell contract changed")
    if not np.isfinite(data.soh).all() or np.any(data.soh <= 0):
        raise ValueError("invalid development labels")
    return data, held_cells


def cell_indices(data: DevData, names: list[str]) -> np.ndarray:
    idx = np.flatnonzero(np.isin(data.cell, names))
    if set(map(str, data.cell[idx])) != set(names):
        raise ValueError("fold names do not match view")
    return idx


def split_indices(data: DevData, fold: dict, fold_number: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    outer_train = cell_indices(data, fold["train_cells"])
    outer_valid = cell_indices(data, fold["validation_cells"])
    if set(data.cell[outer_train]) & set(data.cell[outer_valid]):
        raise ValueError("outer cell overlap")
    if set(np.r_[outer_train, outer_valid]) != set(range(len(data.cell))):
        raise ValueError("outer fold incomplete")
    selected = []
    for batch in sorted(set(data.batch[outer_train])):
        choices = sorted(set(map(str, data.cell[outer_train][data.batch[outer_train] == batch])))
        if len(choices) < 2:
            raise ValueError("inner batch cannot retain train and validation cells")
        selected.append(min(choices, key=lambda c: hashlib.sha256(
            f"round3-inner-2047|{fold_number}|{c}".encode()).hexdigest()))
    inner_valid = outer_train[np.isin(data.cell[outer_train], selected)]
    inner_train = outer_train[~np.isin(data.cell[outer_train], selected)]
    groups = [set(data.cell[idx]) for idx in (inner_train, inner_valid, outer_valid)]
    if any(groups[i] & groups[j] for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("inner or outer cell overlap")
    return inner_train, inner_valid, outer_train, outer_valid


def fit_transform(data: DevData, train: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    observed = np.concatenate((data.x[train], data.reference[train]))
    median = np.nanmedian(np.where(np.isfinite(observed), observed, np.nan), axis=0)
    median = np.nan_to_num(median)
    observed = np.where(np.isfinite(observed), observed, median)
    scaler = StandardScaler().fit(observed)
    def transform(z):
        return scaler.transform(np.where(np.isfinite(z), z, median)).astype(np.float32)
    return transform(data.x), transform(data.reference), {"median": median, "mean": scaler.mean_, "scale": scaler.scale_}


def matched(x: np.ndarray, r: np.ndarray, q: np.ndarray) -> np.ndarray:
    return np.concatenate((x, r, x-r, q[:, None]), axis=1)


def weights(cell: np.ndarray) -> np.ndarray:
    _, inv, counts = np.unique(cell, return_inverse=True, return_counts=True)
    weight = 1. / counts[inv]
    return weight / weight.mean()


def cell_metrics(y: np.ndarray, pred: np.ndarray, cell: np.ndarray) -> dict:
    by_cell = []
    for name in sorted(set(map(str, cell))):
        mask = cell == name
        error = (pred[mask] - y[mask]) * 100.
        by_cell.append({"cell": name, "n": int(mask.sum()),
                        "mae_pp": float(np.mean(np.abs(error))),
                        "rmse_pp": float(np.sqrt(np.mean(error**2)))})
    return {"cell_mae_pp": float(np.mean([r["mae_pp"] for r in by_cell])),
            "cell_rmse_pp": float(np.mean([r["rmse_pp"] for r in by_cell])),
            "cells": by_cell}


def make_model(name: str, dimension: int, cfg: dict, bins=None):
    if name == "matched_mlp":
        return MatchedMLP(dimension, cfg["width"])
    if name == "tabm_embedded":
        return EmbeddedReferenceModel(dimension, bins, cfg["width"], cfg["members"], False)
    if name in ("film_context", "film_no_context"):
        return FiLMReferencePotential(dimension, cfg["width"], cfg["members"], name == "film_context")
    if name == "anchored_conditional":
        return AnchoredConditionalResidual(dimension, cfg["width"], cfg["rank"])
    raise ValueError(name)


def model_output(model, name: str, x, r, q, mu: float, scale: float):
    raw = model(x, r, q) if name in ("matched_mlp", "tabm_embedded") else model(x, r)
    return mu + scale * raw if name in ("matched_mlp", "tabm_embedded") else scale * raw


def fit_neural(data: DevData, sx: np.ndarray, sr: np.ndarray, name: str, cfg: dict,
               seed: int, train: np.ndarray, valid: np.ndarray | None,
               device: torch.device, max_updates: int, patience: int,
               fixed_updates: int | None = None, bins=None) -> dict:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    model = make_model(name, sx.shape[1], cfg, bins).to(device)
    mu = float(np.log(data.soh[train]).mean())
    scale = max(float(np.log(data.soh[train]).std()), .02)
    tx = torch.as_tensor(sx[train], device=device); tr = torch.as_tensor(sr[train], device=device)
    tq = torch.as_tensor(data.log_ratio[train], device=device)
    ty = torch.as_tensor(np.log(data.soh[train]), device=device, dtype=torch.float32)
    tw = torch.as_tensor(weights(data.cell[train]), device=device, dtype=torch.float32)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    best = float("inf"); best_epoch = 0; best_state = None; bad = 0; history = []
    limit = fixed_updates if fixed_updates is not None else max_updates
    for epoch in range(1, limit + 1):
        model.train(); opt.zero_grad(set_to_none=True)
        output = model_output(model, name, tx, tr, tq, mu, scale)
        loss = (((output - ty[:, None]) / scale).square().mean(1) * tw).mean()
        if name == "anchored_conditional":
            _, bilinear, nonlinear = model.components(tx, tr)
            loss = loss + .01 * (bilinear + nonlinear).square().mean()
        if not torch.isfinite(loss):
            raise ValueError(f"nonfinite train loss at update {epoch}")
        loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5.); opt.step()
        if fixed_updates is None and (epoch % 5 == 0 or epoch == limit):
            pred = predict_neural(model, name, sx[valid], sr[valid], data.log_ratio[valid], mu, scale, device)
            score = cell_metrics(data.soh[valid], pred, data.cell[valid])["cell_mae_pp"]
            history.append({"update": epoch, "train_loss": float(loss.detach().cpu()), "inner_cell_mae_pp": score})
            if not np.isfinite(score):
                raise ValueError("nonfinite inner score")
            if score < best - 1e-8:
                best, best_epoch, bad = score, epoch, 0
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            else:
                bad += 5
            if bad >= patience:
                break
    if fixed_updates is None:
        if best_state is None:
            raise ValueError("no selected inner checkpoint")
        model.load_state_dict(best_state)
    else:
        best_epoch = fixed_updates
        best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    train_pred = predict_neural(model, name, sx[train], sr[train], data.log_ratio[train], mu, scale, device)
    result = {"model": model, "state": best_state, "state_sha256": state_digest(best_state),
              "best_epoch": best_epoch,
              "parameters": sum(p.numel() for p in model.parameters() if p.grad is not None),
              "parameters_total": sum(p.numel() for p in model.parameters()),
              "mu": mu, "scale": scale, "history": history,
              "train_cell_mae_pp": cell_metrics(data.soh[train], train_pred, data.cell[train])["cell_mae_pp"]}
    if valid is not None:
        result["valid_pred"] = predict_neural(model, name, sx[valid], sr[valid], data.log_ratio[valid], mu, scale, device)
    return result


def predict_neural(model, name, x, r, q, mu, scale, device) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        tx = torch.as_tensor(x, device=device); tr = torch.as_tensor(r, device=device)
        tq = torch.as_tensor(q, device=device)
        log_pred = model_output(model, name, tx, tr, tq, mu, scale).mean(1)
        pred = torch.exp(log_pred).detach().cpu().numpy().astype(float)
    if not np.isfinite(pred).all() or np.any(pred <= 0):
        raise ValueError("nonfinite or nonpositive prediction")
    return pred


def fit_classic(data: DevData, z: np.ndarray, name: str, cfg: dict, seed: int,
                train: np.ndarray, valid: np.ndarray | None) -> dict:
    mu = float(np.log(data.soh[train]).mean())
    scale = max(float(np.log(data.soh[train]).std()), .02)
    if name == "ridge_matched":
        model = Ridge(alpha=cfg["alpha"], solver="svd")
    elif name == "extra_trees_matched":
        model = ExtraTreesRegressor(min_samples_leaf=cfg["min_samples_leaf"],
                                    n_estimators=300, n_jobs=4, random_state=seed)
    else:
        raise ValueError(name)
    model.fit(z[train], (np.log(data.soh[train]) - mu) / scale,
              sample_weight=weights(data.cell[train]))
    def predict(idx):
        return np.exp(mu + scale * model.predict(z[idx]))
    train_pred = predict(train)
    result = {"model": model, "state_sha256": hashlib.sha256(pickle.dumps(model)).hexdigest(),
              "best_epoch": None, "parameters": None, "parameters_total": None,
              "mu": mu, "scale": scale,
              "train_cell_mae_pp": cell_metrics(data.soh[train], train_pred, data.cell[train])["cell_mae_pp"]}
    if valid is not None:
        result["valid_pred"] = predict(valid)
    return result


def fit_kernel(data: DevData, sx: np.ndarray, sr: np.ndarray, cfg: dict,
               train: np.ndarray, valid: np.ndarray | None) -> dict:
    model = ConditionalDifferenceKernel(**cfg).fit(
        sx[train], sr[train], np.log(data.soh[train]), weights(data.cell[train]))
    def predict(idx):
        return np.exp(model.predict_log(sx[idx], sr[idx]))
    result = {"model": model, "state_sha256": hashlib.sha256(pickle.dumps(model)).hexdigest(),
              "best_epoch": None, "parameters": None, "parameters_total": None,
              "mu": 0., "scale": model.scale,
              "train_cell_mae_pp": cell_metrics(data.soh[train], predict(train),
                                                data.cell[train])["cell_mae_pp"]}
    if valid is not None:
        result["valid_pred"] = predict(valid)
    return result


def summarize_predictions(rows: list[dict], data: DevData, methods=METHODS) -> tuple[list[dict], list[dict]]:
    summaries = []; no_results = []
    for name in methods:
        subset = [row for row in rows if row["method"] == name]
        seeds = (0,) if name in DETERMINISTIC else SEEDS
        expected = len(data.soh) * len(seeds)
        keys = [(row["source_row"], row["seed"]) for row in subset]
        expected_keys = {(int(source), seed) for source in data.source_row for seed in seeds}
        if len(subset) != expected or set(keys) != expected_keys or len(set(keys)) != expected:
            no_results.append({"method": name, "reason": "missing_or_duplicate_outer_predictions",
                               "actual": len(subset), "expected": expected})
            continue
        per_seed = []
        for seed in seeds:
            got = sorted((row for row in subset if row["seed"] == seed), key=lambda row: row["source_row"])
            per_seed.append(cell_metrics(np.array([row["true_soh"] for row in got]),
                                         np.array([row["pred_soh"] for row in got]),
                                         np.array([row["cell"] for row in got])))
        grouped = {}
        for row in subset:
            grouped.setdefault(row["source_row"], []).append(row)
        ordered = [grouped[int(source)] for source in data.source_row]
        pred = np.array([np.exp(np.mean(np.log([r["pred_soh"] for r in values]))) for values in ordered])
        ensemble = cell_metrics(data.soh, pred, data.cell)
        per_batch = {}
        for batch in sorted(set(data.batch)):
            cells = [r for r in ensemble["cells"] if r["cell"].startswith(str(batch) + "/")]
            per_batch[str(batch)] = {"cell_mae_pp": float(np.mean([r["mae_pp"] for r in cells])),
                                     "cells": len(cells)}
        scores = np.array([item["cell_mae_pp"] for item in per_seed])
        summaries.append({"method": name, "single_seed_cell_mae_pp": scores.tolist(),
                          "single_seed_mean_pp": float(scores.mean()),
                          "single_seed_sd_pp": float(scores.std(ddof=1)) if len(scores) > 1 else None,
                          "geometric_ensemble": ensemble, "by_batch": per_batch,
                          "worst_cells": sorted(ensemble["cells"], key=lambda r: -r["mae_pp"])[:5]})
    return summaries, no_results


def paired_bootstrap(summaries: list[dict], replicates: int = 10000) -> dict:
    lookup = {s["method"]: s for s in summaries}
    rng = np.random.default_rng(31415)
    result = {}
    for baseline in ("matched_mlp", "extra_trees_matched"):
        if baseline not in lookup:
            continue
        base = {r["cell"]: r["mae_pp"] for r in lookup[baseline]["geometric_ensemble"]["cells"]}
        for name, item in lookup.items():
            if name == baseline:
                continue
            target = {r["cell"]: r["mae_pp"] for r in item["geometric_ensemble"]["cells"]}
            cells = sorted(base.keys() & target.keys())
            delta = np.array([target[cell] - base[cell] for cell in cells])
            draws = rng.integers(0, len(cells), size=(replicates, len(cells)))
            means = delta[draws].mean(axis=1)
            result[f"{name}_minus_{baseline}"] = {"difference_pp": float(delta.mean()),
                "ci95_pp": np.quantile(means, [.025, .975]).tolist(), "cells": len(cells)}
    return result


def log_event(out: Path, event: dict) -> None:
    event = {"at_utc": datetime.now(timezone.utc).isoformat(), **event}
    with (out / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, allow_nan=False) + "\n")
    print(json.dumps(event, allow_nan=False), flush=True)


def evaluate_method_fold(data: DevData, name: str, fold: int, indices: tuple,
                         device: torch.device, max_updates: int, patience: int,
                         out: Path | None = None, configs=None, seeds=None) -> dict:
    inner_train, inner_valid, outer_train, outer_valid = indices
    configs = CONFIGS[name] if configs is None else configs
    seeds = ((0,) if name in DETERMINISTIC else SEEDS) if seeds is None else seeds
    sx, sr, inner_scaler = fit_transform(data, inner_train)
    inner_z = matched(sx, sr, data.log_ratio)
    inner_bins = (fit_numeric_bins(torch.from_numpy(inner_z[inner_train]), 16)
                  if name == "tabm_embedded" else None)
    if out is not None:
        np.savez(out / f"fold{fold}_inner_scaler.npz", **inner_scaler)
        if inner_bins is not None:
            torch.save(inner_bins, out / f"fold{fold}_inner_bins.pt")
    trials = []; failures = []
    for ci, cfg in enumerate(configs):
        for seed in seeds:
            start = time.monotonic()
            try:
                if name in ("ridge_matched", "extra_trees_matched"):
                    fit = fit_classic(data, inner_z, name, cfg, seed, inner_train, inner_valid)
                elif name == "conditional_kernel":
                    fit = fit_kernel(data, sx, sr, cfg, inner_train, inner_valid)
                else:
                    fit = fit_neural(data, sx, sr, name, cfg, seed, inner_train, inner_valid,
                                     device, max_updates, patience, bins=inner_bins)
                score = cell_metrics(data.soh[inner_valid], fit["valid_pred"], data.cell[inner_valid])["cell_mae_pp"]
                trial = {"method": name, "fold": fold, "config": ci, "seed": seed,
                         "stage": "inner", "status": "ok", "inner_cell_mae_pp": score,
                         "train_cell_mae_pp": fit["train_cell_mae_pp"],
                         "best_epoch": fit["best_epoch"], "parameters": fit["parameters"],
                         "parameters_total": fit["parameters_total"],
                         "state_sha256": fit["state_sha256"], "seconds": time.monotonic() - start}
                trials.append(trial)
                if out is not None and "history" in fit:
                    (out / f"{name}-f{fold}-c{ci}-s{seed}-inner.history.json").write_text(
                        json.dumps(fit["history"], indent=2) + "\n")
                    torch.save({"state_dict": fit["state"], "mu": fit["mu"],
                                "scale": fit["scale"], "config": cfg,
                                "best_epoch": fit["best_epoch"], "bins": inner_bins},
                               out / f"{name}-f{fold}-c{ci}-s{seed}-inner.pt")
            except Exception as error:
                trial = {"method": name, "fold": fold, "config": ci, "seed": seed,
                         "stage": "inner", "status": "failed", "error": repr(error),
                         "seconds": time.monotonic() - start}
                failures.append(trial)
            if out is not None:
                log_event(out, trial)
    choices = []
    for ci in range(len(configs)):
        group = [r for r in trials if r["config"] == ci and r["status"] == "ok"]
        if len(group) == len(seeds):
            choices.append((float(np.mean([r["inner_cell_mae_pp"] for r in group])), ci))
    if not choices:
        return {"selection": None, "trials": trials, "refits": [], "predictions": [],
                "failures": failures, "no_result": "all inner configurations incomplete"}
    _, chosen = min(choices)
    selected = [r for r in trials if r["config"] == chosen and r["status"] == "ok"]
    selection = {"method": name, "fold": fold, "selected_config": chosen,
                 "config_values": configs[chosen],
                 "inner_mean_seed_cell_mae_pp": float(np.mean([r["inner_cell_mae_pp"] for r in selected])),
                 "inner_mean_train_cell_mae_pp": float(np.mean([r["train_cell_mae_pp"] for r in selected])),
                 "epochs_by_seed": {str(r["seed"]): r["best_epoch"] for r in selected}}
    selection["inner_minus_train_gap_pp"] = (selection["inner_mean_seed_cell_mae_pp"]
                                               - selection["inner_mean_train_cell_mae_pp"])
    if out is not None:
        log_event(out, {"stage": "selection", **selection})
    sx, sr, outer_scaler = fit_transform(data, outer_train)
    outer_z = matched(sx, sr, data.log_ratio)
    outer_bins = (fit_numeric_bins(torch.from_numpy(outer_z[outer_train]), 16)
                  if name == "tabm_embedded" else None)
    if out is not None:
        np.savez(out / f"fold{fold}_outer_scaler.npz", **outer_scaler)
        if outer_bins is not None:
            torch.save(outer_bins, out / f"fold{fold}_outer_bins.pt")
    refits = []; predictions = []
    for seed in seeds:
        start = time.monotonic()
        epoch = selection["epochs_by_seed"][str(seed)]
        try:
            if name in ("ridge_matched", "extra_trees_matched"):
                fit = fit_classic(data, outer_z, name, configs[chosen], seed, outer_train, None)
                pred = np.exp(fit["mu"] + fit["scale"] * fit["model"].predict(outer_z[outer_valid]))
            elif name == "conditional_kernel":
                fit = fit_kernel(data, sx, sr, configs[chosen], outer_train, None)
                pred = np.exp(fit["model"].predict_log(sx[outer_valid], sr[outer_valid]))
            else:
                fit = fit_neural(data, sx, sr, name, configs[chosen], seed, outer_train, None,
                                 device, max_updates, patience, fixed_updates=epoch, bins=outer_bins)
                pred = predict_neural(fit["model"], name, sx[outer_valid], sr[outer_valid],
                                      data.log_ratio[outer_valid], fit["mu"], fit["scale"], device)
            if not np.isfinite(pred).all() or np.any(pred <= 0):
                raise ValueError("invalid outer prediction")
            outer_score = cell_metrics(data.soh[outer_valid], pred, data.cell[outer_valid])["cell_mae_pp"]
            refit = {"method": name, "fold": fold, "config": chosen, "seed": seed,
                     "stage": "outer_refit", "status": "ok", "fixed_epoch": epoch,
                     "train_cell_mae_pp": fit["train_cell_mae_pp"],
                     "outer_cell_mae_pp": outer_score, "parameters": fit["parameters"],
                     "parameters_total": fit["parameters_total"],
                     "state_sha256": fit["state_sha256"], "seconds": time.monotonic() - start}
            refit["outer_minus_train_gap_pp"] = outer_score - fit["train_cell_mae_pp"]
            if name == "anchored_conditional":
                with torch.no_grad():
                    parts = fit["model"].components(
                        torch.as_tensor(sx[outer_valid], device=device),
                        torch.as_tensor(sr[outer_valid], device=device))
                    component = [part.detach().cpu().numpy().reshape(-1) * fit["scale"] for part in parts]
                refit["component_mean_abs_log"] = {
                    key: float(np.mean(np.abs(value))) for key, value in
                    zip(("linear", "bilinear", "nonlinear"), component)}
                refit["component_ablation_outer_cell_mae_pp"] = {
                    "linear_only": cell_metrics(data.soh[outer_valid], np.exp(component[0]),
                                                data.cell[outer_valid])["cell_mae_pp"],
                    "linear_plus_bilinear": cell_metrics(data.soh[outer_valid],
                        np.exp(component[0] + component[1]), data.cell[outer_valid])["cell_mae_pp"],
                    "full": outer_score}
            if out is not None:
                artifact = out / f"{name}-f{fold}-s{seed}"
                if name in ("ridge_matched", "extra_trees_matched", "conditional_kernel"):
                    joblib.dump({"model": fit["model"], "mu": fit["mu"], "scale": fit["scale"],
                                 "config": configs[chosen]}, artifact.with_suffix(".joblib"))
                else:
                    torch.save({"state_dict": fit["state"], "mu": fit["mu"], "scale": fit["scale"],
                                "config": configs[chosen], "epoch": epoch, "bins": outer_bins},
                               artifact.with_suffix(".pt"))
            for idx, value in zip(outer_valid, pred):
                predictions.append({"method": name, "fold": fold, "seed": seed,
                                    "source_row": int(data.source_row[idx]), "cell": str(data.cell[idx]),
                                    "batch": str(data.batch[idx]), "true_soh": float(data.soh[idx]),
                                    "pred_soh": float(value)})
        except Exception as error:
            refit = {"method": name, "fold": fold, "config": chosen, "seed": seed,
                     "stage": "outer_refit", "status": "failed", "error": repr(error),
                     "seconds": time.monotonic() - start}
            failures.append(refit)
        refits.append(refit)
        if out is not None:
            log_event(out, refit)
    return {"selection": selection, "trials": trials, "refits": refits,
            "predictions": predictions, "failures": failures,
            "no_result": None if all(r["status"] == "ok" for r in refits) else "incomplete outer refit"}


def main(args) -> int:
    if args.max_updates != 500 or args.patience != 60:
        raise ValueError("round-3 budget is fixed by protocol")
    torch.set_num_threads(4)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"fresh output directory required: {out}")
    data, held_cells = load_development(Path(args.view))
    old = json.loads(Path(args.folds).read_text())
    if len(old["folds"]) != 3 or sorted(old["heldout_cells"]) != held_cells:
        raise ValueError("original folds/holdouts changed")
    splits = [split_indices(data, f, n) for n, f in enumerate(old["folds"])]
    dev_cells = set(map(str, data.cell))
    if any(sum(c in set(map(str, data.cell[s[3]])) for s in splits) != 1 for c in dev_cells):
        raise ValueError("outer cells must be evaluated exactly once")
    if args.device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("explicit MPS requested but unavailable; no fit started")
    device = torch.device("mps" if args.device == "auto" and torch.backends.mps.is_available()
                          else "cpu" if args.device == "auto" else args.device)
    out.mkdir(parents=True)
    manifest = {"scope": "adaptive development nested cell evaluation; no heldout scores",
                "protocol_sha256": digest(PROTOCOL), "view_sha256": digest(Path(args.view)),
                "original_folds_sha256": digest(Path(args.folds)), "runner_sha256": digest(Path(__file__)),
                "model_sha256": {p.name: digest(p) for p in (
                    ROOT / "modeling/anchored_conditional.py", ROOT / "modeling/conditional_kernel.py",
                    ROOT / "modeling/conditional_reference.py",
                    ROOT / "modeling/embedded_potential.py", ROOT / "modeling/reference_potential.py")},
                "device": str(device), "threads": 4, "seeds": SEEDS, "methods": METHODS,
                "configs": CONFIGS, "max_updates": 500, "patience": 60, "check_every": 5,
                "scheduled_fit_cap": 240, "heldout_cells_unscored": held_cells,
                "folds": [{"outer_train_cells": sorted(set(map(str, data.cell[s[2]]))),
                           "inner_train_cells": sorted(set(map(str, data.cell[s[0]]))),
                           "inner_valid_cells": sorted(set(map(str, data.cell[s[1]]))),
                           "outer_valid_cells": sorted(set(map(str, data.cell[s[3]])))} for s in splits]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    selections = []; trials = []; refits = []; predictions = []; failures = []; no_result = []
    start = time.monotonic()
    for fold, indices in enumerate(splits):
        for name in METHODS:
            try:
                result = evaluate_method_fold(data, name, fold, indices, device, 500, 60, out)
                trials.extend(result["trials"]); refits.extend(result["refits"])
                predictions.extend(result["predictions"]); failures.extend(result["failures"])
                if result["selection"] is not None:
                    selections.append(result["selection"])
                if result["no_result"]:
                    no_result.append({"method": name, "fold": fold, "reason": result["no_result"]})
            except Exception as error:
                failure = {"method": name, "fold": fold, "stage": "method",
                           "status": "failed", "error": repr(error)}
                failures.append(failure)
                no_result.append({"method": name, "fold": fold, "reason": "method exception"})
                log_event(out, failure)
            (out / "progress.json").write_text(json.dumps({"completed_fold": fold,
                "completed_method": name, "elapsed_seconds": time.monotonic()-start,
                "inner_fits": len(trials), "refits": len(refits), "failures": failures,
                "no_result": no_result}, indent=2) + "\n")
    import pandas as pd
    pd.DataFrame(trials).to_csv(out / "inner_runs.csv", index=False)
    pd.DataFrame(refits).to_csv(out / "outer_refits.csv", index=False)
    pd.DataFrame(predictions).to_csv(out / "outer_predictions.csv", index=False)
    summaries, incomplete = summarize_predictions(predictions, data)
    no_result.extend(incomplete)
    report = {"scope": "adaptive nested development only; no heldout model scores",
              "seconds": time.monotonic()-start, "device": str(device), "development_cells": len(dev_cells),
              "development_rows": len(data.soh), "heldout_cells_unscored": held_cells,
              "selections": selections, "methods": summaries,
              "paired_cell_bootstrap": paired_bootstrap(summaries),
              "failed_runs": failures, "no_result": no_result,
              "actual_inner_fits": len(trials), "actual_refits": len(refits)}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    log_event(out, {"stage": "done", "seconds": report["seconds"],
                    "successful_methods": len(summaries), "failures": len(failures)})
    return 0 if not no_result else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", default=str(VIEW))
    parser.add_argument("--folds", default=str(FOLDS))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--max-updates", type=int, default=500)
    parser.add_argument("--patience", type=int, default=60)
    raise SystemExit(main(parser.parse_args()))
