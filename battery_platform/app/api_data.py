from __future__ import annotations
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Form,
    Query,
)
from fastapi.responses import Response
from . import schemas as S
from .config import MAX_UPLOAD, MAX_SAMPLES, SCHEMA
from .db import tx, rows, one, execute, insert, js, obj, now, audit
from .security import allow, current_user
from .services import require, public, create_dataset, register_frozen
from .jobs import enqueue, choose_samples

router = APIRouter(prefix="/api")


@router.get("/comparisons")
def compare_jobs(job_ids: str, user=Depends(current_user)):
    try:
        ids = list(dict.fromkeys(int(x) for x in job_ids.split(",")))
    except ValueError:
        raise HTTPException(422, "评估任务编号无效")
    if not 2 <= len(ids) <= 5:
        raise HTTPException(422, "请选择2至5个已完成评估任务")
    with tx() as c:
        reference = None
        comparisons = []
        for identifier in ids:
            job = require(c, "jobs", identifier)
            if job["kind"] != "evaluation" or job["status"] != "succeeded":
                raise HTTPException(409, "只能比较已完成的评估任务")
            predictions = rows(
                c,
                """SELECT p.*,s.cell_id,s.truth FROM predictions p JOIN samples s ON s.id=p.sample_id
                WHERE p.job_id=:i ORDER BY p.sample_id""",
                {"i": identifier},
            )
            identity = [(p["sample_id"], p["input_hash"]) for p in predictions]
            if not identity:
                raise HTTPException(409, "评估没有已保存预测")
            if reference is None:
                reference = identity
            elif reference != identity:
                raise HTTPException(
                    409,
                    "样本集合或输入快照不同，禁止比较。请在相同源电芯和样本范围上分别评估。",
                )
            grouped = {}
            squared = {}
            count = 0
            for p in predictions:
                if p["truth"] is None:
                    continue
                error = 100 * (p["soh"] - p["truth"])
                grouped.setdefault(p["cell_id"], []).append(abs(error))
                squared.setdefault(p["cell_id"], []).append(error**2)
                count += 1
            if not count:
                raise HTTPException(409, "没有真实标签，不能计算模型精度比较")
            model = require(c, "models", predictions[0]["model_id"])
            metadata = obj(job["result"]).get("metrics", {})
            comparisons.append(
                {
                    "job_id": identifier,
                    "model_id": model["id"],
                    "model_name": model["name"],
                    "model_hash": model["artifact_hash"],
                    "scope": metadata.get("scope"),
                    "overlap_cells": metadata.get("overlap_cells", []),
                    "cell_macro_mae_pp": sum(sum(v) / len(v) for v in grouped.values())
                    / len(grouped),
                    "cell_macro_rmse_pp": sum(
                        math.sqrt(sum(v) / len(v)) for v in squared.values()
                    )
                    / len(squared),
                    "rows": count,
                    "cells": len(grouped),
                }
            )
        return {
            "comparison_source_hash": hashlib.sha256(
                js(reference).encode()
            ).hexdigest(),
            "sample_count": len(reference),
            "comparisons": comparisons,
            "caveat": "相同输入集合的保存结果重算；训练重叠及来源限制仍需披露，不构成SOTA或通用能力证明。",
        }


@router.get("/schema")
def schema(user=Depends(current_user)):
    features = []
    for i in range(71):
        group = (
            "局部电量增量对数"
            if i < 16
            else (
                "局部电量占比"
                if i < 32
                else (
                    "局部时长对数"
                    if i < 48
                    else (
                        "相对温升"
                        if i < 64
                        else [
                            "总窗口电量对数",
                            "总窗口时长对数",
                            "平均电流 A",
                            "电流标准差 A",
                            "温度观测覆盖率",
                            "起点绝对温度 °C",
                            "起点电流 A",
                        ][i - 64]
                    )
                )
            )
        )
        features.append(
            {
                "index": i,
                "description": group,
                "temperature_optional": i in set(range(48, 64)) | {69},
            }
        )
    return {
        "schema_id": SCHEMA,
        "feature_count": 71,
        "features": features,
        "required_csv": ["cell_id", "sample_key", "log_ratio"]
        + [f"current_{i}" for i in range(71)]
        + [f"reference_{i}" for i in range(71)],
        "optional_csv": ["truth", "batch"],
        "label_unit": "SOH ratio (0–2); not percent",
        "input_window": "3.7–4.1 V 恒流充电；初始参考必需",
    }


