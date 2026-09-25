from __future__ import annotations
import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from .config import MODEL_ROOT, SCHEMA, MAX_SAMPLES
from .db import execute, rows, one, insert, js, obj, now, audit, notify

PROTECTED = {
    "Batch-4/R3_battery-5",
    "Batch-5/RW_battery-5",
    "Batch-6/Sim_satellite_battery-5",
}
TEMP = set(range(48, 64)) | {69}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024**2):
            h.update(block)
    return h.hexdigest()


def require(c, table, identifier):
    item = one(c, f"SELECT * FROM {table} WHERE id=:i", {"i": identifier})
    if not item:
        raise HTTPException(404, "对象不存在")
    return item


def public(item, fields=()):
    result = dict(item)
    for key in fields:
        if key in result:
            result[key] = obj(result[key])
    return result


def input_hash(sample):
    return hashlib.sha256(
        js({k: sample[k] for k in ("current", "reference", "log_ratio")}).encode()
    ).hexdigest()


def validate_sample(s):
    cell = str(s.get("cell_id", ""))
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,159}", cell)
        or cell in PROTECTED
    ):
        raise ValueError("Invalid or protected physical cell ID")
    for field in ("current", "reference"):
        values = s.get(field)
        if not isinstance(values, list) or len(values) != 71:
            raise ValueError("Each observation requires71 features")
        for i, v in enumerate(values):
            if v is None and i in TEMP:
                continue
            if (
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
            ):
                raise ValueError(f"Invalid required feature {field}[{i}]")
        if values[66] <= 0 or values[70] <= 0:
            raise ValueError("Current must be positive")
        if any(v < -1e-4 for v in values[16:32]):
            raise ValueError("Charge fractions must be nonnegative")
    ratio = s.get("log_ratio")
    if (
        not isinstance(ratio, (int, float))
        or not math.isfinite(ratio)
        or abs(ratio) > 20
    ):
        raise ValueError("Invalid observed log charge ratio")
    if abs(s["current"][64] - s["reference"][64] - ratio) > 0.002:
        raise ValueError("Charge ratio disagrees with observation feature64")
    truth = s.get("truth")
    if truth is not None and (
        not isinstance(truth, (int, float))
        or not math.isfinite(truth)
        or not 0 < truth <= 2
    ):
        raise ValueError("SOH label must be positive finite ratio, not percentage")
    return s


def create_dataset(c, result, actor):
    old = one(
        c, "SELECT id FROM datasets WHERE source_hash=:h", {"h": result["source_hash"]}
    )
    if old:
        return old["id"]
    samples = result["samples"]
    if not 1 <= len(samples) <= MAX_SAMPLES:
        raise ValueError("Dataset row limit exceeded")
    keys = set()
    for s in samples:
        validate_sample(s)
        if s["sample_key"] in keys:
            raise ValueError("Duplicate sample identity")
        keys.add(s["sample_key"])
    identifier = insert(
        c,
        "datasets",
        {
            "name": result["name"],
            "schema_id": SCHEMA,
            "source": result["source"],
            "source_hash": result["source_hash"],
            "provenance": result["provenance"],
            "status": "available",
            "sample_count": len(samples),
            "cell_count": len(set(s["cell_id"] for s in samples)),
            "quality": js(result["quality"]),
            "created_at": now(),
            "created_by": actor,
        },
    )
    for s in samples:
        insert(
            c,
            "samples",
            {
                "dataset_id": identifier,
                "cell_id": s["cell_id"],
                "sample_key": s["sample_key"],
                "ordinal": s["ordinal"],
                "current_json": js(s["current"]),
                "reference_json": js(s["reference"]),
                "log_ratio": s["log_ratio"],
                "truth": s.get("truth"),
                "batch": s.get("batch", "uploaded"),
                "input_hash": input_hash(s),
            },
        )
    execute(
        c,
        """UPDATE models SET dataset_id=:d WHERE dataset_id IS NULL
        AND kind IN ('frozen_et','frozen_hybrid') AND json_extract(metadata,'$.training_view_sha256')=:h""",
        {"d": identifier, "h": result["source_hash"]},
    )
    audit(
        c,
        actor,
        "dataset_import",
        "dataset",
        identifier,
        {"sha256": result["source_hash"], "rows": len(samples)},
    )
    return identifier


