"""Additive worker handlers; computation never owns a SQLite transaction."""
from __future__ import annotations

import json
import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from fastapi import HTTPException

from .config import APP_ROOT, REPO_ROOT, RUNTIME
from .db import audit, execute, insert, js, now, obj, one, rows
from .services import require, sha
from .api_agent import agent_snapshot, agent_compute, agent_complete, incident_snapshot, incident_compute, incident_complete
from .api_evolution import feedback_snapshot, feedback_compute, feedback_complete, evolution_snapshot, evolution_compute, evolution_complete, gepa_snapshot, gepa_compute, gepa_complete, evolution_accounting, context_regression_snapshot, context_regression_compute, context_regression_complete
from .api_v2 import source_snapshot, source_compute, source_complete, fingerprint


def lifecycle(c, job, status, error=None):
    if job["kind"] == "agent_run":
        execute(c, "UPDATE agent_runs SET status=:s,error=:e,finished_at=:t WHERE job_id=:j", {"s": status, "e": error, "t": now(), "j": job["id"]})
    if job["kind"] in ("evolution_experiment", "context_gepa", "context_regression"):
        execute(c, "UPDATE evolution_runs SET status=:s,validation=:v,finished_at=:t WHERE job_id=:j", {"s": status, "v": js({"passed": False, "reason": error}), "t": now(), "j": job["id"]})
    if job["kind"] == "context_regression":
        snapshot = one(c, "SELECT id,validation FROM context_snapshots WHERE id=:i", {"i": obj(job["payload"])["snapshot_id"]})
        if snapshot:
            validation = obj(snapshot["validation"])
            check = validation.get("regression_check", {})
            if check.get("job_id") == job["id"]:
                validation["regression_check"] = {**check, "state": status, "reason": error, "finished_at": now()}
                execute(c, "UPDATE context_snapshots SET validation=:v WHERE id=:i", {"v": js(validation), "i": snapshot["id"]})
    if job["kind"] == "feedback_extract":
        payload = obj(job["payload"])
        table = "inspection_observations" if payload.get("observation_id") else "diagnostic_feedback"
        execute(c, f"UPDATE {table} SET extraction_status=:s WHERE id=:i", {"s": status, "i": payload.get("observation_id", payload.get("feedback_id"))})
    if job["kind"] == "feedback_verified_batch":
        for identifier in obj(job["payload"])["observation_ids"]:
            execute(c, "UPDATE inspection_observations SET extraction_status=:s WHERE id=:i", {"s": status, "i": identifier})


def verified_snapshot(c, job):
    payload = obj(job["payload"])
    requests = []
    for identifier in payload["observation_ids"]:
        observation = require(c, "inspection_observations", identifier)
        requests.append(feedback_snapshot(c, {**job, "payload": js({"observation_id": identifier, "observation_version": observation["version"]})}))
    return {"requests": requests}


def verified_compute(request, cancelled):
    return {"results": [feedback_compute(item, cancelled) for item in request["requests"]]}


def verified_complete(c, job, result, request):
    return {"items": [feedback_complete(c, job, item, source) for item, source in zip(result["results"], request["requests"])]}


def model_snapshot(c, job):
    payload = obj(job["payload"])
    run_path = None
    if job["kind"] not in ("v2_training", "v2_inference"):
        run_path = Path(payload["run_id"])
        if not run_path.is_absolute():
            run_path = REPO_ROOT / "model_lab/reports/v2/xjtu_development_20261002" / run_path
        run_path = run_path.resolve()
        allowed_root = (REPO_ROOT / "model_lab/reports/v2").resolve()
        if not (run_path.is_relative_to(allowed_root) or run_path.is_relative_to(RUNTIME / "jobs")) or not (run_path / "run.json").is_file():
            raise HTTPException(422, "run_id 必须是已登记的服务端 V2 运行目录")
    return {"kind": job["kind"], "job_id": job["id"], "payload": payload, "run_path": str(run_path) if run_path else None}