@router.get("/datasets")
def datasets(user=Depends(current_user)):
    with tx() as c:
        return [
            public(d, ("quality",))
            for d in rows(c, "SELECT * FROM datasets ORDER BY id DESC")
        ]


@router.post("/datasets/import-xjtu", status_code=202)
def import_xjtu(request: Request, user=Depends(allow("admin", "researcher"))):
    with tx() as c:
        return {
            "job_id": enqueue(
                c, "import", {}, user, request.headers.get("idempotency-key")
            )
        }


@router.post("/datasets/upload", status_code=201)
async def upload_dataset(
    name: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(allow("admin", "researcher")),
):
    if not name.strip() or len(name) > 100:
        raise HTTPException(422, "数据集名称无效")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(415, "仅接受声明特征格式的 CSV，不能上传模型或可执行文件")
    contents = await file.read(MAX_UPLOAD + 1)
    if len(contents) > MAX_UPLOAD:
        raise HTTPException(413, "CSV 大小上限为8MiB")
    try:
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
        required = {"cell_id", "sample_key", "log_ratio"} | {
            f"{p}_{i}" for p in ("current", "reference") for i in range(71)
        }
        if (
            reader.fieldnames is None
            or not required.issubset(reader.fieldnames)
            or len(reader.fieldnames) != len(set(reader.fieldnames))
        ):
            raise ValueError("CSV表头缺少必要列或列名重复；请下载样本模板")
        samples = []
        count = {}
        for row in reader:
            if len(samples) >= MAX_SAMPLES:
                raise ValueError("最多导入5000行")
            cell = row["cell_id"].strip()
            n = count.get(cell, 0)
            count[cell] = n + 1
            key = row["sample_key"].strip()
            if not key or len(key) > 160 or key[0] in "=+-@":
                raise ValueError("样本ID无效")
            samples.append(
                {
                    "cell_id": cell,
                    "sample_key": key,
                    "ordinal": n,
                    "current": [
                        (
                            float(row[f"current_{i}"])
                            if row[f"current_{i}"].strip()
                            else None
                        )
                        for i in range(71)
                    ],
                    "reference": [
                        (
                            float(row[f"reference_{i}"])
                            if row[f"reference_{i}"].strip()
                            else None
                        )
                        for i in range(71)
                    ],
                    "log_ratio": float(row["log_ratio"]),
                    "truth": (
                        float(row["truth"]) if row.get("truth", "").strip() else None
                    ),
                    "batch": row.get("batch", "uploaded")[:100],
                }
            )
        result = {
            "name": name,
            "source": Path(file.filename).name,
            "source_hash": hashlib.sha256(contents).hexdigest(),
            "provenance": "declared_unverified",
            "quality": {
                "verified": False,
                "schema_checked": True,
                "note": "用户声明特征与标签；来源及跨数据集物理身份仍需核查",
            },
            "samples": samples,
        }
        with tx() as c:
            identifier = create_dataset(c, result, user["id"])
    except (ValueError, TypeError, KeyError, UnicodeError, csv.Error) as e:
        raise HTTPException(422, str(e)) from e
    return {"id": identifier}