def register_frozen(c, actor):
    folder = MODEL_ROOT / "reports/round3/champion_hybrid_v2_streaming"
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(409, "冻结模型包不存在，请恢复模型研究产物")
    manifest = json.loads(manifest_path.read_text())
    artifact = folder / "et_champion.joblib"
    if sha(artifact) != manifest["package_file_sha256"]["et_champion.joblib"]:
        raise HTTPException(409, "模型校验失败")
    result = []
    dataset = one(
        c,
        "SELECT id FROM datasets WHERE source_hash=:h",
        {"h": manifest["provenance_sha256"]["view"]},
    )
    for kind, name in [
        ("frozen_et", "ExtraTrees / 已冻结快速分支"),
        ("frozen_hybrid", "TabICLv2 + ExtraTrees / 等权混合"),
    ]:
        existing = one(
            c,
            "SELECT id FROM models WHERE kind=:k AND artifact_hash=:h",
            {"k": kind, "h": sha(artifact)},
        )
        if existing:
            result.append(existing["id"])
            continue
        score = (
            0.6575461807590997
            if kind == "frozen_et"
            else manifest["development_ensemble_mae_pp"]
        )
        identifier = insert(
            c,
            "models",
            {
                "name": name,
                "kind": kind,
                "schema_id": SCHEMA,
                "status": "enabled",
                "artifact_path": str(artifact),
                "artifact_hash": sha(artifact),
                "dataset_id": dataset["id"] if dataset else None,
                "train_cells": js(manifest["train_cell_ids"]),
                "metrics": js(
                    {
                        "cell_macro_mae_pp": score,
                        "scope": "historical_adaptive_development",
                        "independent_final_test": False,
                        "unit": "SOH percentage points",
                    }
                ),
                "metadata": js(
                    {
                        "manifest_sha256": sha(manifest_path),
                        "task": manifest["task"],
                        "training_view_sha256": manifest["provenance_sha256"]["view"],
                        "read_only_original": True,
                        "seeds": [0, 1, 2],
                        "model_card": "研究模型；不提供 RUL、失效机理或安全控制建议",
                        "data_requirement": "当前和初始参考的3.7–4.1V恒流充电窗口",
                        "pretrained_checkpoint_sha256": (
                            manifest["checkpoint_sha256"]
                            if kind == "frozen_hybrid"
                            else None
                        ),
                    }
                ),
                "created_at": now(),
                "created_by": actor,
            },
        )
        audit(c, actor, "model_register", "model", identifier, {"kind": kind})
        result.append(identifier)
    return result


def seed_demo(c, actor):
    existing = one(c, "SELECT id FROM assets WHERE code='DEMO-SITE'")
    if existing:
        return {"site_id": existing["id"], "created": False}

    def asset(code, name, kind, parent, loc, lat=None, lon=None):
        return insert(
            c,
            "assets",
            {
                "code": code,
                "name": name,
                "kind": kind,
                "parent_id": parent,
                "provenance": "simulated",
                "location": loc,
                "latitude": lat,
                "longitude": lon,
                "installation_id": str(uuid.uuid4()),
                "created_at": now(),
            },
        )

    site = asset(
        "DEMO-SITE",
        "慧管 · 实验回放示范站",
        "site",
        None,
        "虚拟场景 / 非真实园区",
        31.05,
        121.80,
    )
    slot = 0
    for cabinet in range(1, 4):
        cab = asset(
            f"CAB-{cabinet:02d}",
            f"{cabinet:02d}号电池柜",
            "cabinet",
            site,
            f"A区 · {cabinet:02d}号柜位",
            31.05 + cabinet * 0.0001,
            121.80,
        )
        for module in range(1, 3):
            mod = asset(
                f"CAB{cabinet}-M{module}",
                f"{module}号模组",
                "module",
                cab,
                f"{module}层",
            )
            for _ in range(4 if module == 1 else 3):
                slot += 1
                asset(
                    f"CELL-{slot:03d}",
                    f"电芯 {slot:03d}",
                    "cell",
                    mod,
                    f"{slot:03d}号槽位",
                )
    if not one(c, "SELECT id FROM policies WHERE active=1"):
        insert(
            c,
            "policies",
            {
                "name": "演示维护复核策略 v1",
                "threshold": 0.85,
                "persistence": 2,
                "cooldown_seconds": 3600,
                "stale_seconds": 86400,
                "active": 1,
                "created_by": actor,
                "created_at": now(),
            },
        )
    audit(
        c,
        actor,
        "demo_seed",
        "scenario",
        "seed-v1",
        {"assets": "simulated", "cells": 21},
    )
    return {"site_id": site, "created": True}