def model_compute(request, cancelled):
    payload = request["payload"]
    kind = request["kind"]
    module = {"v2_training": "train", "v2_calibration": "calibrate", "v2_evaluation": "evaluate", "v2_export": "export"}[kind]
    command = [sys.executable, str(APP_ROOT / "v2_model_worker.py"), module]
    if kind == "v2_training":
        # A unique output path prevents cancelled runs overwriting a registered run.
        import yaml
        config = yaml.safe_load((REPO_ROOT / "model_lab/configs/model_v2.yaml").read_text())
        folder = RUNTIME / "jobs" / str(request["job_id"])
        folder.mkdir(parents=True, exist_ok=True)
        config["output_dir"] = str(folder / "model_output")
        config["dataset_manifest"] = str(REPO_ROOT / config["dataset_manifest"])
        config_file = folder / "model_config.yaml"
        config_file.write_text(yaml.safe_dump(config, allow_unicode=True))
        command += ["--config", str(config_file), "--family", payload["family"], "--seed", str(payload["seed"]), "--ablation", payload["ablation"]]
    else:
        command += ["--run-id", request["run_path"]]
        if kind == "v2_evaluation":
            command += ["--split", "dev"]
        if kind == "v2_export":
            command += ["--out", str(RUNTIME / "models" / f"v2-package-job-{request['job_id']}")]
    log = RUNTIME / "jobs" / str(request["job_id"]) / "v2-process.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("w") as output:
        process = subprocess.Popen(command, cwd=str(REPO_ROOT), stdout=output, stderr=subprocess.STDOUT,
                  env={**os.environ, "BATTERY_PARENT_PID": str(os.getpid()), "PYTHONDONTWRITEBYTECODE": "1", "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.7", "PYTORCH_MPS_LOW_WATERMARK_RATIO": "0.5"})
        try:
            while process.poll() is None:
                if cancelled() or time.monotonic() - started > 900:
                    raise InterruptedError("V2 模型作业取消、中断或超过资源上限")
                if log.stat().st_size > 4 * 1024 * 1024:
                    raise RuntimeError("V2 模型日志超过资源上限")
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    if process.returncode:
        raise RuntimeError("V2 模型作业失败；" + log.read_text()[-3000:])
    return {"status": "completed_offline", "log": str(log), "run_path": request["run_path"], "model_output": str(log.parent / "model_output") if kind == "v2_training" else None,
            "package_path": str(RUNTIME / "models" / f"v2-package-job-{request['job_id']}") if kind == "v2_export" else None, "production_activated": False}


def model_complete(c, job, result, request):
    audit(c, job["created_by"], "v2_model_job_complete", "job", job["id"], {"kind": job["kind"], "production_activated": False})
    return result


def registered_packages():
    result = []
    folder = REPO_ROOT / "model_lab/reports/v2/packages"
    candidates = sorted(folder.glob("*/manifest.json")) + sorted((RUNTIME / "models").glob("v2-package-job-*/manifest.json"))
    from model_lab.modeling.v2.prediction import load_package
    for file in candidates:
        try:
            manifest = json.loads(file.read_text())
            if manifest.get("format") != "battery_model_safe_v2" or not manifest.get("reload_verified"):
                continue
            load_package(file.parent)
            result.append({"package_id": file.parent.name, "path": str(file.parent), "manifest": manifest, "manifest_hash": sha(file)})
        except (ValueError, OSError, KeyError):
            continue
    return result


