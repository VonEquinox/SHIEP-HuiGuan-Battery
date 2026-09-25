"""Isolated, local-only computation using the immutable model laboratory runtime.

This program imports no web application packages and never accepts model files
from an HTTP client. Request paths are created by the application supervisor.
"""

from __future__ import annotations
import hashlib
import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
REPO = APP.parent
LAB = REPO / "model_lab"
sys.path.insert(0, str(REPO))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.7"
os.environ["PYTORCH_MPS_LOW_WATERMARK_RATIO"] = "0.5"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"

import numpy as np

PACKAGE = LAB / "reports/round3/champion_hybrid_v2_streaming"
VIEW = LAB / "reports/round2/cv_physical/view_bundle.npz"
PROTECTED = {
    "Batch-4/R3_battery-5",
    "Batch-5/RW_battery-5",
    "Batch-6/Sim_satellite_battery-5",
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while block := f.read(1024**2):
            h.update(block)
    return h.hexdigest()


def clean(value):
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def report(stage, progress, **extra):
    print(
        json.dumps(
            {"stage": stage, "progress": progress, **clean(extra)},
            ensure_ascii=False,
            allow_nan=False,
        ),
        flush=True,
    )


def verified_forest(path=None, expected=None):
    from model_lab.modeling.frozen_et import load_champion

    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    if sha(LAB / "modeling/frozen_et.py") != manifest["code_sha256"]["et_inference"]:
        raise ValueError("Frozen ET inference code integrity mismatch")
    if path is None:
        path = PACKAGE / "et_champion.joblib"
        expected = manifest["package_file_sha256"]["et_champion.joblib"]
    if not expected or sha(path) != expected:
        raise ValueError("Model artifact SHA256 mismatch")
    return load_champion(path)


def arrays(samples):
    x = np.array([s["current"] for s in samples], dtype=np.float32)
    r = np.array([s["reference"] for s in samples], dtype=np.float32)
    q = np.array([s["log_ratio"] for s in samples], dtype=np.float32)
    from model_lab.modeling.frozen_et import validate_inputs

    return validate_inputs(x, r, q, max_rows=5000)


def import_xjtu():
    report("验证数据版本", 5)
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    if sha(VIEW) != manifest["provenance_sha256"]["view"]:
        raise ValueError("Dataset hash changed")
    with np.load(VIEW, allow_pickle=False) as d:
        idx = np.flatnonzero(~d["holdout"].astype(bool))
        cells = d["cell"][idx].astype(str)
        if len(idx) != 2058 or len(set(cells)) != 21 or set(cells) & PROTECTED:
            raise ValueError("Protected development contract changed")
        samples = []
        ordinals = {}
        for source_i, cell in zip(idx, cells):
            n = ordinals.get(cell, 0)
            ordinals[cell] = n + 1
            samples.append(
                {
                    "cell_id": cell,
                    "sample_key": f"xjtu-view-row-{int(source_i)}",
                    "ordinal": n,
                    "source_row": int(source_i),
                    "current": clean(d["x"][source_i]),
                    "reference": clean(d["reference"][source_i]),
                    "log_ratio": float(d["log_window_ratio"][source_i]),
                    "truth": float(d["soh"][source_i]),
                    "batch": str(d["protocol"][source_i]),
                }
            )
    report("已隔离保护电芯", 90, rows=len(samples), cells=len(set(cells)))
    return {
        "name": "XJTU / 已核验开发数据",
        "schema_id": "xjtu_71d_partial_cc_v1",
        "source": str(VIEW.relative_to(REPO)),
        "source_hash": sha(VIEW),
        "provenance": "experimental",
        "quality": {
            "verified": True,
            "source_rows": 2404,
            "imported_rows": 2058,
            "cells": 21,
            "excluded_protected_rows": 346,
            "physical_cycle_number_available": False,
            "observation": "3.7–4.1 V 部分恒流充电；初始参考必需",
            "labels": "诊断放电容量 / 首个可用参考诊断容量；不是 RUL",
            "scope": "开发数据；冻结模型在这些电芯上训练过，回放不是独立测试",
        },
        "samples": samples,
    }


def metrics(y, p, cells):
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    cells = np.asarray(cells)
    valid = np.isfinite(y)
    if not valid.any():
        return {"status": "no_ground_truth", "labelled_rows": 0}
    y, p, cells = y[valid], p[valid], cells[valid]
    errors = 100 * (p - y)
    per = []
    for c in sorted(set(cells)):
        e = errors[cells == c]
        per.append(
            {
                "cell_id": str(c),
                "rows": len(e),
                "mae_pp": float(np.abs(e).mean()),
                "rmse_pp": float(np.sqrt((e**2).mean())),
            }
        )
    return {
        "status": "computed",
        "labelled_rows": len(y),
        "cells": len(per),
        "cell_macro_mae_pp": float(np.mean([c["mae_pp"] for c in per])),
        "cell_macro_rmse_pp": float(np.mean([c["rmse_pp"] for c in per])),
        "pooled_mae_pp": float(np.abs(errors).mean()),
        "pooled_rmse_pp": float(np.sqrt((errors**2).mean())),
        "per_cell": per,
        "unit": "SOH percentage points",
    }


def training(request):
    from sklearn.ensemble import ExtraTreesRegressor
    from sklearn.preprocessing import StandardScaler
    import joblib

    samples = request["samples"]
    x, r, q = arrays(samples)
    y = np.asarray([s["truth"] if s["truth"] is not None else np.nan for s in samples])
    cell = np.asarray([s["cell_id"] for s in samples])
    if not np.isfinite(y).all() or (y <= 0).any():
        raise ValueError("Training requires positive finite labels for all samples")
    cells = np.array(sorted(set(cell)))
    if len(cells) < 4:
        raise ValueError("At least four distinct physical cells required")
    if set(cells) & PROTECTED:
        raise ValueError("Protected cells prohibited")
    rng = np.random.default_rng(2047)
    rng.shuffle(cells)
    valid_cells = cells[: max(1, len(cells) // 4)].tolist()
    train_cells = cells[max(1, len(cells) // 4) :].tolist()
    tr = np.flatnonzero(np.isin(cell, train_cells))
    va = np.flatnonzero(np.isin(cell, valid_cells))
    raw = np.r_[x[tr], r[tr]]
    median = np.nan_to_num(
        np.nanmedian(np.where(np.isfinite(raw), raw, np.nan), axis=0)
    )
    scaler = StandardScaler().fit(np.where(np.isfinite(raw), raw, median))
    sx = scaler.transform(np.where(np.isfinite(x), x, median)).astype(np.float32)
    sr = scaler.transform(np.where(np.isfinite(r), r, median)).astype(np.float32)
    z = np.c_[sx, sr, sx - sr, q]
    logs = np.log(y)
    mu = float(logs[tr].mean())
    scale = max(float(logs[tr].std()), 0.02)
    _, inv, cnt = np.unique(cell[tr], return_inverse=True, return_counts=True)
    weights = 1 / cnt[inv]
    weights /= weights.mean()
    trees = int(request.get("n_estimators", 100))
    leaf = int(request.get("min_samples_leaf", 3))
    if not 30 <= trees <= 300 or not 1 <= leaf <= 16:
        raise ValueError("Training budget invalid")
    models = []
    pred = []
    for seed in (0, 1, 2):
        report(
            "训练 ExtraTrees",
            10 + seed * 25,
            seed=seed,
            train_cells=len(train_cells),
            validation_cells=len(valid_cells),
        )
        m = ExtraTreesRegressor(
            n_estimators=trees, min_samples_leaf=leaf, random_state=seed, n_jobs=4
        )
        m.fit(z[tr], (logs[tr] - mu) / scale, sample_weight=weights)
        models.append(m)
        pred.append(mu + scale * m.predict(z[va]))
    artifact = {
        "schema": "xjtu_71d_partial_cc_v1",
        "models": models,
        "median": median,
        "mean": scaler.mean_,
        "scale": scaler.scale_,
        "target_mu": mu,
        "target_scale": scale,
        "train_min": np.nanmin(raw, axis=0),
        "train_max": np.nanmax(raw, axis=0),
        "seeds": [0, 1, 2],
        "n_estimators": trees,
        "min_samples_leaf": leaf,
    }
    output = Path(request["artifact_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output)
    p = np.exp(np.mean(pred, axis=0))
    score = metrics(y[va], p, cell[va])
    score["scope"] = "within_platform_cell_holdout_validation_not_final_test"
    from model_lab.modeling.frozen_et import predict_soh

    loaded = verified_forest(output, sha(output))
    reload_p = predict_soh(x[va], r[va], q[va], loaded)
    np.testing.assert_allclose(p, reload_p, rtol=1e-10, atol=1e-12)
    report("独立电芯验证及模型重载完成", 95, mae_pp=score["cell_macro_mae_pp"])
    return {
        "artifact_path": str(output),
        "artifact_hash": sha(output),
        "train_cells": train_cells,
        "validation_cells": valid_cells,
        "metrics": score,
        "parameters": {
            "seeds": [0, 1, 2],
            "n_estimators": trees,
            "min_samples_leaf": leaf,
            "split_seed": 2047,
        },
        "validation_predictions": [
            {
                "sample_id": samples[int(i)]["id"],
                "cell_id": str(cell[i]),
                "true_soh": float(y[i]),
                "pred_soh": float(v),
            }
            for i, v in zip(va, p)
        ],
    }


def inference(request):
    samples = request["samples"]
    if not 1 <= len(samples) <= 256:
        raise ValueError("Prediction batch must contain1–256 rows")
    if set(s["cell_id"] for s in samples) & PROTECTED:
        raise ValueError("Protected source cells prohibited")
    x, r, q = arrays(samples)
    model = request["model"]
    kind = model["kind"]
    report("校验模型与输入", 5, rows=len(samples))
    forest = verified_forest(model["artifact_path"], model["artifact_hash"])
    if kind == "frozen_hybrid":
        import torch
        from model_lab.modeling.frozen_hybrid_streaming import FrozenStreamingHybrid

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        requested = request.get("device", "auto")
        if requested == "mps" and device != "mps":
            raise RuntimeError("Requested MPS unavailable")
        m = FrozenStreamingHybrid(PACKAGE, device=device)
        completed = [0]

        def progress(event):
            if event.get("stage") == "view_done":
                completed[0] += 1
            report(
                "混合模型逐成员推理",
                min(90, 10 + int(80 * completed[0] / 24)),
                detail=event,
            )

        result = m.predict_components(x, r, q, chunk_rows=256, progress=progress)
    elif kind in ("frozen_et", "trained_et"):
        from model_lab.modeling.frozen_et import predict_soh

        result = {"soh": predict_soh(x, r, q, forest)}
        device = "cpu"
    else:
        raise ValueError("Unsupported registered model kind")
    v = np.stack([x, r], axis=1)
    finite = np.isfinite(v)
    outside = finite & ((v < forest["train_min"]) | (v > forest["train_max"]))
    fractions = outside.sum(axis=(1, 2)) / np.maximum(finite.sum(axis=(1, 2)), 1)
    predictions = []
    for n, s in enumerate(samples):
        p = {
            "sample_id": s["id"],
            "soh": float(result["soh"][n]),
            "outside_fraction": float(fractions[n]),
            "applicability": (
                "out_of_training_range"
                if fractions[n] > 0
                else (
                    "missing_temperature"
                    if not finite[n].all()
                    else "within_observed_range"
                )
            ),
        }
        for key in ("extra_trees_soh", "tabicl_soh"):
            if key in result:
                p[key] = float(result[key][n])
        predictions.append(p)
    score = metrics(
        [s.get("truth") for s in samples],
        result["soh"],
        [s["cell_id"] for s in samples],
    )
    train = set(model.get("train_cells", []))
    overlap = sorted(train & set(s["cell_id"] for s in samples))
    score.update(
        scope="in_sample_or_mixed" if overlap else "unseen_cells_declared",
        overlap_cells=overlap,
        caveat="非公开统一基准成绩；上传数据血缘需独立确认",
    )
    report("预测完成", 95, rows=len(samples), device=device)
    return {
        "predictions": predictions,
        "metrics": score,
        "device": device,
        "row_count": len(samples),
        "model_kind": kind,
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: ml_bridge.py request.json result.json")
    parent = int(os.environ.get("BATTERY_PARENT_PID", str(os.getppid())))
    if os.getppid() != parent:
        os._exit(70)

    def parent_watchdog():
        while True:
            time.sleep(0.5)
            if os.getppid() != parent:
                os._exit(70)

    threading.Thread(
        target=parent_watchdog, name="model-parent-watchdog", daemon=True
    ).start()
    # Independent app runtimes still share one local compute admission lock.
    # The child holds it, so an orphan cannot overlap a restarted server's job.
    lock_dir = APP / "runtime"
    lock_dir.mkdir(exist_ok=True, mode=0o700)
    compute_lock = (lock_dir / "model-compute.lock").open("a+")
    waiting = False
    while True:
        try:
            fcntl.flock(compute_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not waiting:
                report("等待本地单计算任务锁", 0)
                waiting = True
            time.sleep(0.25)
    request = json.loads(Path(sys.argv[1]).read_text())
    action = request["action"]
    if action == "import_xjtu":
        result = import_xjtu()
    elif action == "training":
        result = training(request)
    elif action in ("inference", "evaluation"):
        result = inference(request)
    else:
        raise ValueError("Unknown computation")
    out = Path(sys.argv[2])
    temporary = out.with_suffix(".tmp")
    temporary.write_text(json.dumps(clean(result), ensure_ascii=False, allow_nan=False))
    temporary.replace(out)
    report("结果已保存", 100)


if __name__ == "__main__":
    main()
