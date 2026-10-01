from __future__ import annotations
import fcntl
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from fastapi import HTTPException
from .config import RUNTIME, APP_ROOT, REPO_ROOT, ML_PYTHON, SCHEMA, MAX_JOB_ROWS
from .db import tx, rows, one, execute, insert, js, obj, now, audit, notify
from .services import require, create_dataset, assess


def enqueue(c, kind, payload, user, key):
    if not key or len(key) > 128:
        raise HTTPException(422, "缺少合法 Idempotency-Key")
    fingerprint = hashlib.sha256(
        js({"kind": kind, "payload": payload}).encode()
    ).hexdigest()
    previous = one(
        c,
        "SELECT * FROM jobs WHERE created_by=:u AND idempotency_key=:k",
        {"u": user["id"], "k": key},
    )
    if previous:
        if previous["request_hash"] != fingerprint:
            raise HTTPException(409, "同一幂等键不能用于不同请求")
        return previous["id"]
    outstanding = one(
        c, "SELECT count(*) n FROM jobs WHERE status IN ('queued','running')"
    )["n"]
    if outstanding >= 12:
        raise HTTPException(429, "计算队列已满，请稍后提交")
    identifier = insert(
        c,
        "jobs",
        {
            "kind": kind,
            "status": "queued",
            "payload": js(payload),
            "created_by": user["id"],
            "created_at": now(),
            "idempotency_key": key,
            "request_hash": fingerprint,
        },
    )
    audit(c, user["id"], "job_enqueue", "job", identifier, {"kind": kind})
    return identifier


def choose_samples(c, payload, training=False):
    dataset = require(c, "datasets", payload["dataset_id"])
    if dataset["status"] != "available" or dataset["schema_id"] != SCHEMA:
        raise HTTPException(409, "数据集不可用或格式不兼容")
    params = {"d": dataset["id"]}
    where = "dataset_id=:d"
    if payload.get("cell_id"):
        where += " AND cell_id=:cell"
        params["cell"] = payload["cell_id"]
    ids = payload.get("sample_ids", [])
    if ids:
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "样本编号重复")
        placeholders = []
        for n, i in enumerate(ids):
            params[f"i{n}"] = i
            placeholders.append(f":i{n}")
        where += " AND id IN (" + ",".join(placeholders) + ")"
    result = rows(
        c,
        f"SELECT * FROM samples WHERE {where} ORDER BY cell_id,ordinal,id"
        + ("" if training else " LIMIT 256"),
        params,
    )
    if not result or (ids and len(result) != len(ids)):
        raise HTTPException(422, "样本不属于指定数据集或不存在")
    asset_id = payload.get("asset_id")
    if asset_id:
        asset = require(c, "assets", asset_id)
        binding = one(c, "SELECT * FROM bindings WHERE asset_id=:a", {"a": asset_id})
        if (
            not asset["active"]
            or asset["kind"] != "cell"
            or not binding
            or binding["dataset_id"] != dataset["id"]
            or any(s["cell_id"] != binding["cell_id"] for s in result)
        ):
            raise HTTPException(409, "实验样本与模拟资产的显式回放绑定不匹配")
    return result