def demo_bind(c, dataset_id, actor):
    dataset = require(c, "datasets", dataset_id)
    cells = rows(
        c,
        "SELECT DISTINCT cell_id FROM samples WHERE dataset_id=:d ORDER BY cell_id",
        {"d": dataset_id},
    )
    assets = rows(
        c,
        "SELECT * FROM assets WHERE kind='cell' AND active=1 AND code LIKE 'CELL-%' ORDER BY code",
    )
    count = 0
    for asset, cell in zip(assets, cells):
        existing = one(
            c, "SELECT * FROM bindings WHERE asset_id=:i", {"i": asset["id"]}
        )
        if existing and (
            existing["dataset_id"] != dataset_id
            or existing["cell_id"] != cell["cell_id"]
        ):
            if one(
                c,
                "SELECT id FROM predictions WHERE asset_id=:i AND installation_id=:n",
                {"i": asset["id"], "n": asset["installation_id"]},
            ):
                raise HTTPException(
                    409,
                    "槽位已有预测历史；更换数据源前须登记新安装身份，不能混合两个电芯历史",
                )
        execute(
            c,
            """INSERT INTO bindings(asset_id,dataset_id,cell_id,scenario_id,created_at)
            VALUES(:a,:d,:c,'experimental-replay-v1',:t) ON CONFLICT(asset_id) DO UPDATE SET
            dataset_id=excluded.dataset_id,cell_id=excluded.cell_id,scenario_id=excluded.scenario_id,created_at=excluded.created_at""",
            {"a": asset["id"], "d": dataset_id, "c": cell["cell_id"], "t": now()},
        )
        count += 1
    audit(
        c,
        actor,
        "demo_bind",
        "dataset",
        dataset_id,
        {
            "bound_slots": count,
            "provenance": "experimental signals on simulated assets",
        },
    )
    return count


def location_for(c, asset):
    item = asset
    visited = set()
    while item and item["id"] not in visited:
        visited.add(item["id"])
        if item["latitude"] is not None and item["longitude"] is not None:
            return item["latitude"], item["longitude"]
        item = (
            one(c, "SELECT * FROM assets WHERE id=:i", {"i": item["parent_id"]})
            if item["parent_id"]
            else None
        )
    return None, None


def recommendations(c, order):
    asset = require(c, "assets", order["asset_id"])
    lat, lon = location_for(c, asset)
    people = rows(
        c,
        "SELECT p.*,u.display_name,u.username,u.active,u.role FROM personnel p JOIN users u ON u.id=p.user_id",
    )
    result = []
    for p in people:
        workload = one(
            c,
            "SELECT count(*) n FROM orders WHERE assignee_id=:u AND status NOT IN ('CLOSED','CANCELLED') AND id!=:i",
            {"u": p["user_id"], "i": order["id"]},
        )["n"]
        skills = obj(p["skills"], [])
        reasons = []
        if not p["active"] or p["role"] != "technician":
            reasons.append("账号不可承接维修")
        if not p["on_call"]:
            reasons.append("非值班状态")
        if order["required_skill"] not in skills:
            reasons.append("不具备所需技能")
        if workload >= p["max_workload"]:
            reasons.append("当前工作量已满")
        distance = None
        if None not in (lat, lon, p["latitude"], p["longitude"]):
            a, b, c1, d = map(math.radians, (lat, lon, p["latitude"], p["longitude"]))
            distance = (
                6371
                * 2
                * math.asin(
                    min(
                        1,
                        math.sqrt(
                            math.sin((c1 - a) / 2) ** 2
                            + math.cos(a) * math.cos(c1) * math.sin((d - b) / 2) ** 2
                        ),
                    )
                )
            )
        result.append(
            {
                "user_id": p["user_id"],
                "display_name": p["display_name"],
                "eligible": not reasons,
                "reasons": reasons or ["技能匹配", "值班中", "工作量可接单"],
                "skills": skills,
                "workload": workload,
                "max_workload": p["max_workload"],
                "distance_km": round(distance, 2) if distance is not None else None,
                "location_provenance": "simulated",
            }
        )
    return sorted(
        result,
        key=lambda p: (
            not p["eligible"],
            p["workload"],
            p["distance_km"] if p["distance_km"] is not None else float("inf"),
            p["user_id"],
        ),
    )


def open_alert(c, event_id, asset_id, key, severity, reason, actor=None):
    active = one(
        c,
        "SELECT * FROM alerts WHERE dedup_key=:k AND status IN ('OPEN','ACKNOWLEDGED')",
        {"k": key},
    )
    if active:
        execute(
            c,
            "UPDATE alerts SET occurrence_count=occurrence_count+1,updated_at=:t,version=version+1 WHERE id=:i",
            {"t": now(), "i": active["id"]},
        )
        return active["id"]
    identifier = insert(
        c,
        "alerts",
        {
            "event_id": event_id,
            "asset_id": asset_id,
            "dedup_key": key,
            "status": "OPEN",
            "severity": severity,
            "reason": reason,
            "created_at": now(),
            "updated_at": now(),
        },
    )
    for u in rows(
        c, "SELECT id FROM users WHERE active=1 AND role IN ('admin','dispatcher')"
    ):
        notify(c, u["id"], "新健康复核事件", reason, f"/operations?alert={identifier}")
    audit(c, actor, "alert_open", "alert", identifier)
    return identifier


