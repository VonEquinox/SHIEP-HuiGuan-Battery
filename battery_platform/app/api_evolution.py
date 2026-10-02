"""Automatic, source-tagged context changes with short transactional activation."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .config import APP_ROOT, REPO_ROOT
from .contracts import v2 as S
from .db import audit, execute, insert, js, now, obj, one, rows, tx
from .services import public, require
from .api_v2 import authenticated, roles, response, fingerprint, replay, remember, page, ensure_context, save_evidence_version

router = APIRouter(prefix="/api/v2")
EVOLUTION_JSON = ("source_feedback_ids", "case_ids", "changes", "validation", "metrics")
SNAPSHOT_JSON = ("content", "changes", "validation")


def public_evolution_run(c, row):
    """Expose the same strict metric vocabulary to list, detail, and charts."""
    from .agent.experiment_metrics import public_metrics
    run = dict(row)
    for key in EVOLUTION_JSON:
        if isinstance(run.get(key), str):
            run[key] = obj(run[key])
    measured = public_metrics(run["metrics"])
    evaluation = one(c, "SELECT * FROM evaluation_runs WHERE evolution_run_id=:i ORDER BY id DESC LIMIT 1", {"i": run["id"]})
    protocol = obj(evaluation["protocol"]) if evaluation else {}
    validation = run["validation"]
    # Unknown/legacy protocols remain one-run groups rather than joining
    # potentially incomparable operational, selection, or replay results.
    run["experiment_metrics"] = measured
    run["experiment_protocol"] = {
        "protocol_id": validation.get("experiment_protocol_id", "unrecorded-run-" + str(run["id"])),
        "protocol_version": protocol.get("protocol_version", "unrecorded"),
        "split": run["split"], "method": run["method"], "provenance": run["provenance"],
        "metric_version": measured["measurement_version"],
        "cohort_sha256": fingerprint(sorted(run["case_ids"])),
        "frozen_config_sha256": validation.get("frozen_config_sha256"),
        "execution_modes": protocol.get("execution_modes", ["unrecorded"]),
        "llm_models": protocol.get("llm_models", []),
    }
    return run


def sync_skills(c):
    from .agent import SkillLibrary
    root = REPO_ROOT / "content_v1"
    if not (root / "skills").is_dir():
        return
    library = SkillLibrary(root)
    context = ensure_context(c)
    for metadata in library.skill_metadata():
        if one(c, "SELECT id FROM skill_versions WHERE skill_id=:s LIMIT 1", {"s": metadata["skill_id"]}):
            continue
        skill = library.load_skill(metadata["skill_id"])
        insert(c, "skill_versions", {"skill_id": metadata["skill_id"], "version": 1, "state": "active", "content": js(skill),
               "source_trust": "synthetic_expert_rules", "origin": "self_synthetic", "root_scenario_ids": js(metadata.get("cold_start_root_ids", [])),
               "context_snapshot_id": context["id"], "created_at": now()})


@router.get("/skills")
def skills(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), state: str = "", skill_id: str = "",
           user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    predicates, values = [], {}
    for field, value in (("state", state), ("skill_id", skill_id)):
        if value:
            predicates.append(f"{field}=:{field}")
            values[field] = value
    with tx() as c:
        sync_skills(c)
        return response(request, **page(c, "skill_versions", cursor=cursor, limit=limit, predicates=predicates, values=values, json_fields=("content", "root_scenario_ids")), approval_required=False)


@router.get("/memories")
def memories(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), state: str = "", origin: str = "",
             user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    predicates, values = [], {}
    for field, value in (("state", state), ("origin", origin)):
        if value:
            predicates.append(f"{field}=:{field}")
            values[field] = value
    with tx() as c:
        context = ensure_context(c)
        return response(request, **page(c, "memory_items", cursor=cursor, limit=limit, predicates=predicates, values=values,
                        json_fields=("scope", "supporting_case_ids", "counterexamples")), current_version=context["context_version"], approval_required=False)


@router.get("/context-snapshots")
def contexts(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    with tx() as c:
        current = ensure_context(c)
        return response(request, **page(c, "context_snapshots", cursor=cursor, limit=limit, json_fields=SNAPSHOT_JSON), current_version=current["context_version"])


@router.get("/context-snapshots/{identifier}")
def context_detail(identifier: int, request: Request, user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    with tx() as c:
        return response(request, **public(require(c, "context_snapshots", identifier), SNAPSHOT_JSON))


@router.post("/context-snapshots/rollback")
def rollback(data: S.ContextRollback, request: Request, user=Depends(roles("admin", "researcher"))):
    key = request.headers.get("idempotency-key", "")
    body = data.model_dump()
    with tx() as c:
        old = replay(c, user, "context_rollback", key, body)
        if old:
            return response(request, **old)
        current = ensure_context(c)
        target = require(c, "context_snapshots", data.snapshot_id)
        if current["context_version"] != data.base_version or target["id"] == current["id"] or target["state"] == "quarantined":
            raise HTTPException(409, "活动上下文已经变化或回滚对象无效")
        snapshot = obj(target["content"])
        snapshot["version"] = one(c, "SELECT coalesce(max(context_version),0)+1 n FROM context_snapshots")["n"]
        snapshot["context_version"] = f"context_v{snapshot['version']}"
        snapshot["context_snapshot_id"] = f"rollback-{snapshot['version']}-{fingerprint(snapshot)[:12]}"
        snapshot["parent_snapshot_id"] = obj(current["content"])["context_snapshot_id"]
        change = {"operation": "ROLLBACK", "from_snapshot_id": current["id"], "restore_snapshot_id": target["id"], "reason": data.reason}
        identifier = publish_snapshot(c, current, snapshot, [change], {"passed": True, "trigger": "manual_operational_rollback"}, user["id"], automatic_regression=False)
        audit(c, user["id"], "context_rollback", "context_snapshot", identifier, change)
        return response(request, **remember(c, user, "context_rollback", key, body, {"snapshot_id": identifier, "context_version": snapshot["version"], "state": "active"}))


@router.get("/evolution/runs")
def evolution_runs(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), status: str = "", split: str = "",
                   user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    predicates, values = [], {}
    for field, value in (("status", status), ("split", split)):
        if value:
            predicates.append(f"{field}=:{field}")
            values[field] = value
    with tx() as c:
        from .agent.experiment_metrics import metrics_contract
        result = page(c, "evolution_runs", cursor=cursor, limit=limit, predicates=predicates, values=values, json_fields=EVOLUTION_JSON)
        result["items"] = [public_evolution_run(c, run) for run in result["items"]]
        return response(request, **result, metrics_contract=metrics_contract())


@router.get("/evolution/runs/{identifier}")
def evolution_run_detail(identifier: int, request: Request, user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    with tx() as c:
        from .agent.experiment_metrics import metrics_contract
        run = public_evolution_run(c, require(c, "evolution_runs", identifier))
        if run["job_id"]:
            run["job"] = public(require(c, "jobs", run["job_id"]), ("result", "payload"))
        run["evaluations"] = [public(v, ("metrics", "protocol", "budget")) for v in rows(c, "SELECT * FROM evaluation_runs WHERE evolution_run_id=:i ORDER BY id", {"i": identifier})]
        return response(request, **run, metrics_contract=metrics_contract())


@router.post("/evolution/experiments", status_code=202)
def experiment(data: S.EvolutionExperiment, request: Request, user=Depends(roles("admin", "researcher"))):
    from .jobs import enqueue
    body = data.model_dump()
    key = request.headers.get("idempotency-key", "")
    if len(set(data.case_ids)) != len(data.case_ids) or len(data.case_ids) > data.max_rollouts:
        raise HTTPException(422, "根事件不能重复，且事件数不能超过 rollout 预算")
    if data.activate and data.split != "evolution":
        raise HTTPException(403, "dev 和封存标签不能激活到运行上下文")
    if data.split == "sealed_test" and data.method in ("ace", "reflexion", "gepa"):
        raise HTTPException(403, "封存评测只允许冻结版本只读重放，不产生候选或反思")
    with tx() as c:
        previous = replay(c, user, "evolution_experiment", key, body)
        if previous:
            return response(request, **previous)
        current = ensure_context(c)
        if current["context_version"] != data.base_version:
            raise HTTPException(409, "上下文版本已变化，请刷新实验配置")
        job_id = enqueue(c, "evolution_experiment", body, user, "experiment-" + fingerprint(key))
        identifier = insert(c, "evolution_runs", {"job_id": job_id, "method": data.method, "status": "queued", "base_context_version": data.base_version,
                  "source_feedback_ids": "[]", "case_ids": js(data.case_ids), "split": data.split, "changes": "[]", "validation": "{}", "metrics": "{}",
                  "provenance": "self_synthetic_replay", "created_by": user["id"], "created_at": now()})
        audit(c, user["id"], "evolution_experiment_enqueue", "evolution_run", identifier, {"split": data.split, "max_rollouts": data.max_rollouts, "activate": data.activate})
        result = {"id": identifier, "evolution_run_id": identifier, "job_id": job_id}
        return response(request, **remember(c, user, "evolution_experiment", key, body, result))


def publish_snapshot(c, base, snapshot, changes, validation, actor, *, automatic_regression=True):
    current = ensure_context(c)
    if current["id"] != base["id"]:
        raise HTTPException(409, "上下文 CAS 冲突，旧候选不会覆盖新经验")
    # ContextStore versions begin at its base, while operational rollback can make
    # the global version larger; publication preserves a monotonically unique ID.
    version = one(c, "SELECT coalesce(max(context_version),-1)+1 n FROM context_snapshots")["n"]
    snapshot = copy.deepcopy(snapshot)
    snapshot["version"] = version
    snapshot["context_version"] = f"context_v{version}"
    execute(c, "UPDATE context_snapshots SET state='superseded' WHERE id=:i", {"i": base["id"]})
    identifier = insert(c, "context_snapshots", {"context_version": version, "parent_id": base["id"], "content": js(snapshot), "changes": js(changes),
                "state": "active", "validation": js(validation), "provenance": "source_tagged_context_only", "created_at": now(), "created_by": actor})
    old = obj(base["content"])
    old_memories = {m["memory_id"]: m for m in old.get("memories", [])}
    for memory in snapshot.get("memories", []):
        previous = old_memories.get(memory["memory_id"])
        if memory == previous:
            continue
        stored = one(c, "SELECT max(version) n FROM memory_items WHERE memory_key=:k", {"k": memory["memory_id"]})["n"]
        used = one(c, "SELECT last_used FROM memory_items WHERE memory_key=:k AND last_used IS NOT NULL ORDER BY last_used DESC LIMIT 1", {"k": memory["memory_id"]})
        # Runtime retrieval is audited metadata. A frozen Context revision must
        # not erase the last real use recorded in its database mirror.
        memory_last_used = memory.get("last_used")
        if used:
            from .agent.contracts import parse_time
            memory_last_used = max(filter(None, (memory_last_used, used["last_used"])), key=parse_time)
        memory_version = (stored or 0) + 1
        execute(c, "UPDATE memory_items SET state='superseded' WHERE memory_key=:k AND state IN ('active','conflicted')", {"k": memory["memory_id"]})
        insert(c, "memory_items", {"memory_key": memory["memory_id"], "version": memory_version, "state": memory.get("state", "active"),
               "scope": js(memory.get("scope", {})), "trigger": memory.get("trigger", ""), "insight": memory["insight"], "supporting_case_ids": js(memory.get("supporting_case_ids", [])),
               "counterexamples": js(memory.get("counterexamples", []) + memory.get("conflicts", [])), "source_trust": memory.get("source_trust", "reported"), "origin": memory.get("origin", "measured_declared"),
               "helpful_count": memory.get("helpful_count", 0), "harmful_count": memory.get("harmful_count", 0), "last_used": memory_last_used, "expires_at": memory.get("expires_at"),
               "context_snapshot_id": identifier, "created_at": now()})
    # Rollback also deactivates entries absent from the restored snapshot.
    for memory_id in set(old_memories) - {m["memory_id"] for m in snapshot.get("memories", [])}:
        execute(c, "UPDATE memory_items SET state='deprecated' WHERE memory_key=:k AND state IN ('active','conflicted')", {"k": memory_id})
    for skill_id, fields in snapshot.get("skills", {}).items():
        if fields == old.get("skills", {}).get(skill_id):
            continue
        previous = one(c, "SELECT * FROM skill_versions WHERE skill_id=:s ORDER BY version DESC LIMIT 1", {"s": skill_id})
        execute(c, "UPDATE skill_versions SET state='superseded' WHERE skill_id=:s AND state='active'", {"s": skill_id})
        content = obj(previous["content"]) if previous else {"manifest": {"skill_id": skill_id}}
        content["context_overrides"] = fields
        insert(c, "skill_versions", {"skill_id": skill_id, "version": previous["version"] + 1 if previous else 1, "state": "active", "content": js(content),
               "source_trust": "automatic_dev_regression", "origin": "self_synthetic", "root_scenario_ids": "[]", "context_snapshot_id": identifier, "created_at": now()})
    if automatic_regression:
        schedule_context_regression(c, require(c, "context_snapshots", identifier), actor)
    return identifier


def feedback_snapshot(c, job):
    payload = obj(job["payload"])
    table = "inspection_observations" if payload.get("observation_id") else "diagnostic_feedback"
    identifier = payload.get("observation_id", payload.get("feedback_id"))
    record = require(c, table, identifier)
    expected = payload.get("observation_version", payload.get("feedback_version"))
    if record["version"] != expected:
        raise HTTPException(409, "反馈版本已更新，抽取旧版本取消发布")
    fields = ("measurements", "performed_actions", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items", "assertion_targets", "candidate_facts")
    feedback = public(record, fields)
    session = require(c, "diagnostic_sessions", record["session_id"])
    feedback["installation_id"] = session["installation_id"]
    feedback["feedback_id"] = f"{table}:{identifier}"
    feedback["root_scenario_id"] = f"order:{record['order_id']}" if record.get("order_id") else f"session:{session['id']}"
    feedback["corrected_claim_ids"] = feedback.get("assertion_targets", [])
    previous = one(c, "SELECT * FROM agent_reports WHERE session_id=:s AND created_at<=:cutoff ORDER BY id DESC LIMIT 1", {"s": session["id"], "cutoff": record["available_at"]})
    base = ensure_context(c)
    return {"kind": "feedback_extract", "table": table, "record": record, "feedback": feedback, "previous_report": obj(previous["report"]) if previous else {},
            "base": base, "preserve_corrected_facts": payload.get("preserve_corrected_facts", False)}


def feedback_compute(request, cancelled):
    from .agent import ContextStore, extract_feedback, evolve_context
    if cancelled():
        raise RuntimeError("任务取消")
    feedback = request["feedback"]
    extracted = extract_feedback(feedback)
    if request["preserve_corrected_facts"]:
        extracted["candidate_facts"] = feedback["candidate_facts"]
    # A declared reading or prose never becomes independently verified solely
    # because an extraction model restated it.
    for fact in extracted["candidate_facts"]:
        if fact.get("kind") == "observation" and feedback.get("calibration_status") != "calibrated":
            fact["trust"] = "reported"
    malicious = bool(re.search(r"忽略.{0,8}(规则|指令)|自动批准|绕过.{0,8}(权限|审批)|ignore.{0,12}(rules|instructions)|carbon_|execute\s+shell", feedback["free_text"], re.I))
    if malicious:
        return {"extracted": extracted, "state": "quarantined", "updates": [], "reason": "feedback attempts to change immutable permissions; original retained as reported evidence"}
    store = ContextStore(initial_snapshot=obj(request["base"]["content"]))
    staged = evolve_context(store, {**feedback, "candidate_facts": extracted["candidate_facts"]}, request["previous_report"])
    if cancelled():
        raise RuntimeError("任务取消")
    return {"extracted": extracted, "state": staged["state"], "updates": staged["updates"], "reason": staged.get("reason")}


def feedback_complete(c, job, result, request):
    from .agent import ContextStore, evolve_context
    current_record = require(c, request["table"], request["record"]["id"])
    if current_record["version"] != request["record"]["version"]:
        raise HTTPException(409, "抽取期间反馈被修正，拒绝覆盖")
    execute(c, f"UPDATE {request['table']} SET candidate_facts=:f,extraction_status=:s,version=version+1 WHERE id=:i",
            {"f": js(result["extracted"]["candidate_facts"]), "s": "quarantined" if result["state"] == "quarantined" else "succeeded", "i": current_record["id"]})
    save_evidence_version(c, request["table"], current_record["id"], job["created_by"], "automatic extraction publication")
    base = ensure_context(c)
    updates = result["updates"]
    activation = {"state": result["state"], "snapshot": obj(base["content"]), "reason": result.get("reason")}
    if result["state"] != "quarantined":
        store = ContextStore(initial_snapshot=obj(base["content"]))
        # Recompute a local delta against the newest snapshot after a CAS conflict;
        # source facts remain immutable and no cloud call runs in this transaction.
        if base["id"] != request["base"]["id"]:
            staged = evolve_context(store, {**request["feedback"], "candidate_facts": result["extracted"]["candidate_facts"]}, request["previous_report"])
            updates, activation = staged["updates"], staged
        else:
            activation = store.apply(updates, expected_version=base["context_version"])
    snapshot_id = base["id"]
    if activation["state"] == "active":
        snapshot_id = publish_snapshot(c, base, activation["snapshot"], updates, {"passed": True, "source_validation": True, "permission_widening": False}, job["created_by"])
    evolution_id = insert(c, "evolution_runs", {"job_id": job["id"], "method": "ace", "status": activation["state"], "base_context_version": base["context_version"],
                   "result_snapshot_id": snapshot_id, "source_feedback_ids": js([request["feedback"]["feedback_id"]]), "case_ids": js([request["feedback"]["root_scenario_id"]]),
                   "split": "operational", "changes": js(updates), "validation": js({"passed": activation["state"] != "quarantined", "reason": activation.get("reason"), "raw_text_preserved": True}),
                   "metrics": js({"candidate_fact_count": len(result["extracted"]["candidate_facts"]), "generalization_verified": False}), "provenance": request["feedback"]["provenance"],
                   "created_by": job["created_by"], "created_at": now(), "finished_at": now()})
    audit(c, job["created_by"], "context_feedback_auto_update", "evolution_run", evolution_id, {"state": activation["state"], "snapshot_id": snapshot_id, "approval_required": False})
    return {"evolution_run_id": evolution_id, "extraction_status": "quarantined" if activation["state"] == "quarantined" else "succeeded", "update_state": activation["state"], "context_snapshot_id": snapshot_id,
            "candidate_fact_count": len(result["extracted"]["candidate_facts"]), "approval_required": False}


def order_verified(c, order_id, actor_id):
    """Optional V1 verification hook; it verifies a case, never approves memory."""
    from .jobs import enqueue
    order = require(c, "orders", order_id)
    if order["verified_by"] != actor_id or actor_id in (order["assignee_id"], order["resolved_by"]):
        raise HTTPException(403, "检查事实必须独立验收")
    observations = rows(c, "SELECT * FROM inspection_observations WHERE order_id=:o", {"o": order_id})
    for observation in observations:
        execute(c, "UPDATE inspection_observations SET verification_status='independently_verified',extraction_status='verification_pending',version=version+1 WHERE id=:i", {"i": observation["id"]})
        save_evidence_version(c, "inspection_observations", observation["id"], actor_id, "independent V1 verification")
    schedule_pending_feedback(c)


def schedule_pending_feedback(c):
    """Bounded background admission; a full compute queue never blocks acceptance."""
    from .jobs import enqueue
    if one(c, "SELECT count(*) n FROM jobs WHERE status IN ('queued','running')")["n"] >= 12:
        return None
    pending = rows(c, """SELECT i.id,i.version,o.verified_by FROM inspection_observations i JOIN orders o ON o.id=i.order_id
                       WHERE i.extraction_status='verification_pending' AND o.verified_by IS NOT NULL ORDER BY i.id LIMIT 200""")
    if not pending:
        return None
    actor = pending[0]["verified_by"]
    pending = [record for record in pending if record["verified_by"] == actor]
    ids = [record["id"] for record in pending]
    job_id = enqueue(c, "feedback_verified_batch", {"observation_ids": ids}, {"id": actor}, "verified-batch-" + fingerprint([[r["id"], r["version"]] for r in pending]))
    for identifier in ids:
        execute(c, "UPDATE inspection_observations SET extraction_status='queued_verification' WHERE id=:i", {"i": identifier})
    return job_id


GEPA_AUTOMATIC_ATTEMPTS = 3
GEPA_RETRY_SECONDS = 60


def _gepa_provider_signature():
    # Credentials are hashed, never persisted. Configuration changes can unblock
    # a batch deferred without a Key without repeatedly enqueueing offline work.
    return fingerprint({field: os.environ.get(field, default) for field, default in (
        ("BATTERY_LLM_API_KEY", ""), ("BATTERY_LLM_BASE_URL", "https://api.deepseek.com"),
        ("BATTERY_LLM_MODEL", "deepseek-flash"), ("BATTERY_LLM_PROXY", "http://127.0.0.1:7897"))})


def _gepa_feedback(c, feedback_id):
    try:
        table, identifier = feedback_id.split(":", 1)
        if table not in ("inspection_observations", "diagnostic_feedback"):
            return None
        return one(c, f"SELECT * FROM {table} WHERE id=:i", {"i": int(identifier)})
    except (AttributeError, TypeError, ValueError):
        return None


def _gepa_job_matches(job, source):
    payload = obj(job["payload"])
    if payload.get("sources"):
        return any((item.get("root_id"), item.get("feedback_id"), item.get("feedback_version")) ==
                   (source["root_id"], source["feedback_id"], source["feedback_version"])
                   for item in payload["sources"])
    # Legacy jobs did not pin versions. A later ACE publication proves a new
    # revision, rather than permanently consuming the root event identity.
    return (source["root_id"] in payload.get("root_ids", [])
            and (not payload.get("feedback_ids") or source["feedback_id"] in payload["feedback_ids"])
            and source["source_event_created_at"] <= job["created_at"])


def _gepa_job_generation(job, source):
    payload = obj(job["payload"])
    for item in payload.get("sources", []):
        if (item.get("root_id"), item.get("feedback_id"), item.get("feedback_version")) == (
                source["root_id"], source["feedback_id"], source["feedback_version"]):
            return item.get("retry_generation", payload.get("retry_generation", 0))
    return payload.get("retry_generation", 0)


def _gepa_disposition(job):
    """Reserved, consumed, deferred, retryable, or explicitly stopped."""
    if job.get("cancel_requested") or job["status"] == "cancelled":
        return "cancelled"
    if job["status"] in ("queued", "running"):
        return "reserved"
    if job["status"] == "interrupted":
        # Restart never silently replays potentially billable interrupted work.
        return "interrupted"
    result = obj(job.get("result"))
    validation = obj(job.get("run_validation"))
    reason = result.get("validation", {}).get("reason", validation.get("reason"))
    state = result.get("state", job.get("run_status", job["status"]))
    if reason == "cloud_candidate_client_not_configured":
        return "deferred"
    if job["status"] == "failed" or state in ("conflicted", "failed"):
        return "retryable"
    if reason == "cloud_candidate_generation_failed":
        return "retryable"
    metrics = result.get("metrics", obj(job.get("run_metrics")))
    candidates = metrics.get("candidate_evaluation", [])
    if metrics.get("provider_failed_requests", 0):
        baseline = next((item.get("metrics", {}) for item in candidates
                         if item.get("candidate", {}).get("candidate_id") == "baseline"), {})
        reasons = {item.get("reason") for item in baseline.get("hard_failures", [])}
        # Executor can catch a provider exception and return a fallback report
        # with metrics. Those numbers cannot establish a valid comparison floor.
        # Actual safety/permission rejection stays terminal rather than retrying
        # until a forbidden action happens to pass.
        safety_failures = {"tool_or_execution_permission_violation", "safety_infeasible_test_recommended"}
        if not baseline or ("cloud_report_not_strictly_valid" in reasons and not reasons & safety_failures):
            return "retryable"
    return "consumed"


def _enqueue_context_gepa(c, sources, actor, *, key, retry_of=None, retry_generation=0, explicit_retry=False):
    from .jobs import enqueue
    current = ensure_context(c)
    root_ids = [source["root_id"] for source in sources]
    payload = {"root_ids": root_ids, "feedback_ids": [source["feedback_id"] for source in sources],
               "sources": sources, "batch_size": len(sources), "max_rollouts": 200, "selection_count": 5,
               "provider_config_sha256": _gepa_provider_signature(), "retry_generation": retry_generation,
               "retry_of_job_ids": sorted(set(retry_of or [])), "automatic_attempt_limit": GEPA_AUTOMATIC_ATTEMPTS,
               "explicit_retry": explicit_retry}
    job_id = enqueue(c, "context_gepa", payload, {"id": actor}, key)
    if one(c, "SELECT id FROM evolution_runs WHERE job_id=:j", {"j": job_id}):
        return job_id
    identifier = insert(c, "evolution_runs", {"job_id": job_id, "method": "gepa", "status": "queued", "base_context_version": current["context_version"],
               "source_feedback_ids": js(payload["feedback_ids"]), "case_ids": js(root_ids), "split": "operational",
               "changes": "[]", "validation": js({"automatic": not explicit_retry, "distinct_root_count": len(root_ids),
               "source_consumption": "reserved", "sources": sources, "retry_of_job_ids": payload["retry_of_job_ids"]}), "metrics": "{}",
               "provenance": "source_tagged_operational_with_synthetic_selection", "created_by": actor, "created_at": now()})
    audit(c, actor, "context_gepa_explicit_retry" if explicit_retry else "context_gepa_auto_enqueue", "evolution_run", identifier,
          {"root_count": len(root_ids), "selection_split": "dev", "approval_required": False, "retry_of_job_ids": payload["retry_of_job_ids"],
           "retry_generation": retry_generation, "sources": sources})
    return job_id


def schedule_context_gepa(c):
    """Versioned reservations; at most three automatic attempts per revision."""
    if one(c, "SELECT count(*) n FROM jobs WHERE status IN ('queued','running')")["n"] >= 12:
        return None
    try:
        batch_size = max(1, min(200, int(os.environ.get("BATTERY_GEPA_BATCH_SIZE", "50"))))
    except ValueError:
        batch_size = 50
    history = rows(c, """SELECT j.*,e.status run_status,e.validation run_validation,e.metrics run_metrics
                         FROM jobs j LEFT JOIN evolution_runs e ON e.job_id=j.id
                         WHERE j.kind='context_gepa' ORDER BY j.id""")
    eligible = {}
    for event in rows(c, "SELECT * FROM evolution_runs WHERE method='ace' AND split='operational' AND status IN ('active','no_update') ORDER BY id"):
        root_ids, feedback_ids = obj(event["case_ids"], []), obj(event["source_feedback_ids"], [])
        if not root_ids or not feedback_ids:
            continue
        feedback = _gepa_feedback(c, feedback_ids[0])
        if feedback is None or feedback["extraction_status"] not in ("succeeded", "corrected"):
            continue
        eligible[root_ids[0]] = {"root_id": root_ids[0], "feedback_id": feedback_ids[0], "feedback_version": feedback["version"],
                                 "source_event_id": event["id"], "source_event_created_at": event["created_at"], "actor_id": event["created_by"]}
    candidates = []
    provider_signature = _gepa_provider_signature()
    for source in eligible.values():
        matches = [job for job in history if _gepa_job_matches(job, source)]
        if any(_gepa_disposition(job) == "consumed" for job in matches):
            continue
        generation = max((_gepa_job_generation(job, source) for job in matches), default=0)
        attempts = [job for job in matches if _gepa_job_generation(job, source) == generation]
        dispositions = [(job, _gepa_disposition(job)) for job in attempts]
        if any(state in ("reserved", "consumed", "cancelled", "interrupted") for _, state in dispositions):
            continue
        if any(state == "deferred" and (not os.environ.get("BATTERY_LLM_API_KEY") or
               obj(job["payload"]).get("provider_config_sha256") == provider_signature) for job, state in dispositions):
            continue
        failures = [job for job, state in dispositions if state == "retryable"]
        if len(failures) >= GEPA_AUTOMATIC_ATTEMPTS:
            continue
        if failures:
            latest = failures[-1]
            stamp = latest.get("finished_at") or latest["created_at"]
            try:
                finished = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                finished = finished.replace(tzinfo=finished.tzinfo or timezone.utc)
                delay = min(300, GEPA_RETRY_SECONDS * 2 ** (len(failures) - 1))
                if datetime.now(timezone.utc) < finished + timedelta(seconds=delay):
                    continue
            except (ValueError, TypeError):
                # Unknown terminal time requires explicit recovery, never hot-loop.
                continue
        candidates.append({**source, "retry_generation": generation})
    if len(candidates) < batch_size:
        return None
    selected = sorted(candidates, key=lambda source: source["root_id"])[:batch_size]
    selected_history = [job for job in history if any(_gepa_job_matches(job, source) for source in selected)]
    generation = max((obj(job["payload"]).get("retry_generation", 0) for job in selected_history), default=0)
    source_key = [(source["root_id"], source["feedback_id"], source["feedback_version"]) for source in selected]
    key = "auto-gepa-" + fingerprint([source_key, [job["id"] for job in selected_history], provider_signature])
    return _enqueue_context_gepa(c, selected, selected[0]["actor_id"], key=key,
                                  retry_of=[job["id"] for job in selected_history], retry_generation=generation)


@router.post("/evolution/runs/{identifier}/retry", status_code=202)
def retry_context_gepa(identifier: int, request: Request, user=Depends(roles("admin", "researcher"))):
    """Explicit recovery also permits deliberate resumption after cancellation."""
    key, body = request.headers.get("idempotency-key", ""), {"evolution_run_id": identifier}
    with tx() as c:
        old = replay(c, user, "context_gepa_retry", key, body)
        if old:
            return response(request, **old)
        run = require(c, "evolution_runs", identifier)
        if not run.get("job_id"):
            raise HTTPException(409, "此进化记录没有可恢复作业")
        job = require(c, "jobs", run["job_id"])
        if job["kind"] != "context_gepa" or job["status"] in ("queued", "running"):
            raise HTTPException(409, "只有已终结的 GEPA 作业可以显式恢复")
        if job["created_by"] != user["id"] and user["role"] != "admin":
            raise HTTPException(403, "只能恢复自己的 GEPA 作业")
        record = {**job, "run_status": run["status"], "run_validation": run["validation"], "run_metrics": run["metrics"]}
        if _gepa_disposition(record) == "consumed":
            raise HTTPException(409, "此来源版本已经完成候选评估或终结，不重复消费")
        if not os.environ.get("BATTERY_LLM_API_KEY"):
            raise HTTPException(503, "云端候选接口尚未配置；恢复未入队且不产生费用")
        payload = obj(job["payload"])
        history = rows(c, """SELECT j.*,e.status run_status,e.validation run_validation,e.metrics run_metrics
                             FROM jobs j LEFT JOIN evolution_runs e ON e.job_id=j.id WHERE j.kind='context_gepa'""")
        sources = []
        for root_id, feedback_id in zip(payload.get("root_ids", []), payload.get("feedback_ids", [])):
            feedback = _gepa_feedback(c, feedback_id)
            if feedback is None or feedback["extraction_status"] not in ("succeeded", "corrected"):
                raise HTTPException(409, "来源反馈尚未完成安全抽取")
            event = one(c, "SELECT * FROM evolution_runs WHERE method='ace' AND source_feedback_ids=:f ORDER BY id DESC LIMIT 1", {"f": js([feedback_id])})
            source = {"root_id": root_id, "feedback_id": feedback_id, "feedback_version": feedback["version"],
                      "source_event_id": event["id"] if event else None, "source_event_created_at": event["created_at"] if event else now(), "actor_id": user["id"]}
            if any(_gepa_job_matches(other, source) and _gepa_disposition(other) == "consumed" for other in history):
                raise HTTPException(409, "当前来源版本已经完成候选评估或终结，不重复消费")
            source["retry_generation"] = max((_gepa_job_generation(other, source) for other in history
                                               if _gepa_job_matches(other, source)), default=0) + 1
            sources.append(source)
        if not sources or any(any(_gepa_job_matches(other, source) for source in sources)
                              for other in rows(c, "SELECT * FROM jobs WHERE kind='context_gepa' AND status IN ('queued','running')")):
            raise HTTPException(409, "同一来源版本已有预留作业或来源为空")
        generation = max(source["retry_generation"] for source in sources)
        job_id = _enqueue_context_gepa(c, sources, user["id"], key=key,
                                      retry_of=[job["id"]], retry_generation=generation, explicit_retry=True)
        new_run = one(c, "SELECT id FROM evolution_runs WHERE job_id=:j", {"j": job_id})
        result = {"job_id": job_id, "evolution_run_id": new_run["id"], "resumed_from_job_id": job["id"]}
        return response(request, **remember(c, user, "context_gepa_retry", key, body, result))


def evolution_snapshot(c, job):
    payload = obj(job["payload"])
    run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
    base = ensure_context(c)
    if base["context_version"] != payload["base_version"]:
        raise HTTPException(409, "实验上下文已变化，请重新提交")
    execute(c, "UPDATE evolution_runs SET status='running' WHERE id=:i", {"i": run["id"]})
    return {"kind": "evolution_experiment", "payload": payload, "run": run, "base": base}


def _evaluation_cases(case_ids, split):
    from tools.content.replay import read_selected_jsonl
    # Hidden labels remain in this scorer-only loader, outside the Agent context.
    directory = REPO_ROOT / "content_v1"
    split_directory = "evaluation/sealed" if split == "sealed_test" else "evaluation/dev" if split == "dev" else "streams"
    candidates = sorted((directory / split_directory).glob("*.jsonl"))
    records = {}
    for file in candidates:
        if file.is_file():
            for case in read_selected_jsonl(file, set(case_ids)):
                records[case.get("case_id", case.get("root_scenario_id"))] = case
    if not records:
        if candidates:
            raise ValueError("所请求根事件未登记在当前 split")
        raise RuntimeError("合成案例包未就绪，未使用虚构评测成绩")
    assignments = json.loads((directory / "manifests/splits.json").read_text())["root_assignments"]
    requested_split = "sealed" if split == "sealed_test" else split
    # Validate public root membership before opening the shared evaluator label
    # store; a wrong-split request cannot select a protected label row.
    for identifier in case_ids:
        if identifier not in records:
            raise ValueError(f"未登记案例: {identifier}")
        actual_split = "sealed" if assignments[identifier] in ("sealed", "sealed_test") else assignments[identifier]
        if actual_split != requested_split:
            raise ValueError("案例实际根级 split 与实验请求不一致")
    labels = {item["case_id"]: item for item in read_selected_jsonl(directory / "oracle/labels.jsonl", set(case_ids))}
    result = []
    for identifier in case_ids:
        case = copy.deepcopy(records[identifier])
        case["split"] = requested_split
        oracle = labels[identifier]
        case["asset"] = case.get("asset_context", {})
        case["hidden_truth"] = oracle["hidden_truth"]
        case["expected_behavior"] = oracle["expected_behavior"]
        case["feedback"] = next(iter(oracle.get("feedback_events", [])), {})
        case["initial_visible"]["asset_id"] = case["asset"]["asset_id"]
        case["initial_visible"]["installation_id"] = case["asset"]["installation_id"]
        case["initial_visible"]["asset"] = case["asset"]
        case["initial_visible"]["visible_cutoff"] = case["initial_visible"].get("cutoff")
        case["test_catalog"] = json.loads((directory / "manifests/test_catalog.json").read_text())["tests"]
        for observation in case["initial_visible"].get("observations", []):
            observation["evidence_id"] = observation.get("observation_id")
            observation["installation_id"] = case["asset"]["installation_id"]
            observation["measured_at"] = observation["timestamp"]
        result.append(case)
    return result


def evolution_compute(request, cancelled):
    from .agent import ReplayEvaluator, SkillLibrary, run_agent
    payload = request["payload"]
    cases = _evaluation_cases(payload["case_ids"], payload["split"])
    method_arm = {"no_memory": "A1", "fixed": "A2", "reflexion": "A2", "ace": "A3", "gepa": "A4"}
    library = SkillLibrary(REPO_ROOT / "content_v1")
    if cancelled():
        raise RuntimeError("任务取消")
    optimizer = None
    if payload["method"] == "gepa" and payload["split"] == "evolution":
        from .agent.gepa_service import make_batch_optimizer
        optimizer = make_batch_optimizer(REPO_ROOT / "content_v1", max_rollouts=payload["max_rollouts"], direct_root_count=len(cases),
                                         batch_size=min(50, len(cases)), cancelled=cancelled)
    replay_environment = None
    if payload["split"] == "evolution":
        from tools.content.replay import EvaluatorReplay
        replay_environment = EvaluatorReplay(REPO_ROOT / "content_v1", oracle_access=True,
                                             allowed_splits={payload["split"]}, case_ids=set(payload["case_ids"]))
    direct_runs = []
    def tracked_runner(*args, **kwargs):
        if cancelled():
            raise RuntimeError("实验已取消")
        result = run_agent(*args, **kwargs)
        direct_runs.append(result.get("run", {}))
        return result
    try:
        evaluation = ReplayEvaluator().evaluate(method_arm[payload["method"]], cases, initial_snapshot=obj(request["base"]["content"]), skill_library=library,
                                frozen_config={"base_context_version": payload["base_version"], "method": payload["method"], "case_ids": payload["case_ids"], "max_rollouts": payload["max_rollouts"],
                                               "memory_enabled": payload["method"] != "no_memory"},
                                milestone=payload["split"] == "sealed_test", batch_optimizer=optimizer, batch_size=min(50, len(cases)), runner=tracked_runner,
                                replay_environment=replay_environment, replay_authorized_test_ids=["T_TIME_ALIGN", "T_CHANNEL_CHECK"] if replay_environment else [],
                                allow_context_updates=payload["method"] != "fixed", memory_enabled=payload["method"] != "no_memory")
    finally:
        staged = optimizer.service.accounting() if optimizer else {}
        direct_count, search_count = len(direct_runs), staged.get("rollouts", 0)
        request["_accounting"] = {**_provider_metrics(direct_runs, [staged]), "rollouts": direct_count + search_count,
                                 "budget": {"rollouts": direct_count + search_count, "direct_root_count": direct_count,
                                            "gepa_rollouts_used": search_count, "max_rollouts": payload["max_rollouts"],
                                            "remaining_rollouts": payload["max_rollouts"] - direct_count - search_count},
                                 "selection_root_ids": staged.get("selection_root_ids", []), "source_root_ids": payload["case_ids"]}
    if cancelled():
        raise RuntimeError("任务取消")
    evaluation["requested_method"] = payload["method"]
    search_runs = [record["gepa_result"] for record in evaluation["records"] if "gepa_result" in record]
    search_rollouts = optimizer.service.rollouts if optimizer else 0
    evaluation["rollouts"] = len(cases) + search_rollouts
    evaluation["budget"] = {"rollouts": evaluation["rollouts"], "direct_root_count": len(cases), "gepa_rollouts_used": search_rollouts,
                            "max_rollouts": payload["max_rollouts"], "remaining_rollouts": payload["max_rollouts"] - evaluation["rollouts"]}
    evaluation["gepa_status"] = ("candidate_selection_executed" if search_rollouts else
                                 "no_update" if search_runs else "awaiting_reachable_feedback_batch" if optimizer else
                                 "read_only_no_feedback_batch" if payload["method"] == "gepa" else "not_requested")
    direct_runs = [record.get("run", {}) for record in evaluation["records"]]
    evaluation["provider_metrics"] = _provider_metrics(direct_runs, search_runs)
    evaluation["gepa_telemetry"] = {"runs": search_runs, "rollouts": search_rollouts,
                                    "selection_root_ids": sorted({root for run in search_runs for root in run.get("selection_root_ids", [])})}
    # The worker may receive cancellation after compute returns but before its
    # publication transaction; retain the complete successful compute costs.
    request["_accounting"] = {**evaluation["provider_metrics"], "rollouts": evaluation["rollouts"], "budget": evaluation["budget"],
                             "selection_root_ids": evaluation["gepa_telemetry"]["selection_root_ids"], "source_root_ids": payload["case_ids"]}
    return evaluation


def _provider_metrics(direct_runs, search_runs):
    usage = {}
    for record in [run.get("llm_usage", {}) for run in direct_runs] + [run.get("provider_usage", {}) for run in search_runs]:
        for field, value in record.items():
            usage[field] = usage.get(field, 0) + value
    return {"provider_requests": sum(run.get("llm_request_count", 0) for run in direct_runs) + sum(run.get("provider_requests", 0) for run in search_runs),
            "provider_failed_requests": sum(run.get("llm_failed_request_count", 0) for run in direct_runs) + sum(run.get("provider_failed_requests", 0) for run in search_runs),
            "provider_unknown_usage_requests": sum(run.get("llm_unknown_usage_request_count", 0) for run in direct_runs) + sum(run.get("provider_unknown_usage_requests", 0) for run in search_runs),
            "provider_usage": usage}


def evolution_complete(c, job, result, request):
    from .agent.experiment_metrics import METRICS_VERSION, PROTOCOL_VERSION, ExperimentMetrics
    base = ensure_context(c)
    run = request["run"]
    payload = request["payload"]
    state = "succeeded"
    snapshot_id = None
    changes = result.get("context_changes", result["final_context_snapshot"].get("changes", []))
    if payload["activate"]:
        if base["id"] != request["base"]["id"]:
            state = "conflicted"
        elif changes:
            snapshot_id = publish_snapshot(c, base, result["final_context_snapshot"], changes, {"passed": True, "source_split": "evolution", "generalization_verified": False}, job["created_by"])
            state = "active"
    measured = ExperimentMetrics.model_validate(result["metrics"]).model_dump()
    metrics = {**measured, "root_count": result["root_count"], "generalization_verified": False, "label": result["label"], "gepa_status": result["gepa_status"],
               **result.get("provider_metrics", {}), "gepa_telemetry": result.get("gepa_telemetry", {})}
    execution_modes = sorted({record.get("run", {}).get("execution_mode", "unrecorded") for record in result["records"]})
    llm_models = sorted({record["run"]["llm_model"] for record in result["records"] if record.get("run", {}).get("llm_model")})
    protocol = {**result["frozen_config"], "protocol_version": PROTOCOL_VERSION,
                "metric_schema_version": METRICS_VERSION, "split": payload["split"], "method": payload["method"],
                "execution_modes": execution_modes, "llm_models": llm_models}
    comparison_protocol = {"protocol_version": PROTOCOL_VERSION, "metric_schema_version": METRICS_VERSION,
                          "split": payload["split"], "method": payload["method"], "case_ids": sorted(payload["case_ids"]),
                          "max_rollouts": payload["max_rollouts"], "activate": payload["activate"],
                          "execution_modes": execution_modes, "llm_models": llm_models,
                          "frozen_controls": {key: value for key, value in result["frozen_config"].items()
                                              if key not in ("base_context_version", "case_ids")}}
    validation = {"passed": state != "conflicted", "case_split_verified": True, "selection_eligible": result["selection_eligible"],
                  "frozen_config_sha256": result["frozen_config_sha256"], "experiment_protocol_id": fingerprint(comparison_protocol)}
    execute(c, "UPDATE evolution_runs SET status=:s,result_snapshot_id=:snapshot,changes=:changes,validation=:validation,metrics=:metrics,finished_at=:t WHERE id=:i",
            {"s": state, "snapshot": snapshot_id, "changes": js(changes), "validation": js(validation), "metrics": js(metrics), "t": now(), "i": run["id"]})
    evaluation_id = insert(c, "evaluation_runs", {"evolution_run_id": run["id"], "split": payload["split"], "sample_count": result["root_count"], "metrics": js(metrics),
                "protocol": js(protocol), "budget": js(result["budget"]), "created_at": now()})
    audit(c, job["created_by"], "evolution_experiment_complete", "evolution_run", run["id"], {"status": state, "split": payload["split"], "snapshot_id": snapshot_id})
    # Store reports and scores in job result, never evaluator hidden labels.
    return {"evolution_run_id": run["id"], "evaluation_id": evaluation_id, "status": state, "context_snapshot_id": snapshot_id, "metrics": metrics,
            "records": result["records"], "budget": result["budget"]}


def gepa_snapshot(c, job):
    payload = obj(job["payload"])
    base = ensure_context(c)
    run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
    events = []
    expected_versions = {item["feedback_id"]: item["feedback_version"] for item in payload.get("sources", [])}
    for root_id, feedback_id in zip(payload["root_ids"], payload["feedback_ids"]):
        table, identifier = feedback_id.split(":", 1)
        if table not in ("inspection_observations", "diagnostic_feedback"):
            raise RuntimeError("GEPA 来源不是已完成反馈")
        feedback = public(require(c, table, int(identifier)), ("measurements", "performed_actions", "candidate_facts", "assertion_targets", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items"))
        if feedback["extraction_status"] not in ("succeeded", "corrected"):
            raise HTTPException(409, "GEPA 来源反馈尚未完成安全抽取")
        if feedback_id in expected_versions and feedback["version"] != expected_versions[feedback_id]:
            raise HTTPException(409, "GEPA 预留来源版本已变化，旧批次不读取新版反馈")
        report = one(c, "SELECT * FROM agent_reports WHERE session_id=:s AND created_at<=:cutoff ORDER BY id DESC LIMIT 1", {"s": feedback["session_id"], "cutoff": feedback["available_at"]})
        if report is None:
            raise RuntimeError("反馈来源缺少可观察的原报告")
        events.append({"root_scenario_id": root_id, "case_id": root_id, "split": "operational", "report": obj(report["report"]),
                       "tool_trace": obj(report["tool_trace"], []), "feedback": {**feedback, "feedback_id": feedback_id, "root_scenario_id": root_id}})
    execute(c, "UPDATE evolution_runs SET status='running',base_context_version=:v WHERE id=:i", {"v": base["context_version"], "i": run["id"]})
    return {"kind": "context_gepa", "payload": payload, "base": base, "run": run, "feedback_events": events}


def gepa_compute(request, cancelled):
    from .agent import ContextStore
    from .agent.gepa_service import GEPAService
    payload = request["payload"]
    service = GEPAService(REPO_ROOT / "content_v1", max_rollouts=payload["max_rollouts"], batch_size=payload["batch_size"],
                          selection_count=payload["selection_count"], cancelled=cancelled)
    try:
        return service.optimize(request["feedback_events"], ContextStore(initial_snapshot=obj(request["base"]["content"])))
    finally:
        request["_accounting"] = service.accounting()


def evolution_accounting(c, job, result, request, error):
    """Persist spent compute costs on failure/cancel; never publish business state."""
    source = (request or {}).get("_accounting") or ({**result, **result.get("provider_metrics", {})} if result else {})
    fields = {"rollouts", "budget", "provider_usage", "provider_requests", "provider_failed_requests", "provider_unknown_usage_requests", "selection_root_ids", "source_root_ids"}
    accounting = {field: source[field] for field in fields if field in source}
    if not accounting:
        return
    accounting.update(accounting_only=True, terminal_error_type=type(error).__name__ if error else None)
    record = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
    if record:
        metrics = {**obj(record["metrics"]), **accounting, "generalization_verified": False}
        execute(c, "UPDATE evolution_runs SET metrics=:m WHERE id=:i", {"m": js(metrics), "i": record["id"]})
        audit(c, job["created_by"], "evolution_terminal_accounting", "evolution_run", record["id"], accounting)


def gepa_complete(c, job, result, request):
    from .agent import ContextStore
    current = ensure_context(c)
    state, snapshot_id = result.get("state", "no_update"), None
    update = result.get("activation_update")
    regression = result.get("regression")
    sources = [_gepa_feedback(c, event["feedback"]["feedback_id"]) for event in request["feedback_events"]]
    source_changed = any(source is None or source["version"] != event["feedback"]["version"]
                         for source, event in zip(sources, request["feedback_events"]))
    conflict_reason = "source_feedback_version_changed" if source_changed else None
    if source_changed:
        state = "conflicted"
    if update:
        captured = obj(request["base"]["content"])
        if (source_changed or current["id"] != request["base"]["id"] or result.get("base_context_version") != captured["version"]
                or result.get("base_context_snapshot_id") != captured["context_snapshot_id"]):
            state = "conflicted"
            conflict_reason = conflict_reason or "context_version_changed"
        else:
            applied = ContextStore(initial_snapshot=obj(current["content"])).apply([update], expected_version=current["context_version"], source_scope="evolution", regression=regression)
            state = applied["state"]
            if state == "active":
                snapshot_id = publish_snapshot(c, current, applied["snapshot"], [update], {"passed": True, "regression": regression, "automatic": True}, job["created_by"])
    metrics = {"candidate_evaluation": result.get("candidateevaluation", result.get("candidates", [])), "rollouts": result.get("rollouts", 0),
               "budget": result.get("budget", {}), "provider_usage": result.get("provider_usage", {}), "provider_requests": result.get("provider_requests", 0),
               "provider_failed_requests": result.get("provider_failed_requests", 0),
               "provider_unknown_usage_requests": result.get("provider_unknown_usage_requests", 0),
               "selection_root_ids": result.get("selection_root_ids", []), "generalization_verified": False}
    disposition = _gepa_disposition({**job, "status": "succeeded", "result": js({"state": state, "metrics": metrics,
                                    "validation": {"reason": conflict_reason or result.get("reason")}})})
    validation = {"passed": state not in ("quarantined", "conflicted", "failed"), "reason": conflict_reason or result.get("reason"), "regression": regression,
                  "source_root_count": len(request["feedback_events"]), "approval_required": False, "source_consumption": disposition,
                  "sources": request["payload"].get("sources", []), "automatic_attempt_limit": GEPA_AUTOMATIC_ATTEMPTS}
    execute(c, "UPDATE evolution_runs SET status=:s,result_snapshot_id=:snapshot,changes=:changes,validation=:validation,metrics=:metrics,finished_at=:t WHERE id=:i",
            {"s": state, "snapshot": snapshot_id, "changes": js([update] if update else []), "validation": js(validation), "metrics": js(metrics), "t": now(), "i": request["run"]["id"]})
    audit(c, job["created_by"], "context_gepa_auto_complete", "evolution_run", request["run"]["id"], {"status": state, "snapshot_id": snapshot_id, "approval_required": False})
    return {"evolution_run_id": request["run"]["id"], "state": state, "context_snapshot_id": snapshot_id, "metrics": metrics, "validation": validation}


def schedule_context_regression(c, snapshot, actor, *, selection_count=5, max_rollouts=10, key=None):
    """A published version gets a bounded independent check, never sealed data."""
    from .jobs import enqueue
    if one(c, "SELECT count(*) n FROM jobs WHERE status IN ('queued','running')")["n"] >= 12:
        validation = obj(snapshot["validation"])
        validation["regression_check"] = {"state": "no_check", "reason": "compute_queue_full"}
        execute(c, "UPDATE context_snapshots SET validation=:v WHERE id=:i", {"v": js(validation), "i": snapshot["id"]})
        return None
    payload = {"snapshot_id": snapshot["id"], "base_version": snapshot["context_version"],
               "selection_count": selection_count, "max_rollouts": max_rollouts}
    job_id = enqueue(c, "context_regression", payload, {"id": actor}, key or f"context-regression-{snapshot['id']}")
    run = one(c, "SELECT id FROM evolution_runs WHERE job_id=:j", {"j": job_id})
    if run is None:
        insert(c, "evolution_runs", {"job_id": job_id, "method": "context_regression", "status": "queued",
               "base_context_version": snapshot["context_version"], "source_feedback_ids": "[]", "case_ids": "[]", "split": "dev",
               "changes": "[]", "validation": js({"automatic": True, "source_split": "dev"}), "metrics": "{}",
               "provenance": "independent_synthetic_dev_regression", "created_by": actor, "created_at": now()})
    validation = obj(snapshot["validation"])
    validation["regression_check"] = {"state": "queued", "job_id": job_id, "max_rollouts": max_rollouts,
                                     "selection_count": selection_count, "selection_split": "dev"}
    execute(c, "UPDATE context_snapshots SET validation=:v WHERE id=:i", {"v": js(validation), "i": snapshot["id"]})
    audit(c, actor, "context_regression_enqueue", "context_snapshot", snapshot["id"], payload)
    return job_id


@router.post("/context-snapshots/check", status_code=202)
def context_check(data: S.ContextRegression, request: Request, user=Depends(roles("admin", "researcher"))):
    key = request.headers.get("idempotency-key", "")
    body = data.model_dump()
    with tx() as c:
        old = replay(c, user, "context_regression_check", key, body)
        if old:
            return response(request, **old)
        current = ensure_context(c)
        if current["context_version"] != data.base_version:
            raise HTTPException(409, "上下文版本已变化，请刷新检查")
        job_id = schedule_context_regression(c, current, user["id"], selection_count=data.selection_count,
                                            max_rollouts=data.max_rollouts, key="context-check-" + fingerprint([user["id"], key]))
        result = {"job_id": job_id, "snapshot_id": current["id"], "base_version": current["context_version"],
                  "state": "queued" if job_id else "no_check", "approval_required": False}
        return response(request, **remember(c, user, "context_regression_check", key, body, result))


def context_regression_snapshot(c, job):
    payload = obj(job["payload"])
    base = require(c, "context_snapshots", payload["snapshot_id"])
    previous = require(c, "context_snapshots", base["parent_id"]) if base["parent_id"] else None
    run = one(c, "SELECT * FROM evolution_runs WHERE job_id=:j", {"j": job["id"]})
    execute(c, "UPDATE evolution_runs SET status='running' WHERE id=:i", {"i": run["id"]})
    return {"kind": "context_regression", "payload": payload, "base": base, "previous": previous, "run": run}


def context_regression_compute(request, cancelled):
    from .agent.regression import ContextRegressionService
    payload = request["payload"]
    service = ContextRegressionService(REPO_ROOT / "content_v1", selection_count=payload["selection_count"],
                                       rollout_budget=payload["max_rollouts"], cancelled=cancelled)
    current = obj(request["base"]["content"])
    previous = obj(request["previous"]["content"]) if request["previous"] else None
    source_roots = {str(root) for memory in current.get("memories", []) for root in memory.get("supporting_case_ids", [])}
    try:
        return service.check(current, previous, source_root_ids=sorted(source_roots))
    finally:
        request["_accounting"] = service.accounting()


def context_regression_complete(c, job, result, request):
    current = ensure_context(c)
    checked = request["base"]
    state, restored_id, changes = result["state"], None, []
    # A delayed check of an old version cannot undo a newer feedback update.
    captured = obj(checked["content"])
    if current["id"] != checked["id"] or current["context_version"] != request["payload"]["base_version"] or fingerprint(obj(current["content"])) != fingerprint(captured):
        state = "conflicted"
    elif state == "regression":
        previous = request["previous"]
        if previous is None or previous["state"] == "quarantined":
            state = "no_check"
        else:
            restored = obj(previous["content"])
            restored["parent_snapshot_id"] = captured["context_snapshot_id"]
            restored["context_snapshot_id"] = "automatic-rollback-" + fingerprint([checked["id"], previous["id"], now()])[:20]
            changes = [{"operation": "ROLLBACK", "from_snapshot_id": checked["id"], "restore_snapshot_id": previous["id"],
                        "reason": result["reason"], "trigger": "automatic_independent_regression"}]
            restored_id = publish_snapshot(c, current, restored, changes, {"passed": True, "trigger": "automatic_independent_regression",
                                            "checked_snapshot_id": checked["id"], "regression": result}, job["created_by"], automatic_regression=False)
            execute(c, "UPDATE context_snapshots SET state='quarantined' WHERE id=:i", {"i": checked["id"]})
            state = "rolled_back"
    validation = {**obj(checked["validation"]), "regression_check": {**result, "state": state,
                   "job_id": job["id"], "restored_snapshot_id": restored_id, "automatic": True}}
    execute(c, "UPDATE context_snapshots SET validation=:v WHERE id=:i", {"v": js(validation), "i": checked["id"]})
    execute(c, "UPDATE evolution_runs SET status=:s,result_snapshot_id=:r,changes=:changes,validation=:v,metrics=:m,finished_at=:t WHERE id=:i",
            {"s": state, "r": restored_id, "changes": js(changes), "v": js({"passed": state == "passed", "reason": result["reason"], "automatic": True}),
             "m": js(result), "t": now(), "i": request["run"]["id"]})
    if result.get("selection_root_ids"):
        insert(c, "evaluation_runs", {"evolution_run_id": request["run"]["id"], "split": "dev", "sample_count": len(result["selection_root_ids"]),
               "metrics": js(result), "protocol": js({"current_snapshot_id": checked["id"], "previous_snapshot_id": request["previous"]["id"] if request["previous"] else None,
                                                     "selection_sha256": result.get("selection_sha256"), "sealed_access": False}),
               "budget": js(result.get("budget", {})), "created_at": now()})
    audit(c, job["created_by"], "context_regression_complete", "context_snapshot", checked["id"], {"state": state, "reason": result["reason"], "restored_snapshot_id": restored_id})
    return {"state": state, "checked_snapshot_id": checked["id"], "restored_snapshot_id": restored_id,
            "evolution_run_id": request["run"]["id"], "metrics": result, "approval_required": False}