def snapshot(c, job):
    p = obj(job["payload"])
    if job["kind"] == "import":
        return {"action": "import_xjtu"}
    training = job["kind"] == "training"
    ss = choose_samples(c, p, training)
    request = {
        "action": job["kind"],
        "samples": [
            {
                "id": s["id"],
                "cell_id": s["cell_id"],
                "sample_key": s["sample_key"],
                "current": obj(s["current_json"], []),
                "reference": obj(s["reference_json"], []),
                "log_ratio": s["log_ratio"],
                "truth": s["truth"],
            }
            for s in ss
        ],
    }
    if training:
        request.update(
            n_estimators=p.get("n_estimators", 100),
            min_samples_leaf=p.get("min_samples_leaf", 3),
            artifact_path=str(RUNTIME / "models" / f'job-{job["id"]}.joblib'),
        )
    else:
        m = require(c, "models", p["model_id"])
        if m["status"] != "enabled" or m["schema_id"] != SCHEMA:
            raise ValueError("Registered model unavailable")
        request["model"] = {k: m[k] for k in ("kind", "artifact_path", "artifact_hash")}
        request["model"]["train_cells"] = obj(m["train_cells"], [])
    # Capture installation identity before computation, never bind old predictions
    # to a replacement installed while the job is running.
    bindings = {}
    for s in ss:
        candidates = rows(
            c,
            """SELECT a.id,a.installation_id,b.scenario_id FROM assets a JOIN bindings b ON b.asset_id=a.id
            WHERE a.active=1 AND b.dataset_id=:d AND b.cell_id=:cell""",
            {"d": s["dataset_id"], "cell": s["cell_id"]},
        )
        if p.get("asset_id"):
            candidates = [a for a in candidates if a["id"] == p["asset_id"]]
        # Ambiguous mappings require an explicit asset; never multiply sample metrics.
        bindings[str(s["id"])] = candidates[0] if len(candidates) == 1 else None
    request["_asset_snapshot"] = bindings
    return request


def complete(c, job, result, request):
    p = obj(job["payload"])
    actor = job["created_by"]
    if job["kind"] == "import":
        dataset_id = create_dataset(c, result, actor)
        summary = {
            "dataset_id": dataset_id,
            "rows": len(result["samples"]),
            "cells": len(set(s["cell_id"] for s in result["samples"])),
        }
    elif job["kind"] == "training":
        identifier = insert(
            c,
            "models",
            {
                "name": f'ExtraTrees / 平台实验 #{job["id"]}',
                "kind": "trained_et",
                "schema_id": SCHEMA,
                "status": "enabled",
                "artifact_path": result["artifact_path"],
                "artifact_hash": result["artifact_hash"],
                "dataset_id": p["dataset_id"],
                "train_cells": js(result["train_cells"]),
                "metrics": js(result["metrics"]),
                "metadata": js(
                    {
                        "parameters": result["parameters"],
                        "validation_cells": result["validation_cells"],
                        "origin_job": job["id"],
                        "task": "3.7–4.1V 部分恒流充电 SOH；平台内按电芯验证",
                    }
                ),
                "created_at": now(),
                "created_by": actor,
            },
        )
        summary = {**result, "model_id": identifier}
        summary.pop("artifact_path", None)
        audit(c, actor, "model_training_complete", "model", identifier)
    else:
        prediction_ids = []
        for v in result["predictions"]:
            s = require(c, "samples", v["sample_id"])
            source_dataset = require(c, "datasets", s["dataset_id"])
            binding = request.get("_asset_snapshot", {}).get(str(s["id"]))
            provenance = source_dataset["provenance"]
            if provenance == "experimental" and binding:
                provenance = "experimental_replay"
            identifier = insert(
                c,
                "predictions",
                {
                    "job_id": job["id"],
                    "model_id": p["model_id"],
                    "sample_id": s["id"],
                    "asset_id": binding["id"] if binding else None,
                    "installation_id": binding["installation_id"] if binding else None,
                    "soh": v["soh"],
                    "extra_trees_soh": v.get("extra_trees_soh"),
                    "tabicl_soh": v.get("tabicl_soh"),
                    "outside_fraction": v["outside_fraction"],
                    "applicability": v["applicability"],
                    "input_hash": s["input_hash"],
                    "provenance": provenance,
                    "created_at": now(),
                },
            )
            prediction_ids.append(identifier)
            if job["kind"] == "inference":
                assess(c, identifier)
        summary = {k: v for k, v in result.items() if k != "predictions"}
        summary["prediction_ids"] = prediction_ids
    execute(
        c,
        "UPDATE jobs SET status='succeeded',progress=100,result=:r,finished_at=:t WHERE id=:i",
        {"r": js(summary), "t": now(), "i": job["id"]},
    )
    notify(
        c,
        actor,
        "计算任务完成",
        f'任务 #{job["id"]} 已完成，结果已持久化',
        f'/models?job={job["id"]}',
    )
    audit(c, actor, "job_succeeded", "job", job["id"], {"kind": job["kind"]})


