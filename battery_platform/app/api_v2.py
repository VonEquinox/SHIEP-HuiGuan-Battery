"""Shared V2 adapters. Long work is staged, then published by the existing worker."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .config import APP_ROOT, REPO_ROOT, RUNTIME
from .db import audit, execute, insert, js, now, obj, one, rows, tx
from .services import public, require
from .contracts import v2 as S

# The supported launcher starts in battery_platform/. Resolve the monorepo's
# numerical package consistently with test and CLI execution.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


router = APIRouter(prefix="/api/v2")


def authenticated(request: Request):
    # Lazy import also permits security.current_user to resolve mobile tokens here.
    from .security import current_user
    return current_user(request)


def roles(*allowed):
    def dependency(user=Depends(authenticated)):
        if user["role"] not in allowed:
            raise HTTPException(403, "当前角色没有此操作权限")
        return user
    return dependency


def response(http_request: Request, **values):
    return {**values, "request_id": getattr(http_request.state, "request_id", None) or uuid.uuid4().hex}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def timestamp(value, *, future=False):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        parsed = parsed.astimezone(timezone.utc)
        if not future and parsed > datetime.now(timezone.utc) + timedelta(seconds=2):
            raise ValueError("future timestamp")
        return parsed.isoformat()
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(422, "时间必须是含时区且符合可见性要求的 ISO8601 时间")


def replay(c, user, operation, key, body):
    if not key or len(key) > 128:
        raise HTTPException(422, "缺少合法 Idempotency-Key 或 client_submission_id")
    previous = one(c, "SELECT * FROM v2_idempotency WHERE actor_id=:u AND operation=:o AND idempotency_key=:k",
                   {"u": user["id"], "o": operation, "k": key})
    if previous:
        if previous["request_hash"] != fingerprint(body):
            raise HTTPException(409, "同一幂等键不能用于不同请求")
        return obj(previous["result"])
    return None


def remember(c, user, operation, key, body, result):
    insert(c, "v2_idempotency", {"actor_id": user["id"], "operation": operation, "idempotency_key": key,
           "request_hash": fingerprint(body), "result": js(result), "created_at": now()})
    return result


def page(c, table, *, cursor=0, limit=50, predicates=(), values=None, json_fields=()):
    values = {**(values or {}), "cursor": cursor, "limit": limit + 1}
    where = " AND ".join(["id>:cursor", *predicates])
    found = rows(c, f"SELECT * FROM {table} WHERE {where} ORDER BY id LIMIT :limit", values)
    more = len(found) > limit
    items = [public(item, json_fields) for item in found[:limit]]
    return {"items": items, "next_cursor": items[-1]["id"] if more else None}


def asset_access(c, asset_id, user, installation_id=None):
    asset = require(c, "assets", asset_id)
    if user["role"] == "technician":
        grant = one(c, """SELECT o.id FROM orders o LEFT JOIN order_assets oa ON oa.order_id=o.id
            WHERE o.assignee_id=:u AND (o.asset_id=:a OR oa.asset_id=:a)
            AND (:n IS NULL OR oa.installation_id=:n OR (oa.asset_id IS NULL AND o.asset_id=:a AND :n=:current)) LIMIT 1""",
                    {"u": user["id"], "a": asset_id, "n": installation_id, "current": asset["installation_id"]})
        if not grant:
            raise HTTPException(403, "只能访问本人获派的资产和安装身份")
    return asset


def session_access(c, identifier, user):
    session = require(c, "diagnostic_sessions", identifier)
    asset_access(c, session["asset_id"], user, session["installation_id"])
    return session


def versioned_evidence(c, table, record, cutoff):
    history_table = "inspection_observation_versions" if table == "inspection_observations" else "diagnostic_feedback_versions"
    key = "observation_id" if table == "inspection_observations" else "feedback_id"
    history = one(c, f"SELECT * FROM {history_table} WHERE {key}=:i AND created_at<=:cutoff ORDER BY version DESC LIMIT 1", {"i": record["id"], "cutoff": cutoff})
    if not history:
        return None
    visible = obj(history["content"])
    visible.update(id=record["id"], version=history["version"])
    for field in ("measurements", "observed_symptoms", "performed_actions", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items", "attachment_ids", "candidate_facts", "assertion_targets", "comparison_context"):
        if isinstance(visible.get(field), str):
            visible[field] = obj(visible[field], [])
    return visible


def save_evidence_version(c, table, identifier, actor, note):
    record = require(c, table, identifier)
    history_table = "inspection_observation_versions" if table == "inspection_observations" else "diagnostic_feedback_versions"
    key = "observation_id" if table == "inspection_observations" else "feedback_id"
    insert(c, history_table, {key: identifier, "version": record["version"], "content": js(record), "author_id": actor, "note": note, "created_at": now()})


# Test text references approved procedures; it contains no electrical control commands.
TEST_CATALOG = {
    "T_TIME_ALIGN": {"required_qualifications": ["battery", "instrumentation"], "duration_minutes": 10,
                     "result_enum": ["aligned", "misaligned", "inconclusive"], "units": [], "sop_id": "SOP_TIME_ALIGNMENT"},
    "T_CHANNEL_CHECK": {"required_qualifications": ["battery", "instrumentation"], "duration_minutes": 15,
                        "result_enum": ["consistent", "inconsistent", "inconclusive"], "units": ["V", "mV", "degC", "°C"], "sop_id": "SOP_CHANNEL_COMPARISON"},
    "T_ENVIRONMENT_REVIEW": {"required_qualifications": ["battery"], "duration_minutes": 15, "units": ["degC", "°C"], "sop_id": "SOP_ENVIRONMENT_REVIEW"},
    "T_CONNECTION_VISUAL": {"required_qualifications": ["battery"], "duration_minutes": 15, "units": [], "sop_id": "SOP_VISUAL_INSPECTION"},
    "T_CAPACITY_REVIEW": {"required_qualifications": ["battery"], "duration_minutes": 20, "units": ["Ah", "mAh", "ratio"], "sop_id": "SOP_EXISTING_CAPACITY_RECORD_REVIEW"},
    "T_SENSOR_COMPARE": {"required_qualifications": ["battery", "instrumentation"], "duration_minutes": 15, "units": ["V", "mV", "degC", "°C"], "sop_id": "SOP_CHANNEL_COMPARISON"},
    "T_COOLING_REVIEW": {"required_qualifications": ["battery"], "duration_minutes": 15, "units": ["degC", "°C"], "sop_id": "SOP_EXISTING_COOLING_RECORD_REVIEW"},
    "T_COMMUNICATION_CHECK": {"required_qualifications": ["battery"], "duration_minutes": 10, "units": ["s", "ms", "count"], "sop_id": "SOP_COMMUNICATION_RECORD_REVIEW"},
}


def test_catalog():
    catalog = {key: {"test_id": key, "requires_attachment": False, "destructive": False, **value}
               for key, value in TEST_CATALOG.items()}
    # Content packages may add only bounded, non-destructive, reviewed SOP references.
    file = REPO_ROOT / "content_v1/manifests/test_catalog.json"
    if file.is_file():
        data = json.loads(file.read_text())
        tests = data.get("tests", data.get("test_catalog", [])) if isinstance(data, dict) else data
        for item in tests:
            if item.get("test_id") and item.get("allowed_procedure_ids") and not item.get("destructive", False):
                catalog[item["test_id"]] = {**item, "sop_id": item["allowed_procedure_ids"][0],
                    "required_qualifications": ["battery", item.get("required_skill", "instrumentation")],
                    "units": item.get("measurement_units", []),
                    "provenance": "demo_synthetic", "requires_attachment": False}
    for item in catalog.values():
        item.setdefault("provenance", "platform_demo")
        item.setdefault("procedure_scope", "record_review_and_non_destructive_demo; not a certified physical SOP")
    return catalog


def validate_tests(tests, required=()):
    if len(tests) != len(set(tests)) or len(required) != len(set(required)):
        raise HTTPException(422, "授权检查集合不能重复")
    if not set(required).issubset(tests):
        raise HTTPException(422, "必做检查必须在授权集合内")
    unknown = set(tests) - set(test_catalog())
    if unknown:
        raise HTTPException(422, f"检查未登记批准规程: {','.join(sorted(unknown))}")


def ensure_context(c):
    current = one(c, "SELECT * FROM context_snapshots WHERE state='active'")
    if current:
        return current
    from .agent import ContextStore, SkillLibrary
    snapshot = ContextStore().snapshot()
    root = REPO_ROOT / "content_v1"
    library = SkillLibrary(root)
    # Only the package's visible cold-start cases enter initial retrieval; the
    # evaluator-only oracle and all other splits are intentionally unopened.
    case_path = root / "cases/cold_start.jsonl"
    if case_path.is_file():
        for line in case_path.read_text().splitlines():
            case = json.loads(line)
            asset = case.get("asset_context", {})
            visible = case.get("initial_visible", {})
            observations = visible.get("observations", [])
            insight = "Synthetic visible case observations: " + "; ".join(f"{v.get('metric')}={v.get('value')} {v.get('unit')}" for v in observations[:6])
            snapshot["memories"].append({"memory_id": "cold-" + case["case_id"], "version": 1, "state": "active",
                "scope": {"chemistry": asset.get("chemistry"), "protocol_id": asset.get("protocol_id")},
                "trigger": " ".join(str(v.get("metric", "")) for v in observations), "insight": insight,
                "supporting_case_ids": [case["case_id"]], "counterexamples": [], "source_trust": "reported",
                "origin": case.get("origin", "self_synthetic"), "source_scope": "cold_start", "available_at": visible.get("cutoff", now()),
                "helpful_count": 0, "harmful_count": 0, "last_used": None, "expires_at": None})
    for metadata in library.skill_metadata():
        snapshot["skills"][metadata["skill_id"]] = {}
    snapshot["context_snapshot_id"] = "context-0-" + fingerprint(snapshot)[:16]
    version = int(snapshot.get("version", 0))
    identifier = insert(c, "context_snapshots", {"context_version": version, "parent_id": None,
                        "content": js(snapshot), "changes": "[]", "state": "active", "validation": js({"passed": True, "kind": "cold_start"}),
                        "provenance": "self_synthetic_cold_start", "created_at": now()})
    for memory in snapshot["memories"]:
        insert(c, "memory_items", {"memory_key": memory["memory_id"], "version": 1, "state": "active", "scope": js(memory["scope"]),
            "trigger": memory["trigger"], "insight": memory["insight"], "supporting_case_ids": js(memory["supporting_case_ids"]), "counterexamples": "[]",
            "source_trust": "reported", "origin": memory["origin"], "root_scenario_id": memory["supporting_case_ids"][0],
            "context_snapshot_id": identifier, "created_at": now()})
    for metadata in library.skill_metadata():
        insert(c, "skill_versions", {"skill_id": metadata["skill_id"], "version": 1, "state": "active", "content": js(library.load_skill(metadata["skill_id"])),
            "source_trust": "ai_synthetic_unreviewed", "origin": "self_synthetic", "root_scenario_ids": js(metadata.get("example_case_ids", [])),
            "context_snapshot_id": identifier, "created_at": now()})
    return require(c, "context_snapshots", identifier)


def prediction_profile(c, asset, cutoff=None, prediction_id=None):
    predicates = "asset_id=:a AND installation_id=:n"
    values = {"a": asset["id"], "n": asset["installation_id"]}
    if cutoff:
        predicates += " AND created_at<=:cutoff"
        values["cutoff"] = cutoff
    if prediction_id:
        predicates += " AND id=:p"
        values["p"] = prediction_id
    prediction = one(c, f"SELECT * FROM predictions WHERE {predicates} ORDER BY id DESC LIMIT 1", values)
    v2_profile = one(c, """SELECT * FROM v2_prediction_profiles WHERE asset_id=:a AND installation_id=:n
                         AND (:cutoff IS NULL OR available_at<=:cutoff) ORDER BY id DESC LIMIT 1""",
                     {"a": asset["id"], "n": asset["installation_id"], "cutoff": cutoff}) if not prediction_id else None
    if v2_profile and (not prediction or v2_profile["available_at"] >= prediction["created_at"]):
        stored = obj(v2_profile["profile"])
        normalized = []
        for head, value in stored["heads"].items():
            scalar = (value.get("quantiles") or {}).get("0.5")
            if head in ("threshold_risk", "fault"):
                scalar = (value.get("params") or {}).get("probability", scalar)
            if head == "rul":
                scalar = (value.get("params") or {}).get("median", scalar)
            normalized.append({**value, "head": head, "value": scalar if value["support"] == "supported" else None,
                    "distribution": {"kind": value.get("distribution_kind"), "parameters": value.get("params") or {}, "quantiles": value.get("quantiles") or {}},
                    "target_definition_id": v2_profile["target_definition_id"], "model_version": stored["model_version"]})
        return {"asset_id": asset["id"], "installation_id": asset["installation_id"], "prediction_id": None, "v2_profile_id": v2_profile["id"],
                "heads": normalized, "support": stored["support"], "query": source_time_view(stored["query"]), "visible_cutoff": cutoff,
                "stale": (datetime.now(timezone.utc) - datetime.fromisoformat(v2_profile["available_at"])).total_seconds() > 86400,
                "production_connected": False, "provenance": v2_profile["provenance"], "available_at": v2_profile["available_at"]}
    heads = []
    if prediction:
        for item in rows(c, "SELECT * FROM prediction_outputs WHERE prediction_id=:p ORDER BY id", {"p": prediction["id"]}):
            heads.append({**public(item, ("parameters",)), "head": item["head"], "distribution": {"kind": item["distribution_kind"], "parameters": obj(item["parameters"])}})
        if not any(h["head"] == "soh" for h in heads):
            supported = prediction["applicability"] == "within_observed_range" and prediction["provenance"] != "declared_unverified"
            heads.append({"head": "soh", "value": prediction["soh"] if supported else None, "unit": "ratio",
                          "support": "supported" if supported else "unsupported", "reason": "V1 deterministic partial CC SOH; no calibrated density" if supported else prediction["applicability"],
                          "distribution": {"kind": "point", "parameters": {}}, "calibration_version": None,
                          "target_definition_id": None, "model_version": str(prediction["model_id"]), "provenance": prediction["provenance"]})
    for head, unit in (("soh", "ratio"), ("rul", "cycles"), ("threshold_risk", "probability"), ("efficiency", "ratio"), ("fault", "class")):
        if not any(h["head"] == head for h in heads):
            heads.append({"head": head, "value": None, "unit": unit, "support": "unsupported",
                          "reason": "当前安装身份没有经登记模型输出或可用标签/校准", "distribution": {"kind": "none", "parameters": {}},
                          "calibration_version": None, "target_definition_id": None})
    return {"asset_id": asset["id"], "installation_id": asset["installation_id"], "prediction_id": prediction["id"] if prediction else None,
            "heads": heads, "visible_cutoff": cutoff, "stale": bool(prediction and (datetime.now(timezone.utc) - datetime.fromisoformat(prediction["created_at"])).total_seconds() > 86400),
            "production_connected": False, "provenance": prediction["provenance"] if prediction else asset["provenance"]}


def source_time_view(query):
    result = dict(query)
    physical = (query.get("time_basis") == "verified_physical_cycle" and query.get("physical_cycles_known") is True
                and bool(query.get("source_id")))
    basis = "verified_physical_cycle" if physical else "source_record_ordinal"
    suffix = "_cycle" if physical else "_ordinal"
    source_time = {"time_basis": basis}
    if physical:
        source_time.update(unit="physical_cycle", source_id=query["source_id"], physical_cycles_known=True)
    converted = False
    for key in ("query_time", "visible_cutoff", "feature_max_time", "available_at", "reference_cutoff"):
        value = result.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            source_time[key.removesuffix("_time").removesuffix("_at") + suffix] = value
            converted = True
    if converted:
        result["source_time"] = source_time
        result["time_basis"] = basis
    return result


@router.get("/overview")
def overview(request: Request, user=Depends(authenticated)):
    with tx() as c:
        context = ensure_context(c)
        counts = {r["status"]: r["n"] for r in rows(c, "SELECT status,count(*) n FROM agent_runs GROUP BY status")}
        sources = {r["provenance"]: r["n"] for r in rows(c, "SELECT provenance,count(*) n FROM source_manifests GROUP BY provenance")}
        return response(request, open_proposals=one(c, "SELECT count(*) n FROM work_proposals WHERE status='PENDING_APPROVAL'")["n"],
                        pending_rounds=one(c, "SELECT count(*) n FROM inspection_rounds WHERE status='OPEN'")["n"], agent_runs=counts,
                        context_version=context["context_version"], source_counts=sources,
                        unsupported_heads=one(c, "SELECT count(*) n FROM prediction_outputs WHERE support='unsupported'")["n"], production_connected=False)


@router.get("/assets/{identifier}/prediction-profile")
def profile(identifier: int, request: Request, cutoff: str | None = None, user=Depends(authenticated)):
    with tx() as c:
        return response(request, **prediction_profile(c, asset_access(c, identifier, user), timestamp(cutoff) if cutoff else None))


def ensure_sources(c):
    try:
        from model_lab.modeling.v2.sources import SOURCE_DEFINITIONS, get_local_registry
        registry_path = REPO_ROOT / "model_lab/reports/v2/sources/source_registry.yaml"
        definitions = SOURCE_DEFINITIONS
        registry = {v["source_id"]: v for v in get_local_registry(registry_path)} if registry_path.is_file() else {}
    except (ImportError, ValueError, KeyError, TypeError):
        definitions = {
            "xjtu": {"landing_url": "https://zenodo.org/records/10963339", "paper_doi": "10.1038/s41467-024-48779-z"},
            "matr": {"landing_url": "https://data.matr.io/1/projects/5c48dd2bc625d700019f3204"},
            "dyad": {"landing_url": "https://figshare.com/articles/dataset/23659323"},
            "ch_batterygen": {"landing_url": "https://github.com/CH-BatteryGen/dataset-warehouse"},
        }
        registry = {}
    for source_id, definition in definitions.items():
        existing = one(c, "SELECT id FROM source_manifests WHERE source_id=:s", {"s": source_id})
        if not existing:
            manifest = {**definition, **registry.get(source_id, {})}
            insert(c, "source_manifests", {"source_id": source_id, "landing_url": manifest.get("landing_url", ""),
                   "paper_doi": manifest.get("paper_doi"), "license_status": manifest.get("license_status", "not_verified"),
                   "status": manifest.get("status", "metadata_only"), "provenance": "public_generated" if source_id == "ch_batterygen" else "experimental",
                   "manifest": js(manifest), "retrieved_at": manifest.get("retrieved_at")})


@router.get("/sources")
def sources(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
            provenance: str = "", status: str = "", user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    with tx() as c:
        ensure_sources(c)
        predicates, values = [], {}
        for key, value in (("provenance", provenance), ("status", status)):
            if value:
                predicates.append(f"{key}=:{key}")
                values[key] = value
        return response(request, **page(c, "source_manifests", cursor=cursor, limit=limit, predicates=predicates, values=values, json_fields=("manifest",)))


@router.post("/sources/{identifier}/ingest", status_code=202)
def ingest(identifier: int, data: S.SourceIngest, request: Request, user=Depends(roles("admin", "researcher"))):
    from .jobs import enqueue
    with tx() as c:
        source = require(c, "source_manifests", identifier)
        if data.mode == "registered_local":
            dataset = require(c, "datasets", data.dataset_id)
            if dataset["provenance"] in ("declared_unverified", "simulated") or source["provenance"] == "public_generated":
                raise HTTPException(409, "源与已注册数据集的来源状态不能证明兼容，须先核验导入清单")
            if source["source_id"].lower() not in dataset["source"].lower():
                raise HTTPException(409, "已注册数据集未包含此源的身份清单，不能自动重标来源")
        identifier_job = enqueue(c, "source_ingest", {"source_id": identifier, "source_version": source["version"], **data.model_dump()}, user, request.headers.get("idempotency-key", ""))
        return response(request, job_id=identifier_job, source_id=identifier, mode=data.mode)


@router.get("/models")
def models(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), user=Depends(authenticated)):
    with tx() as c:
        return response(request, **page(c, "models", cursor=cursor, limit=limit, json_fields=("metrics", "metadata", "train_cells")),
                        families=[{"id": "M0", "support": "existing_frozen_partial_cc_soh"}, {"id": "M1", "support": "offline_v2_pipeline"}, {"id": "M2", "support": "offline_v2_sequence_pipeline"}])


@router.post("/model-runs", status_code=202)
def model_run(data: S.ModelRunCreate, request: Request, user=Depends(roles("admin", "researcher"))):
    from .jobs import enqueue, choose_samples
    payload = data.model_dump()
    with tx() as c:
        if data.kind in ("training", "evaluation", "inference"):
            if data.dataset_id is None:
                raise HTTPException(422, "V1 模型作业必须指定 dataset_id")
            choose_samples(c, payload, training=data.kind == "training")
            if data.kind != "training":
                require(c, "models", data.model_id)
        elif data.kind == "v2_inference":
            if not data.asset_id:
                raise HTTPException(422, "V2 推理必须指定已绑定的 asset_id")
            asset_access(c, data.asset_id, user)
        elif data.kind != "v2_training" and not data.run_id:
            raise HTTPException(422, "V2 校准/评测/导出须指定服务端登记的 run_id")
        identifier = enqueue(c, data.kind, payload, user, request.headers.get("idempotency-key", ""))
    return response(request, job_id=identifier, id=identifier)


@router.get("/model-runs/{identifier}")
def model_run_detail(identifier: int, request: Request, user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    with tx() as c:
        job = public(require(c, "jobs", identifier), ("payload", "result"))
        if job["kind"] not in ("training", "evaluation", "inference", "v2_training", "v2_calibration", "v2_evaluation", "v2_export", "v2_inference"):
            raise HTTPException(404, "不是模型作业")
        return response(request, **job)


@router.get("/model-packages")
def model_packages(request: Request, user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    from .v2_jobs import registered_packages, feature_bundle
    packages = registered_packages()
    def visible_rows(manifest):
        return [{"row_index": index, **{key: row.get(key) for key in ("source_id", "physical_cell_id", "chemistry", "protocol_id", "query_time", "visible_cutoff", "split", "time_basis", "physical_cycles_known")}}
                for index, row in enumerate(manifest["rows"])]
    try:
        file, manifest, _ = feature_bundle()
        feature_rows = visible_rows(manifest)
    except (ValueError, FileNotFoundError):
        feature_rows = []
    items = []
    for package in packages:
        item = {"package_id": package["package_id"], "manifest": package["manifest"], "manifest_hash": package["manifest_hash"]}
        try:
            _, bundle, _ = feature_bundle(package["package_id"], package=package)
            item.update(feature_rows=visible_rows(bundle), binding_input_source=bundle["binding_input_source"])
        except (ValueError, OSError, KeyError):
            item.update(feature_rows=[], binding_input_source="unavailable", binding_error="该安全包尚无可用于运行绑定的开发观察")
        items.append(item)
    return response(request, items=items,
                    feature_rows=feature_rows, next_cursor=None, production_activated=False)


@router.post("/assets/{identifier}/v2-binding")
def bind_v2(identifier: int, data: S.V2Binding, request: Request, user=Depends(roles("admin", "researcher", "dispatcher"))):
    from .v2_jobs import registered_packages, feature_bundle
    package = next((item for item in registered_packages() if item["package_id"] == data.package_id), None)
    if not package:
        raise HTTPException(422, "只能绑定校验通过且可重新加载的服务端安全包")
    try:
        file, manifest, _ = feature_bundle(data.package_id, package=package)
    except (ValueError, OSError, KeyError):
        raise HTTPException(422, "该安全包没有可用于绑定的开发观察")
    if data.row_index >= len(manifest["rows"]):
        raise HTTPException(422, "开发源观察编号不存在")
    row = manifest["rows"][data.row_index]
    key = request.headers.get("idempotency-key", "")
    body = data.model_dump()
    with tx() as c:
        previous = replay(c, user, f"v2-binding:{identifier}", key, body)
        if previous:
            return response(request, **previous)
        asset = asset_access(c, identifier, user)
        if asset["kind"] != "cell" or not asset["active"] or asset["version"] != data.version or asset["installation_id"] != data.installation_id:
            raise HTTPException(409, "安装身份或资产版本不允许绑定")
        old = one(c, "SELECT * FROM v2_model_bindings WHERE asset_id=:a", {"a": identifier})
        if old and old["installation_id"] == data.installation_id and old["physical_cell_id"] != row["physical_cell_id"]:
            raise HTTPException(409, "同安装身份不能改成另一物理电芯，须先登记更换")
        v1 = one(c, "SELECT * FROM bindings WHERE asset_id=:a", {"a": identifier})
        if v1 and v1["cell_id"] != row["physical_cell_id"].removeprefix("xjtu:"):
            raise HTTPException(409, "V1 物理源映射不一致，不能混合安装历史")
        from .services import sha
        values = {"asset_id": identifier, "installation_id": data.installation_id, "package_id": data.package_id, "physical_cell_id": row["physical_cell_id"],
                  "row_index": data.row_index, "feature_manifest_hash": sha(file), "created_at": now(), "created_by": user["id"]}
        if old:
            execute(c, """UPDATE v2_model_bindings SET installation_id=:installation_id,package_id=:package_id,physical_cell_id=:physical_cell_id,
                row_index=:row_index,feature_manifest_hash=:feature_manifest_hash,version=version+1,created_at=:created_at,created_by=:created_by WHERE asset_id=:asset_id""", values)
        else:
            insert(c, "v2_model_bindings", values)
        execute(c, "UPDATE assets SET version=version+1 WHERE id=:i", {"i": identifier})
        audit(c, user["id"], "v2_physical_binding", "asset", identifier, {"physical_cell_id": row["physical_cell_id"], "source_cutoff": row["visible_cutoff"], "provenance": "experimental_replay_on_simulated_asset"})
        result = {"asset_id": identifier, "installation_id": data.installation_id, "version": data.version + 1, "binding": one(c, "SELECT * FROM v2_model_bindings WHERE asset_id=:a", {"a": identifier})}
        return response(request, **remember(c, user, f"v2-binding:{identifier}", key, body, result))


def mobile_current_user(request: Request):
    from .security import digest
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "移动会话格式无效")
    with tx() as c:
        user = one(c, """SELECT u.id,u.username,u.display_name,u.role,u.version,t.scope FROM mobile_tokens t JOIN users u ON u.id=t.user_id
            WHERE t.token_hash=:h AND t.expires_at>:t AND u.active=1 AND u.role='technician'""", {"h": digest(header[7:]), "t": time.time()})
    if not user:
        raise HTTPException(401, "移动会话已过期或账号无权使用")
    allowed = (
        r"/api/auth/me", r"/api/notifications(?:/\d+/read)?", r"/api/orders(?:/\d+(?:/transition|/attachments)?)?", r"/api/attachments/\d+",
        r"/api/v2/orders/\d+/(?:inspection|observations|rounds/\d+/submit|qr/verify)",
        r"/api/v2/observations/\d+/facts", r"/api/v2/agent/runs/\d+", r"/api/v2/diagnostic-sessions/\d+(?:/feedback)?", r"/api/v2/demo-mobile/logout",
    )
    if not any(re.fullmatch(pattern, request.url.path) for pattern in allowed):
        raise HTTPException(403, "移动会话仅可操作获派任务、证据和对应诊断")
    user["csrf"] = ""
    user["mobile"] = True
    return user


@router.post("/demo-mobile/login")
def mobile_login(data: S.MobileLogin, request: Request):
    from .security import digest, login
    if os.environ.get("BATTERY_DEMO_MOBILE") != "1":
        raise HTTPException(403, "测试移动登录仅在独立 demo 环境显式启用")
    cookie_token, user = login(request, data.username, data.password)
    with tx() as c:
        execute(c, "DELETE FROM sessions WHERE token_hash=:h", {"h": digest(cookie_token)})
    if user["role"] != "technician":
        raise HTTPException(403, "移动测试会话仅供已创建的技术员账号使用")
    with tx() as c:
        token = secrets.token_urlsafe(32)
        execute(c, "DELETE FROM mobile_tokens WHERE expires_at<=:t", {"t": time.time()})
        insert(c, "mobile_tokens", {"token_hash": digest(token), "user_id": user["id"], "expires_at": time.time() + 3600,
                                   "scope": "assigned_orders", "created_at": now()})
        audit(c, user["id"], "demo_mobile_login", "user", user["id"])
    user.pop("csrf", None)
    return response(request, token=token, token_type="Bearer", expires_in=3600, user=user, mode="demo_account_not_wechat_identity")


@router.post("/demo-mobile/logout")
def mobile_logout(request: Request, user=Depends(authenticated)):
    from .security import digest
    with tx() as c:
        execute(c, "DELETE FROM mobile_tokens WHERE token_hash=:h", {"h": digest(request.headers.get("authorization", "")[7:])})
    return response(request, ok=True)


def _qr_secret():
    configured = os.environ.get("BATTERY_QR_SECRET")
    if configured:
        return configured.encode()
    path = RUNTIME / "qr-signing.key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(secrets.token_bytes(32))
    except FileExistsError:
        pass
    return path.read_bytes()


def sign_qr(payload):
    encoded = base64.urlsafe_b64encode(js(payload).encode()).rstrip(b"=").decode()
    signature = hmac.new(_qr_secret(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + "." + signature


def verify_qr(token):
    try:
        encoded, signature = token.split(".")
        expected = hmac.new(_qr_secret(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["expires_at"] < time.time():
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, "二维码签名无效或已过期")


def source_snapshot(c, job):
    payload = obj(job["payload"])
    source = require(c, "source_manifests", payload["source_id"])
    return {"kind": "source_ingest", "source": source, "payload": payload}


def source_compute(request, cancelled: Callable[[], bool]):
    if cancelled():
        raise RuntimeError("任务取消")
    if request["payload"]["mode"] == "registered_local":
        return {"mode": "registered_local"}
    from model_lab.modeling.v2.sources import refresh_metadata
    result = refresh_metadata(request["source"]["source_id"], RUNTIME / "source_metadata", proxy=os.environ.get("HTTPS_PROXY", "http://127.0.0.1:7897"))
    if cancelled():
        raise RuntimeError("任务取消")
    return result


def source_complete(c, job, result, request):
    current = require(c, "source_manifests", request["source"]["id"])
    if current["version"] != request["source"]["version"]:
        raise HTTPException(409, "来源已更新，请重新导入")
    if result.get("mode") == "registered_local":
        dataset = require(c, "datasets", request["payload"]["dataset_id"])
        identifier = insert(c, "feature_views", {"source_manifest_id": current["id"], "dataset_id": dataset["id"], "schema_id": dataset["schema_id"],
               "cutoff": now(), "split": "registered_v1", "physical_ids": js([v["cell_id"] for v in rows(c, "SELECT DISTINCT cell_id FROM samples WHERE dataset_id=:d", {"d": dataset["id"]})]),
               "manifest": js({"dataset_id": dataset["id"], "source_hash": dataset["source_hash"], "provenance": dataset["provenance"], "label": "registered_existing_dataset_not_raw_reparse"}), "created_at": now()})
        return {"feature_view_id": identifier, "source_id": current["id"], "status": "registered_local", "dataset_id": dataset["id"]}
    previous_manifest = obj(current["manifest"])
    merged_manifest = {**previous_manifest, **result}
    final_status = current["status"] if current["status"] in ("parsed", "verified") and previous_manifest.get("parsed_manifest") else result.get("status", "metadata_only")
    merged_manifest["status"] = final_status
    merged_manifest["last_metadata_refresh_status"] = result.get("status", "metadata_only")
    execute(c, "UPDATE source_manifests SET manifest=:m,status=:s,license_status=:l,retrieved_at=:t,version=version+1 WHERE id=:i",
            {"m": js(merged_manifest), "s": final_status, "l": result.get("license_status", "not_verified"), "t": result.get("retrieved_at", now()), "i": current["id"]})
    return {"source_id": current["id"], "status": final_status, "raw_downloaded_by_this_job": False, "errors": result.get("errors", [])}