def assess(c, prediction_id):
    p = require(c, "predictions", prediction_id)
    if not p["asset_id"]:
        return
    # Unverified user uploads cannot drive an apparent experimental diagnosis.
    if p["provenance"] not in ("experimental_replay", "simulated"):
        return
    asset = require(c, "assets", p["asset_id"])
    if not asset["active"] or asset["installation_id"] != p["installation_id"]:
        return
    policy = one(c, "SELECT * FROM policies WHERE active=1 ORDER BY id DESC LIMIT 1")
    if not policy:
        return
    # Duplicate sample/model/policy evidence does not count as a new observation.
    duplicate = one(
        c,
        """SELECT e.id FROM health_events e JOIN predictions q ON q.id=e.prediction_id
        WHERE q.sample_id=:s AND q.model_id=:m AND q.asset_id=:a AND q.installation_id=:n AND e.policy_id=:p""",
        {
            "s": p["sample_id"],
            "m": p["model_id"],
            "a": asset["id"],
            "n": p["installation_id"],
            "p": policy["id"],
        },
    )
    if duplicate:
        return
    latest = rows(
        c,
        """SELECT q.*,s.ordinal FROM predictions q JOIN samples s ON s.id=q.sample_id
        WHERE q.id IN (SELECT max(id) FROM predictions WHERE asset_id=:a AND model_id=:m AND installation_id=:n GROUP BY sample_id)
        ORDER BY s.ordinal DESC,q.id DESC LIMIT :l""",
        {
            "a": asset["id"],
            "m": p["model_id"],
            "n": p["installation_id"],
            "l": policy["persistence"],
        },
    )
    if not latest or latest[0]["id"] != p["id"]:
        return
    incompatible = p["applicability"] != "within_observed_range"
    low = len(latest) >= policy["persistence"] and all(
        v["soh"] < policy["threshold"] for v in latest
    )
    if not incompatible and not low:
        return
    reason = (
        "观测超出模型训练覆盖范围，请人工核验，不能据此诊断设备故障"
        if incompatible
        else f'连续{policy["persistence"]}个不同样本 SOH 低于演示阈值{policy["threshold"]*100:g}%，建议容量复测'
    )
    severity = "REVIEW" if incompatible else "WARNING"
    key = f'health:{asset["id"]}:{p["installation_id"]}:{policy["id"]}:{severity}'
    event = insert(
        c,
        "health_events",
        {
            "prediction_id": p["id"],
            "asset_id": asset["id"],
            "policy_id": policy["id"],
            "installation_id": p["installation_id"],
            "severity": severity,
            "reason": reason,
            "evidence": js(
                {
                    "prediction_id": p["id"],
                    "model_id": p["model_id"],
                    "soh": p["soh"],
                    "input_hash": p["input_hash"],
                    "outside_fraction": p["outside_fraction"],
                    "sample_ids": [v["sample_id"] for v in latest],
                    "not_safety_alarm": True,
                    "threshold": policy["threshold"],
                }
            ),
            "scenario_id": "experimental-replay-v1",
            "provenance": p["provenance"],
            "created_at": now(),
        },
    )
    previous = one(
        c,
        "SELECT * FROM alerts WHERE dedup_key=:k ORDER BY id DESC LIMIT 1",
        {"k": key},
    )
    if previous and previous["status"] == "RESOLVED":
        delta = (
            datetime.now(timezone.utc) - datetime.fromisoformat(previous["updated_at"])
        ).total_seconds()
        if delta < policy["cooldown_seconds"]:
            return
    open_alert(c, event, asset["id"], key, severity, reason)


def demo_event(c, asset_id, scenario, actor):
    asset = require(c, "assets", asset_id)
    if asset["provenance"] != "simulated" or not asset["active"]:
        raise HTTPException(409, "只能对有效模拟资产注入场景")
    reason = {
        "capacity-review": "演示场景：容量复核任务（非模型预测）",
        "sensor-temperature": "演示场景：温度监测异常（合成传感器事件）",
        "communication-loss": "演示场景：通讯中断（未接真实 BMS）",
    }[scenario]
    key = f'demo:{scenario}:{asset_id}:{asset["installation_id"]}'
    old = one(
        c, "SELECT id FROM alerts WHERE dedup_key=:k AND status!='RESOLVED'", {"k": key}
    )
    if old:
        return old["id"]
    event = insert(
        c,
        "health_events",
        {
            "asset_id": asset_id,
            "installation_id": asset["installation_id"],
            "severity": "REVIEW",
            "reason": reason,
            "evidence": js({"synthetic": True, "not_model_result": True}),
            "scenario_id": scenario,
            "provenance": "simulated",
            "created_at": now(),
        },
    )
    return open_alert(c, event, asset_id, key, "REVIEW", reason, actor)