def extension_handler(kind):
    if kind == "carbon_solve":
        from .carbon import jobs as module
    elif kind in ("dispatch", "dispatch_solve"):
        from .dispatch import jobs as module
    else:
        try:
            from .v2_jobs import V2_JOB_HANDLERS
        except ImportError:
            return None
        return V2_JOB_HANDLERS.get(kind)
    return {name: getattr(module, name) for name in ("snapshot", "compute", "complete")}


class JobSupervisor:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.lock_file = None
        self.child = None

    def start(self):
        self.lock_file = (RUNTIME / "worker.lock").open("a+")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError(
                "Another app worker is active for this runtime; only one server process is supported"
            )
        with tx() as c:
            interrupted = rows(c, "SELECT * FROM jobs WHERE status='running'")
            execute(
                c,
                "UPDATE jobs SET status='interrupted',error='进程中断；没有自动重放任务',finished_at=:t WHERE status='running'",
                {"t": now()},
            )
            for job in interrupted:
                handler = extension_handler(job["kind"])
                if handler and handler.get("lifecycle"):
                    handler["lifecycle"](c, job, "interrupted", "进程中断；没有自动重放任务")
        self.thread = threading.Thread(
            target=self.loop, name="battery-job-supervisor", daemon=True
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.child and self.child.poll() is None:
            self.child.terminate()
        if self.thread:
            self.thread.join(timeout=12)
        if self.child and self.child.poll() is None:
            self.child.kill()
            self.child.wait(timeout=5)
        if self.lock_file:
            fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            self.lock_file.close()

    def loop(self):
        while not self.stop_event.is_set():
            with tx() as c:
                from .api_evolution import schedule_pending_feedback, schedule_context_gepa
                schedule_pending_feedback(c)
                schedule_context_gepa(c)
                job = one(
                    c, "SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1"
                )
                if job:
                    execute(
                        c,
                        "UPDATE jobs SET status='running',started_at=:t WHERE id=:i",
                        {"t": now(), "i": job["id"]},
                    )
            if job:
                self.run(job)
            else:
                self.stop_event.wait(0.3)

    def run(self, job):
        folder = RUNTIME / "jobs" / str(job["id"])
        folder.mkdir(exist_ok=True, mode=0o700)
        status = "failed"
        try:
            handler = extension_handler(job["kind"])
            if handler:
                self.run_extension(job, handler)
                return
            if not ML_PYTHON.is_file():
                raise RuntimeError("研究模型 Python 环境缺失；未使用模拟推理")
            with tx() as c:
                request = snapshot(c, job)
            request_path = folder / "request.json"
            result_path = folder / "result.json"
            log_path = folder / "process.log"
            request_path.write_text(js(request))
            request_path.chmod(0o600)
            with log_path.open("w") as log:
                env = os.environ.copy()
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                env["BATTERY_PARENT_PID"] = str(os.getpid())
                env["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.7"
                env["PYTORCH_MPS_LOW_WATERMARK_RATIO"] = "0.5"
                self.child = subprocess.Popen(
                    [
                        str(ML_PYTHON),
                        str(APP_ROOT / "ml_bridge.py"),
                        str(request_path),
                        str(result_path),
                    ],
                    cwd=str(REPO_ROOT),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                started = time.monotonic()
                position = 0
                while self.child.poll() is None:
                    with tx() as c:
                        current = require(c, "jobs", job["id"])
                    if (
                        current["cancel_requested"]
                        or self.stop_event.is_set()
                        or time.monotonic() - started > 900
                    ):
                        status = (
                            "cancelled"
                            if current["cancel_requested"]
                            else "interrupted"
                        )
                        self.child.terminate()
                        try:
                            self.child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self.child.kill()
                            self.child.wait(timeout=5)
                        raise RuntimeError("任务已取消/中断或超过15分钟资源上限")
                    time.sleep(0.25)
                    if log_path.stat().st_size > 4 * 1024 * 1024:
                        raise RuntimeError("计算日志超过资源上限")
                    with log_path.open() as read:
                        read.seek(position)
                        lines = read.readlines()
                        position = read.tell()
                    if lines:
                        with tx() as c:
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                insert(
                                    c,
                                    "job_logs",
                                    {
                                        "job_id": job["id"],
                                        "at": now(),
                                        "message": line[:1800],
                                    },
                                )
                                try:
                                    value = json.loads(line)
                                    if "progress" in value:
                                        execute(
                                            c,
                                            "UPDATE jobs SET progress=:p WHERE id=:i",
                                            {
                                                "p": min(99, int(value["progress"])),
                                                "i": job["id"],
                                            },
                                        )
                                except (ValueError, TypeError):
                                    pass
            if self.child.returncode != 0:
                tail = log_path.read_text()[-3500:]
                raise RuntimeError("计算进程失败；详见任务日志。" + tail)
            if (
                not result_path.is_file()
                or result_path.stat().st_size > 32 * 1024 * 1024
            ):
                raise RuntimeError("计算结果缺失或超出限制")
            result = json.loads(result_path.read_text())
            with tx() as c:
                current = require(c, "jobs", job["id"])
                if current["cancel_requested"]:
                    status = "cancelled"
                    raise RuntimeError("结果发布前任务已取消")
                complete(c, job, result, request)
        except BaseException as error:
            if self.child and self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=5)
            with tx() as c:
                execute(
                    c,
                    "UPDATE jobs SET status=:s,error=:e,finished_at=:t WHERE id=:i",
                    {"s": status, "e": str(error)[-4000:], "t": now(), "i": job["id"]},
                )
                audit(
                    c,
                    job["created_by"],
                    "job_" + status,
                    "job",
                    job["id"],
                    {"reason": str(error)[-500:]},
                )
        finally:
            self.child = None

    def run_extension(self, job, handler):
        request, result = None, None
        def cancelled():
            if self.stop_event.is_set():
                return True
            with tx() as c:
                current = require(c, "jobs", job["id"])
                return bool(current["cancel_requested"] or current["status"] != "running")

        status = "failed"
        try:
            with tx() as c:
                request = handler["snapshot"](c, job)
            if cancelled():
                raise InterruptedError("作业已取消或服务正在停止")
            result = handler["compute"](request, cancelled)
            with tx() as c:
                current = require(c, "jobs", job["id"])
                if self.stop_event.is_set() or current["cancel_requested"] or current["status"] != "running":
                    raise InterruptedError("结果发布前作业已取消或中断")
                summary = handler["complete"](c, job, result, request)
                execute(c, "UPDATE jobs SET status='succeeded',progress=100,result=:r,finished_at=:t WHERE id=:i",
                        {"r": js(summary or {}), "t": now(), "i": job["id"]})
                audit(c, job["created_by"], "job_succeeded", "job", job["id"], {"kind": job["kind"]})
        except BaseException as error:
            with tx() as c:
                current = require(c, "jobs", job["id"])
                if current["cancel_requested"]:
                    status = "cancelled"
                elif self.stop_event.is_set() or isinstance(error, InterruptedError):
                    status = "interrupted"
                execute(c, "UPDATE jobs SET status=:s,error=:e,finished_at=:t WHERE id=:i",
                        {"s": status, "e": str(error)[-4000:], "t": now(), "i": job["id"]})
                if handler.get("accounting"):
                    try:
                        with c.begin_nested():
                            # Costs survive a cancelled/failed publication;
                            # this hook must never publish a business result.
                            handler["accounting"](c, job, result, request, error)
                    except Exception as accounting_error:
                        audit(c, job["created_by"], "job_accounting_failed", "job", job["id"],
                              {"error_type": type(accounting_error).__name__})
                if handler.get("lifecycle"):
                    handler["lifecycle"](c, job, status, str(error)[-1000:])
                audit(c, job["created_by"], "job_" + status, "job", job["id"], {"reason": str(error)[-500:]})