@router.get("/datasets/{identifier}/samples")
def samples(
    identifier: int,
    cell_id: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(current_user),
):
    with tx() as c:
        require(c, "datasets", identifier)
        params = {"d": identifier, "cell": cell_id, "o": offset, "l": limit}
        where = "dataset_id=:d" + (" AND cell_id=:cell" if cell_id else "")
        return {
            "items": rows(
                c,
                f"SELECT id,dataset_id,cell_id,sample_key,ordinal,truth,batch,input_hash FROM samples WHERE {where} ORDER BY cell_id,ordinal LIMIT :l OFFSET :o",
                params,
            ),
            "total": one(c, f"SELECT count(*) n FROM samples WHERE {where}", params)[
                "n"
            ],
            "cells": rows(
                c,
                "SELECT cell_id,count(*) sample_count FROM samples WHERE dataset_id=:d GROUP BY cell_id ORDER BY cell_id",
                params,
            ),
        }


@router.get("/samples/{identifier}")
def sample(identifier: int, user=Depends(current_user)):
    with tx() as c:
        s = require(c, "samples", identifier)
        s["current"] = obj(s.pop("current_json"), [])
        s["reference"] = obj(s.pop("reference_json"), [])
        return s


def safe_csv(v):
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


@router.get("/datasets/{identifier}/export")
def export_dataset(
    identifier: int,
    limit: int = Query(5000, ge=1, le=5000),
    user=Depends(allow("admin", "researcher")),
):
    with tx() as c:
        require(c, "datasets", identifier)
        items = rows(
            c,
            "SELECT * FROM samples WHERE dataset_id=:d ORDER BY cell_id,ordinal LIMIT :l",
            {"d": identifier, "l": limit},
        )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["cell_id", "sample_key", "log_ratio", "truth", "batch"]
        + [f"current_{i}" for i in range(71)]
        + [f"reference_{i}" for i in range(71)]
    )
    for s in items:
        writer.writerow(
            [
                safe_csv(s[k])
                for k in ("cell_id", "sample_key", "log_ratio", "truth", "batch")
            ]
            + obj(s["current_json"], [])
            + obj(s["reference_json"], [])
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="dataset-{identifier}.csv"'
        },
    )


@router.delete("/datasets/{identifier}")
def delete_dataset(identifier: int, user=Depends(allow("admin", "researcher"))):
    with tx() as c:
        require(c, "datasets", identifier)
        used = one(
            c, "SELECT id FROM models WHERE dataset_id=:d", {"d": identifier}
        ) or one(
            c, "SELECT asset_id FROM bindings WHERE dataset_id=:d", {"d": identifier}
        )
        used = used or one(
            c,
            "SELECT p.id FROM predictions p JOIN samples s ON s.id=p.sample_id WHERE s.dataset_id=:d",
            {"d": identifier},
        )
        used = used or any(
            obj(j["payload"]).get("dataset_id") == identifier
            for j in rows(c, "SELECT payload FROM jobs")
        )
        if used:
            raise HTTPException(409, "该数据集已被模型、任务、预测或资产引用，禁止删除")
        execute(c, "DELETE FROM samples WHERE dataset_id=:d", {"d": identifier})
        execute(c, "DELETE FROM datasets WHERE id=:d", {"d": identifier})
        audit(c, user["id"], "dataset_delete", "dataset", identifier)
    return {"ok": True}


@router.get("/models")
def models(user=Depends(current_user)):
    with tx() as c:
        result = rows(c, "SELECT * FROM models ORDER BY id")
        for m in result:
            m["artifact_present"] = Path(m["artifact_path"]).is_file()
            m.pop("artifact_path")
            for k in ("train_cells", "metrics", "metadata"):
                m[k] = obj(m[k])
        return result


@router.post("/models/register-frozen")
def register(request: Request, user=Depends(allow("admin", "researcher"))):
    with tx() as c:
        return {"model_ids": register_frozen(c, user["id"])}


@router.post("/models/{identifier}/toggle")
def toggle(identifier: int, user=Depends(allow("admin", "researcher"))):
    with tx() as c:
        m = require(c, "models", identifier)
        status = "retired" if m["status"] == "enabled" else "enabled"
        execute(
            c, "UPDATE models SET status=:s WHERE id=:i", {"s": status, "i": identifier}
        )
        audit(c, user["id"], "model_" + status, "model", identifier)
    return {"status": status}