def feature_bundle(package_id=None, *, package=None):
    """Resolve a package's development inputs before opening any numeric data."""
    import numpy as np
    from model_lab.modeling.v2.contracts import load_dataset, validate_training_manifest
    root = (REPO_ROOT / "model_lab/data/derived/v2").resolve()
    file = root / "xjtu_features_protocol/features.json"
    expected_schema = None
    if package_id is not None:
        package = package or next((item for item in registered_packages() if item["package_id"] == package_id), None)
        if not package or package["package_id"] != package_id:
            raise ValueError("安全模型包不可用")
        package_root = Path(package["path"])
        if sha(package_root / "manifest.json") != package["manifest_hash"]:
            raise ValueError("模型包版本已变化")
        record = json.loads((package_root / "run.json").read_text())
        expected_schema = record["feature_schema"]
        declared = Path(record.get("dataset_manifest", ""))
        # Historical runs retain original absolute provenance. Resolve only the
        # matching V2 derived suffix inside this checkout, never an outside path.
        parts = declared.parts
        suffix = next((parts[i + 3:] for i in range(len(parts) - 2)
                       if parts[i:i + 3] == ("data", "derived", "v2")), None)
        file = root.joinpath(*suffix) if suffix is not None else None
    metadata = json.loads(file.read_text()) if file is not None and file.is_file() and file.resolve().is_relative_to(root) else None
    eligible = (metadata is not None and metadata.get("data_namespace") == "experimental"
                and (expected_schema is None or metadata.get("schema_version") == expected_schema)
                and all(row.get("split") in ("train", "dev", "calibration") for row in metadata.get("rows", [])))
    if eligible:
        validate_training_manifest(metadata)
        if Path(metadata["arrays_file"]).name != metadata["arrays_file"]:
            raise ValueError("开发输入数组路径越界")
        manifest, arrays = load_dataset(file)
        manifest = {**manifest, "binding_input_source": "committed_development_bundle"}
        return file, manifest, arrays
    if package_id is None:
        raise ValueError("运行适配器仅使用无封存对象的开发特征包")
    # Multi-source studies can contain old final objects. Their exported,
    # hash-checked development examples are a separate label-free input corpus.
    queries = json.loads((package_root / "reload_domain_queries.json").read_text())
    if not queries or any(row.get("split") != "dev" for row in queries):
        raise ValueError("重载观察必须全部来自独立开发集合")
    if any(row.get("feature_schema") != expected_schema for row in queries):
        raise ValueError("重载输入特征版本与模型包不一致，必须重新生成特征并重训模型")
    if any(row.get("source_id") == "xjtu" and str(row.get("physical_cell_id", "")).endswith("-5") for row in queries):
        raise ValueError("受保护电芯不可成为运行输入")
    with np.load(package_root / "reload_domain_samples.npz", allow_pickle=False) as archive:
        if set(archive.files) != {"features", "sequences", "sequence_mask", "domain"}:
            raise ValueError("重载输入不能包含标签")
        arrays = {name: archive[name] for name in archive.files}
    if any(len(value) != len(queries) for value in arrays.values()):
        raise ValueError("重载输入和观察数量不一致")
    manifest = {"schema_version": record["feature_schema"], "data_namespace": record["data_namespace"],
                "rows": queries, "binding_input_source": "label_free_package_development_examples"}
    return package_root / "manifest.json", manifest, arrays


def inference_query(row, manifest):
    hidden = {"target_observed_at", "target_available_at", "split", "survival_censor_type",
              "survival_label_observed_at", "survival_label_available_at"}
    return {**{key: value for key, value in row.items() if key not in hidden},
            "feature_schema": manifest["schema_version"], "data_namespace": manifest["data_namespace"],
            "allowed_heads": ["soh", "rul", "threshold_risk", "efficiency", "fault"]}


def v2_inference_snapshot(c, job):
    payload = obj(job["payload"])
    asset = require(c, "assets", payload["asset_id"])
    binding = one(c, "SELECT * FROM v2_model_bindings WHERE asset_id=:a", {"a": asset["id"]})
    if not binding or binding["installation_id"] != asset["installation_id"] or not asset["active"]:
        raise HTTPException(409, "当前安装尚无有效 V2 物理源绑定")
    package = next((item for item in registered_packages() if item["package_id"] == binding["package_id"]), None)
    if not package:
        raise HTTPException(409, "登记的安全模型包不可用")
    return {"kind": "v2_inference", "binding": binding, "asset": asset, "package": package}