@router.get("/jobs")
def jobs(user=Depends(current_user)):
    with tx() as c:
        result = rows(
            c,
            "SELECT id,kind,status,progress,created_by,created_at,started_at,finished_at,error,payload FROM jobs ORDER BY id DESC LIMIT 100",
        )
        return [public(j, ("payload",)) for j in result]


@router.post("/jobs", status_code=202)
def new_job(
    data: S.JobCreate, request: Request, user=Depends(allow("admin", "researcher"))
):
    with tx() as c:
        payload = data.model_dump()
        selected = choose_samples(c, payload, data.kind == "training")
        if data.kind != "training":
            if data.model_id is None:
                raise HTTPException(422, "请选择模型")
            model = require(c, "models", data.model_id)
            if model["status"] != "enabled" or model["schema_id"] != SCHEMA:
                raise HTTPException(409, "模型不可用或不兼容")
        elif len(set(s["cell_id"] for s in selected)) < 4:
            raise HTTPException(422, "按电芯训练至少需要4个独立电芯")
        identifier = enqueue(
            c, data.kind, payload, user, request.headers.get("idempotency-key")
        )
        return {"job_id": identifier}


@router.get("/jobs/{identifier}")
def job(identifier: int, user=Depends(current_user)):
    with tx() as c:
        j = require(c, "jobs", identifier)
        j = public(j, ("payload", "result"))
        j["logs"] = rows(
            c,
            "SELECT * FROM job_logs WHERE job_id=:i ORDER BY id DESC LIMIT 100",
            {"i": identifier},
        )
        return j


@router.post("/jobs/{identifier}/cancel")
def cancel(identifier: int, user=Depends(allow("admin", "researcher"))):
    with tx() as c:
        j = require(c, "jobs", identifier)
        if j["created_by"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "只能取消自己的任务")
        if j["status"] not in ("queued", "running"):
            raise HTTPException(409, "任务已经结束")
        if j["status"] == "queued":
            execute(
                c,
                "UPDATE jobs SET status='cancelled',cancel_requested=1,finished_at=:t WHERE id=:i",
                {"t": now(), "i": identifier},
            )
        else:
            execute(
                c, "UPDATE jobs SET cancel_requested=1 WHERE id=:i", {"i": identifier}
            )
        audit(c, user["id"], "job_cancel_request", "job", identifier)
    return {"ok": True}


@router.get("/predictions")
def predictions(
    asset_id: int | None = None,
    job_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
    user=Depends(current_user),
):
    with tx() as c:
        where = []
        params = {"l": limit}
        if asset_id:
            where.append("p.asset_id=:a")
            params["a"] = asset_id
        if job_id:
            where.append("p.job_id=:j")
            params["j"] = job_id
        return rows(
            c,
            """SELECT p.*,s.cell_id,s.sample_key,s.ordinal,s.truth,d.provenance dataset_provenance,m.name model_name,a.name asset_name
            FROM predictions p JOIN samples s ON s.id=p.sample_id JOIN datasets d ON d.id=s.dataset_id
            JOIN models m ON m.id=p.model_id LEFT JOIN assets a ON a.id=p.asset_id"""
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY p.id DESC LIMIT :l",
            params,
        )


@router.get("/predictions/{identifier}")
def prediction(identifier: int, user=Depends(current_user)):
    with tx() as c:
        p = require(c, "predictions", identifier)
        s = require(c, "samples", p["sample_id"])
        m = require(c, "models", p["model_id"])
        current = obj(s.pop("current_json"), [])
        reference = obj(s.pop("reference_json"), [])
        p["input_snapshot"] = {**s, "current": current, "reference": reference}
        p["model"] = {k: m[k] for k in ("id", "name", "kind", "artifact_hash")}
        p["feedback"] = rows(
            c,
            "SELECT f.*,u.display_name actor FROM feedback f JOIN users u ON u.id=f.created_by WHERE prediction_id=:i ORDER BY f.id",
            {"i": identifier},
        )
        return p