def v2_inference_compute(request, cancelled):
    from model_lab.modeling.v2.prediction import load_package
    if cancelled():
        raise InterruptedError("任务取消")
    file, manifest, arrays = feature_bundle(request["binding"]["package_id"], package=request["package"])
    if sha(file) != request["binding"]["feature_manifest_hash"]:
        raise ValueError("开发特征清单已变化，旧绑定不可重用")
    index = request["binding"]["row_index"]
    row = manifest["rows"][index]
    if row["physical_cell_id"] != request["binding"]["physical_cell_id"]:
        raise ValueError("物理电芯映射不一致")
    # Labels are excluded even though the evaluator's safe bundle stores them.
    selected_arrays = {key: arrays[key][index:index + 1] for key in ("features", "sequences", "sequence_mask", "domain") if key in arrays}
    query = inference_query(row, manifest)
    with (APP_ROOT / "runtime/model-compute.lock").open("a+") as lock:
        started = time.monotonic()
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if cancelled() or time.monotonic() - started > 900:
                    raise InterruptedError("推理取消或等待全局模型计算锁超时")
                time.sleep(0.2)
        try:
            profile = load_package(request["package"]["path"]).predict(query, selected_arrays)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    if cancelled():
        raise InterruptedError("任务取消")
    return {"profile": profile, "row": query}


def v2_inference_complete(c, job, result, request):
    asset = require(c, "assets", request["asset"]["id"])
    binding = one(c, "SELECT * FROM v2_model_bindings WHERE asset_id=:a", {"a": asset["id"]})
    if asset["version"] != request["asset"]["version"] or asset["installation_id"] != request["binding"]["installation_id"] or binding != request["binding"]:
        raise HTTPException(409, "推理期间安装身份或物理数据绑定已变化")
    profile = result["profile"]
    identifier = insert(c, "v2_prediction_profiles", {"job_id": job["id"], "asset_id": asset["id"], "installation_id": asset["installation_id"],
             "physical_cell_id": binding["physical_cell_id"], "source_id": result["row"]["source_id"], "model_version": profile["model_version"],
             "support": profile["support"]["status"], "profile": js(profile), "provenance": "experimental_replay_on_simulated_asset" if asset["provenance"] == "simulated" else "experimental_replay",
             "available_at": now(), "source_cutoff": result["row"]["visible_cutoff"]})
    audit(c, job["created_by"], "v2_prediction_publish", "v2_prediction_profile", identifier, {"source_id": result["row"]["source_id"], "installation_id": asset["installation_id"]})
    return {"profile_id": identifier, "asset_id": asset["id"], "model_version": profile["model_version"], "support": profile["support"], "heads": profile["heads"]}


def _handler(snapshot, compute, complete, accounting=None):
    return {"snapshot": snapshot, "compute": compute, "complete": complete, "lifecycle": lifecycle, **({"accounting": accounting} if accounting else {})}


V2_JOB_HANDLERS = {
    "agent_run": _handler(agent_snapshot, agent_compute, agent_complete),
    "incident_analysis": _handler(incident_snapshot, incident_compute, incident_complete),
    "feedback_extract": _handler(feedback_snapshot, feedback_compute, feedback_complete),
    "feedback_verified_batch": _handler(verified_snapshot, verified_compute, verified_complete),
    "evolution_experiment": _handler(evolution_snapshot, evolution_compute, evolution_complete, evolution_accounting),
    "context_gepa": _handler(gepa_snapshot, gepa_compute, gepa_complete, evolution_accounting),
    "context_regression": _handler(context_regression_snapshot, context_regression_compute, context_regression_complete, evolution_accounting),
    "source_ingest": _handler(source_snapshot, source_compute, source_complete),
    "v2_inference": _handler(v2_inference_snapshot, v2_inference_compute, v2_inference_complete),
    **{kind: _handler(model_snapshot, model_compute, model_complete) for kind in ("v2_training", "v2_calibration", "v2_evaluation", "v2_export")},
}
