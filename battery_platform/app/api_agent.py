from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .contracts import v2 as S
from .db import audit, execute, insert, js, now, notify, obj, one, rows, tx
from .services import public, require
from .api_v2 import (authenticated, roles, response, fingerprint, timestamp, replay, remember, page,
                     asset_access, session_access, ensure_context, prediction_profile, test_catalog, validate_tests, versioned_evidence)

router = APIRouter(prefix="/api/v2")

PROPOSAL_JSON = ("asset_ids", "installation_ids", "allowed_tests", "required_tests", "required_qualifications", "predecessors", "required_tools", "content", "approved_content")
REPORT_JSON = ("report", "tool_trace")


def create_run(c, payload, user, key):
    from .jobs import enqueue
    asset = asset_access(c, payload["asset_id"], user, payload["installation_id"])
    if not asset["active"] or asset["installation_id"] != payload["installation_id"]:
        raise HTTPException(409, "资产已退役或安装身份已经变化")
    cutoff = timestamp(payload["visible_cutoff"])
    session_id = payload.get("session_id")
    if session_id:
        session = session_access(c, session_id, user)
        if session["asset_id"] != asset["id"] or session["installation_id"] != payload["installation_id"]:
            raise HTTPException(409, "诊断会话资产或安装身份不一致")
        if session["status"] in ("CLOSED", "UNRESOLVED") and payload.get("round", 1) > session["round"]:
            raise HTTPException(409, "诊断已终止，追加检查需要新的提案或会话")
    else:
        if payload.get("round", 1) != 1:
            raise HTTPException(422, "新诊断会话必须从第一轮开始")
        group_id = payload.get("incident_group_id")
        if group_id:
            group = require(c, "incident_groups", group_id)
            if group["status"] != "ACTIVE" or not one(c, "SELECT group_id FROM incident_members WHERE group_id=:g AND asset_id=:a AND state='active'", {"g": group_id, "a": asset["id"]}):
                raise HTTPException(409, "群组状态或成员不一致")
        session_id = insert(c, "diagnostic_sessions", {"asset_id": asset["id"], "installation_id": asset["installation_id"],
                            "incident_group_id": group_id, "status": "OPEN", "round": 1, "created_at": now(), "created_by": user["id"]})
    if payload.get("prediction_id"):
        prediction = require(c, "predictions", payload["prediction_id"])
        if prediction["asset_id"] != asset["id"] or prediction["installation_id"] != payload["installation_id"] or prediction["created_at"] > cutoff:
            raise HTTPException(409, "指定预测不属于当前可见资产/安装身份")
    context = ensure_context(c)
    payload = {**payload, "session_id": session_id, "visible_cutoff": cutoff}
    job_id = enqueue(c, "agent_run", payload, user, "agent-" + fingerprint(key))
    existing = one(c, "SELECT * FROM agent_runs WHERE job_id=:j", {"j": job_id})
    if existing:
        return {"id": existing["id"], "run_id": existing["id"], "session_id": existing["session_id"], "job_id": job_id}
    identifier = insert(c, "agent_runs", {"job_id": job_id, "session_id": session_id, "asset_id": asset["id"], "installation_id": asset["installation_id"],
                        "visible_cutoff": cutoff, "round": payload.get("round", 1), "context_snapshot_id": context["id"],
                        "status": "queued", "agent_version": "single-executor-v2", "request": js(payload), "created_at": now()})
    audit(c, user["id"], "agent_run_enqueue", "agent_run", identifier, {"visible_cutoff": cutoff, "context_snapshot_id": context["id"]})
    return {"id": identifier, "run_id": identifier, "session_id": session_id, "job_id": job_id}


@router.post("/agent/runs", status_code=202)
def add_run(data: S.AgentRunCreate, request: Request, user=Depends(roles("admin", "researcher", "dispatcher"))):
    body = data.model_dump()
    key = request.headers.get("idempotency-key", "")
    with tx() as c:
        previous = replay(c, user, "agent_run", key, body)
        result = previous or remember(c, user, "agent_run", key, body, create_run(c, body, user, key))
    return response(request, **result)


def run_detail(c, identifier, user):
    run = public(require(c, "agent_runs", identifier), ("request",))
    session_access(c, run["session_id"], user)
    run["job"] = public(require(c, "jobs", run["job_id"]), ("result", "payload"))
    run["status"] = run["job"]["status"]
    run["report"] = one(c, "SELECT * FROM agent_reports WHERE agent_run_id=:i", {"i": identifier})
    if run["report"]:
        run["report"] = public(run["report"], REPORT_JSON)
    return run


@router.get("/agent/runs/{identifier}")
def get_run(identifier: int, request: Request, user=Depends(authenticated)):
    with tx() as c:
        return response(request, **run_detail(c, identifier, user))


@router.get("/agent/runs")
def list_runs(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
              asset_id: int | None = None, status: str = "", user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    predicates, values = [], {}
    for key, value in (("asset_id", asset_id), ("status", status)):
        if value is not None and value != "":
            predicates.append(f"{key}=:{key}")
            values[key] = value
    with tx() as c:
        return response(request, **page(c, "agent_runs", cursor=cursor, limit=limit, predicates=predicates, values=values, json_fields=("request",)))


@router.get("/diagnostic-sessions/{identifier}")
def get_session(identifier: int, request: Request, user=Depends(authenticated)):
    with tx() as c:
        session = session_access(c, identifier, user)
        session["runs"] = [public(v, ("request",)) for v in rows(c, "SELECT * FROM agent_runs WHERE session_id=:s ORDER BY id", {"s": identifier})]
        session["reports"] = [public(v, REPORT_JSON) for v in rows(c, "SELECT * FROM agent_reports WHERE session_id=:s ORDER BY report_version", {"s": identifier})]
        session["proposals"] = [public(v, PROPOSAL_JSON) for v in rows(c, "SELECT * FROM work_proposals WHERE session_id=:s ORDER BY id", {"s": identifier})]
        session["observations"] = [public(v, ("measurements", "observed_symptoms", "performed_actions", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items", "candidate_facts", "attachment_ids", "assertion_targets", "comparison_context"))
                                   for v in rows(c, "SELECT * FROM inspection_observations WHERE session_id=:s ORDER BY id", {"s": identifier})]
        session["feedback"] = [public(v, ("assertion_targets", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items", "candidate_facts")) for v in rows(c, "SELECT * FROM diagnostic_feedback WHERE session_id=:s ORDER BY id", {"s": identifier})]
        return response(request, **session)


def insert_proposal(c, data, user):
    report = require(c, "agent_reports", data["report_id"])
    session = session_access(c, report["session_id"], user)
    if session["status"] == "CLOSED":
        raise HTTPException(409, "已关闭诊断不能追加原事件任务")
    asset_ids = data.get("asset_ids") or [report["asset_id"]]
    group_id = data.get("incident_group_id") or session["incident_group_id"]
    if len(asset_ids) > 1:
        if not group_id:
            raise HTTPException(422, "多资产提案必须关联同源群组")
        group = require(c, "incident_groups", group_id)
        members = rows(c, "SELECT * FROM incident_members WHERE group_id=:g AND state='active'", {"g": group_id})
        if group["status"] != "ACTIVE" or not set(asset_ids).issubset(v["asset_id"] for v in members):
            raise HTTPException(409, "群组已拆分或成员发生变化")
    if report["asset_id"] not in asset_ids:
        raise HTTPException(422, "提案必须包括报告资产")
    installations = {}
    for asset_id in asset_ids:
        asset = asset_access(c, asset_id, user)
        if not asset["active"]:
            raise HTTPException(409, "提案资产已退役")
        installations[str(asset_id)] = asset["installation_id"]
    if installations[str(report["asset_id"])] != report["installation_id"]:
        raise HTTPException(409, "报告安装身份已经过期")
    validate_tests(data["allowed_tests"], data.get("required_tests", []))
    catalog = test_catalog()
    minimum_qualifications = {q for test_id in data["allowed_tests"] for q in catalog[test_id].get("required_qualifications", [catalog[test_id].get("required_skill", "battery")])}
    data["required_qualifications"] = sorted(set(data.get("required_qualifications", ["battery"])) | minimum_qualifications)
    if not set(data["required_qualifications"]).issubset({"battery", "electrical", "sensor", "inspection", "instrumentation"}):
        raise HTTPException(422, "检查资格必须来自已登记的资格目录")
    if data.get("primary_alert_id"):
        alert = require(c, "alerts", data["primary_alert_id"])
        if alert["asset_id"] not in asset_ids or alert["status"] == "RESOLVED":
            raise HTTPException(409, "主告警不属于当前活动提案资产")
    for predecessor in data.get("predecessors", []):
        require(c, "orders", predecessor)
    for field in ("due_at", "expires_at"):
        if data.get(field):
            data[field] = timestamp(data[field], future=True)
            if data[field] <= now():
                raise HTTPException(422, "截止或失效时间必须在未来")
    identifier = insert(c, "work_proposals", {"report_id": report["id"], "session_id": session["id"], "incident_group_id": group_id,
              "primary_alert_id": data.get("primary_alert_id"), "title": data["title"], "status": "PENDING_APPROVAL", "asset_ids": js(asset_ids), "installation_ids": js(installations),
              "allowed_tests": js(data["allowed_tests"]), "required_tests": js(data.get("required_tests", [])), "required_qualifications": js(data.get("required_qualifications", ["battery"])),
              "duration_minutes": data.get("duration_minutes", 60), "max_rounds": data.get("max_rounds", 3), "due_at": data.get("due_at"), "expires_at": data.get("expires_at"),
              "severity": data.get("severity", "routine"), "predecessors": js(data.get("predecessors", [])), "required_tools": js(data.get("required_tools", {})), "content": js(data),
              "created_by": user["id"], "created_at": now(), "updated_at": now()})
    audit(c, user["id"], "work_proposal_create", "work_proposal", identifier, {"report_id": report["id"], "formal_order_created": False})
    return public(require(c, "work_proposals", identifier), PROPOSAL_JSON)


@router.post("/work-proposals", status_code=201)
def propose(data: S.ProposalCreate, request: Request, user=Depends(roles("admin", "researcher", "dispatcher"))):
    body = data.model_dump()
    key = request.headers.get("idempotency-key", "")
    with tx() as c:
        previous = replay(c, user, "work_proposal", key, body)
        result = previous or remember(c, user, "work_proposal", key, body, insert_proposal(c, dict(body), user))
    return response(request, **result)


@router.get("/work-proposals")
def proposals(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), status: str = "",
              user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    with tx() as c:
        return response(request, **page(c, "work_proposals", cursor=cursor, limit=limit,
                        predicates=("status=:status",) if status else (), values={"status": status}, json_fields=PROPOSAL_JSON))


@router.get("/work-proposals/{identifier}")
def get_proposal(identifier: int, request: Request, user=Depends(authenticated)):
    with tx() as c:
        proposal = require(c, "work_proposals", identifier)
        session_access(c, proposal["session_id"], user)
        return response(request, **public(proposal, PROPOSAL_JSON))


@router.post("/work-proposals/{identifier}/approve")
def approve(identifier: int, data: S.ProposalApprove, request: Request, user=Depends(roles("admin", "dispatcher"))):
    body = data.model_dump()
    key = request.headers.get("idempotency-key", "")
    with tx() as c:
        previous = replay(c, user, f"approve:{identifier}", key, body)
        if previous:
            return response(request, **previous)
        proposal = require(c, "work_proposals", identifier)
        if proposal["status"] == "APPROVED":
            if proposal["approval_hash"] != fingerprint(body):
                raise HTTPException(409, "提案已按另一份内容批准，请查看正式工单")
            result = {"proposal_id": identifier, "order_id": proposal["order_id"], "order": require(c, "orders", proposal["order_id"]), "approved_version": proposal["approved_version"]}
            return response(request, **remember(c, user, f"approve:{identifier}", key, body, result))
        if proposal["version"] != data.version or proposal["status"] != "PENDING_APPROVAL":
            raise HTTPException(409, "提案状态或版本已改变")
        if proposal["expires_at"] and proposal["expires_at"] <= now():
            raise HTTPException(409, "提案已过期，请重新生成")
        final = public(proposal, PROPOSAL_JSON)
        for name, value in data.model_dump(exclude_none=True).items():
            if name not in ("version", "note"):
                final[name] = value
        validate_tests(final["allowed_tests"], final["required_tests"])
        catalog = test_catalog()
        minimum_qualifications = {q for test_id in final["allowed_tests"] for q in catalog[test_id].get("required_qualifications", [catalog[test_id].get("required_skill", "battery")])}
        final["required_qualifications"] = sorted(set(final["required_qualifications"]) | minimum_qualifications)
        if not set(final["required_qualifications"]).issubset({"battery", "electrical", "sensor", "inspection", "instrumentation"}):
            raise HTTPException(422, "检查资格必须来自已登记的资格目录")
        if final["due_at"]:
            final["due_at"] = timestamp(final["due_at"], future=True)
            if final["due_at"] <= now():
                raise HTTPException(409, "提案处理期限已过，请修改期限")
        if final["incident_group_id"]:
            group = require(c, "incident_groups", final["incident_group_id"])
            active_members = {v["asset_id"] for v in rows(c, "SELECT asset_id FROM incident_members WHERE group_id=:g AND state='active'", {"g": group["id"]})}
            if group["status"] != "ACTIVE" or not set(final["asset_ids"]).issubset(active_members):
                raise HTTPException(409, "同源群组已变化，请重新审阅")
        for asset_id in final["asset_ids"]:
            asset = require(c, "assets", asset_id)
            if not asset["active"] or asset["installation_id"] != final["installation_ids"][str(asset_id)]:
                raise HTTPException(409, "安装身份已变化，不能批准旧报告任务")
        report = require(c, "agent_reports", proposal["report_id"])
        main_asset_id = report["asset_id"]
        primary_alert = final["primary_alert_id"]
        linked_alerts = {v["alert_id"] for v in rows(c, "SELECT alert_id FROM incident_members WHERE group_id=:g AND alert_id IS NOT NULL", {"g": final["incident_group_id"]})} if final["incident_group_id"] else set()
        if primary_alert:
            alert = require(c, "alerts", primary_alert)
            event = require(c, "health_events", alert["event_id"])
            if alert["status"] == "RESOLVED" or event["installation_id"] != final["installation_ids"][str(alert["asset_id"])]:
                raise HTTPException(409, "主告警已解除或不属于当前安装")
            if one(c, "SELECT id FROM orders WHERE alert_id=:a", {"a": primary_alert}):
                raise HTTPException(409, "主告警已有正式工单，请使用关联任务")
        else:
            event_id = insert(c, "health_events", {"asset_id": main_asset_id, "installation_id": report["installation_id"], "severity": final["severity"],
                "reason": "人工批准的有界检查提案", "evidence": js({"proposal_id": identifier, "report_id": report["id"], "asset_ids": final["asset_ids"], "not_physical_control": True}),
                "scenario_id": f"proposal-{identifier}", "provenance": report["provenance"], "created_at": now()})
            primary_alert = insert(c, "alerts", {"event_id": event_id, "asset_id": main_asset_id, "dedup_key": f"proposal:{identifier}", "status": "OPEN", "severity": final["severity"],
                "reason": "群组检查" if len(final["asset_ids"]) > 1 else "诊断补测检查", "created_at": now(), "updated_at": now()})
        linked_alerts.add(primary_alert)
        order_id = insert(c, "orders", {"alert_id": primary_alert, "asset_id": main_asset_id, "title": final["title"], "status": "CREATED",
                         "required_skill": final["required_qualifications"][0] if final["required_qualifications"] else "battery",
                         "created_by": user["id"], "created_at": now(), "updated_at": now()})
        for asset_id in final["asset_ids"]:
            insert(c, "order_assets", {"order_id": order_id, "asset_id": asset_id, "installation_id": final["installation_ids"][str(asset_id)]})
        for alert_id in linked_alerts:
            insert(c, "order_alert_links", {"order_id": order_id, "alert_id": alert_id})
        insert(c, "order_events", {"order_id": order_id, "to_status": "CREATED", "actor_id": user["id"], "note": f"提案 #{identifier} 第 {data.version} 版经人工确认；{data.note}", "created_at": now()})
        if one(c, "SELECT name FROM sqlite_master WHERE type='table' AND name='dispatch_requirements'"):
            insert(c, "dispatch_requirements", {"order_id": order_id, "required_qualifications": js(final["required_qualifications"]),
                   "duration_minutes": final["duration_minutes"], "due_at": final["due_at"], "severity": final["severity"], "predecessors": js(final["predecessors"]),
                   "required_tools": js(final["required_tools"]), "updated_at": now(), "updated_by": user["id"]})
        final["approval_note"] = data.note
        execute(c, """UPDATE work_proposals SET status='APPROVED',approved_by=:u,approved_version=:v,approved_content=:content,approval_hash=:hash,
                order_id=:o,primary_alert_id=:a,allowed_tests=:tests,required_tests=:required,required_qualifications=:quals,max_rounds=:rounds,duration_minutes=:duration,
                due_at=:due,version=version+1,updated_at=:t WHERE id=:i AND version=:v""",
                {"u": user["id"], "v": data.version, "content": js(final), "hash": fingerprint(body), "o": order_id, "a": primary_alert,
                 "tests": js(final["allowed_tests"]), "required": js(final["required_tests"]), "quals": js(final["required_qualifications"]), "rounds": final["max_rounds"],
                 "duration": final["duration_minutes"], "due": final["due_at"], "t": now(), "i": identifier})
        insert(c, "inspection_rounds", {"order_id": order_id, "session_id": final["session_id"], "round": 1, "status": "OPEN", "authorized_tests": js(final["allowed_tests"]),
               "required_tests": js(final["required_tests"]), "created_at": now()})
        audit(c, user["id"], "work_proposal_approve", "work_proposal", identifier, {"approved_version": data.version, "order_id": order_id, "final_content": final})
        result = {"proposal_id": identifier, "order_id": order_id, "order": require(c, "orders", order_id), "approved_version": data.version}
        return response(request, **remember(c, user, f"approve:{identifier}", key, body, result))


@router.post("/work-proposals/{identifier}/reject")
def reject(identifier: int, data: S.VersionNote, request: Request, user=Depends(roles("admin", "dispatcher"))):
    with tx() as c:
        proposal = require(c, "work_proposals", identifier)
        if proposal["version"] != data.version or proposal["status"] != "PENDING_APPROVAL":
            raise HTTPException(409, "提案状态或版本冲突")
        execute(c, "UPDATE work_proposals SET status='REJECTED',version=version+1,updated_at=:t WHERE id=:i", {"t": now(), "i": identifier})
        audit(c, user["id"], "work_proposal_reject", "work_proposal", identifier, {"note": data.note})
        return response(request, **public(require(c, "work_proposals", identifier), PROPOSAL_JSON))


@router.get("/incidents")
def incidents(request: Request, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), status: str = "", provenance: str = "",
              severity: str = "",
              user=Depends(roles("admin", "researcher", "dispatcher", "viewer"))):
    predicates, values = [], {}
    for key, value in (("status", status), ("provenance", provenance)):
        if value:
            predicates.append(f"{key}=:{key}")
            values[key] = value
    with tx() as c:
        if severity:
            predicates.append("EXISTS (SELECT 1 FROM incident_members m JOIN alerts a ON a.id=m.alert_id WHERE m.group_id=incident_groups.id AND a.severity=:severity)")
            values["severity"] = severity
        result = page(c, "incident_groups", cursor=cursor, limit=limit, predicates=predicates, values=values, json_fields=("evidence",))
        for group in result["items"]:
            group["members"] = [public(v, ("evidence",)) for v in rows(c, "SELECT * FROM incident_members WHERE group_id=:g ORDER BY asset_id", {"g": group["id"]})]
            levels = [v["severity"] for v in rows(c, "SELECT a.severity FROM alerts a JOIN incident_members m ON m.alert_id=a.id WHERE m.group_id=:g", {"g": group["id"]})]
            group["severity"] = max(levels, key=lambda value: {"critical": 4, "high": 3, "warning": 2, "routine": 1, "review": 0}.get(value, 0)) if levels else "routine"
        return response(request, **result)


@router.get("/incidents/{identifier}")
def incident(identifier: int, request: Request, user=Depends(authenticated)):
    with tx() as c:
        group = require(c, "incident_groups", identifier)
        members = rows(c, "SELECT * FROM incident_members WHERE group_id=:g ORDER BY asset_id", {"g": identifier})
        for member in members:
            asset_access(c, member["asset_id"], user, member["installation_id"])
        return response(request, **public(group, ("evidence",)), members=[public(v, ("evidence",)) for v in members])


@router.post("/incidents/analyze", status_code=202)
def analyze(data: S.IncidentAnalyze, request: Request, user=Depends(roles("admin", "researcher", "dispatcher"))):
    from .jobs import enqueue
    if len(data.asset_ids) != len(set(data.asset_ids)):
        raise HTTPException(422, "资产集合不能重复")
    body = {**data.model_dump(), "visible_cutoff": timestamp(data.visible_cutoff)}
    with tx() as c:
        for asset_id in data.asset_ids:
            asset_access(c, asset_id, user)
        job_id = enqueue(c, "incident_analysis", body, user, request.headers.get("idempotency-key", ""))
        return response(request, job_id=job_id)


@router.post("/incidents/{identifier}/split")
def split(identifier: int, data: S.IncidentSplit, request: Request, user=Depends(roles("admin", "dispatcher"))):
    with tx() as c:
        group = require(c, "incident_groups", identifier)
        if group["version"] != data.version or group["status"] != "ACTIVE":
            raise HTTPException(409, "群组状态或版本冲突")
        members = rows(c, "SELECT * FROM incident_members WHERE group_id=:g AND state='active'", {"g": identifier})
        ids = {v["asset_id"] for v in members}
        selected = set(data.member_asset_ids)
        if not selected < ids or len(selected) != len(data.member_asset_ids):
            raise HTTPException(422, "拆分必须选择部分不重复的活动成员")
        children = []
        for subset in (selected, ids - selected):
            new_id = insert(c, "incident_groups", {"title": group["title"] + " · 拆分", "status": "ACTIVE", "relation_type": "split_review",
                       "reason": data.note, "evidence": js({"parent_group_id": identifier, "human_split": True, "not_confirmed_cause": True}),
                       "window_start": group["window_start"], "window_end": group["window_end"], "provenance": group["provenance"], "parent_group_id": identifier,
                       "created_at": now(), "created_by": user["id"]})
            for member in members:
                if member["asset_id"] in subset:
                    insert(c, "incident_members", {**member, "group_id": new_id})
            children.append(new_id)
        execute(c, "UPDATE incident_groups SET status='SPLIT',version=version+1 WHERE id=:i", {"i": identifier})
        execute(c, "UPDATE incident_members SET state='split' WHERE group_id=:i", {"i": identifier})
        audit(c, user["id"], "incident_split", "incident_group", identifier, {"children": children, "note": data.note, "alerts_preserved": True})
        return response(request, parent_id=identifier, child_ids=children)


def agent_snapshot(c, job):
    run = one(c, "SELECT * FROM agent_runs WHERE job_id=:j", {"j": job["id"]})
    if not run:
        raise RuntimeError("诊断作业缺少运行记录")
    asset = require(c, "assets", run["asset_id"])
    if asset["installation_id"] != run["installation_id"] or not asset["active"]:
        raise HTTPException(409, "诊断输入安装身份已变化")
    context = require(c, "context_snapshots", run["context_snapshot_id"])
    cutoff = run["visible_cutoff"]
    request = obj(run["request"])
    prediction = one(c, "SELECT * FROM predictions WHERE asset_id=:a AND installation_id=:n AND created_at<=:cutoff ORDER BY id DESC LIMIT 1",
                     {"a": asset["id"], "n": asset["installation_id"], "cutoff": cutoff})
    profile = prediction_profile(c, asset, cutoff, request.get("prediction_id"))
    # The visible profile must never use the newest prediction beyond the cutoff.
    if not profile.get("prediction_id") and not profile.get("v2_profile_id"):
        profile = {"support": {"status": "insufficient_data", "reasons": ["No prediction before cutoff"]}, "heads": {}}
    else:
        profile["heads"] = {head["head"]: head for head in profile["heads"]}
        profile.setdefault("support", {"status": "supported" if any(head["support"] == "supported" for head in profile["heads"].values()) else "unsupported", "reasons": []})
    observation_rows = rows(c, "SELECT * FROM inspection_observations WHERE session_id=:s AND installation_id=:n AND available_at<=:cutoff AND round<=:round ORDER BY id",
                    {"s": run["session_id"], "n": run["installation_id"], "cutoff": cutoff, "round": run["round"]})
    observations = [visible for record in observation_rows if (visible := versioned_evidence(c, "inspection_observations", record, cutoff)) is not None]
    for observation in observations:
        observation["evidence_id"] = f"obs-{observation['id']}"
    events = [public(v, ("evidence",)) for v in rows(c, "SELECT * FROM health_events WHERE asset_id=:a AND installation_id=:n AND created_at<=:cutoff ORDER BY id",
               {"a": asset["id"], "n": asset["installation_id"], "cutoff": cutoff})]
    for event in events:
        observations.append({"evidence_id": f"event-{event['id']}", "installation_id": event["installation_id"], "measured_at": event["created_at"], "available_at": event["created_at"],
                             "observed_symptoms": [event["reason"]], "provenance": event["provenance"], "evidence": event["evidence"]})
    previous_reports = [obj(v["report"]) for v in rows(c, "SELECT report FROM agent_reports WHERE session_id=:s AND created_at<=:cutoff ORDER BY id", {"s": run["session_id"], "cutoff": cutoff})]
    feedback_rows = rows(c, "SELECT * FROM diagnostic_feedback WHERE session_id=:s AND available_at<=:cutoff ORDER BY id", {"s": run["session_id"], "cutoff": cutoff})
    feedback = [visible for record in feedback_rows if (visible := versioned_evidence(c, "diagnostic_feedback", record, cutoff)) is not None]
    approved = one(c, "SELECT * FROM work_proposals WHERE session_id=:s AND status='APPROVED' AND updated_at<=:cutoff ORDER BY id DESC LIMIT 1", {"s": run["session_id"], "cutoff": cutoff})
    allowed = obj(approved["allowed_tests"], []) if approved else []
    catalog = test_catalog()
    authorization = {"authorized_test_ids": allowed, "qualifications": obj(approved["required_qualifications"], []) if approved else [], "round_budget": approved["max_rounds"] if approved else 0,
                     "can_propose_only": not bool(approved),
                     "human_approved": bool(approved), "can_approve": False, "can_assign": False}
    order = require(c, "orders", approved["order_id"]) if approved else None
    if order and order["assignee_id"] and order["updated_at"] <= cutoff:
        person = one(c, "SELECT skills FROM personnel WHERE user_id=:u", {"u": order["assignee_id"]})
        authorization["qualifications"] = obj(person["skills"], []) if person else []
    elif approved:
        authorization["qualifications"] = []
    group_context = {"groups": [], "causality": "not_established"}
    group_snapshot = None
    session = require(c, "diagnostic_sessions", run["session_id"])
    if session["incident_group_id"]:
        group = require(c, "incident_groups", session["incident_group_id"])
        if group["status"] != "ACTIVE" or group["created_at"] > cutoff:
            raise HTTPException(409, "关联群组已变化或尚未在当前 cutoff 可见，请刷新事件范围")
        member_rows = rows(c, "SELECT * FROM incident_members WHERE group_id=:g AND state='active' ORDER BY asset_id", {"g": group["id"]})
        peer_members, member_versions = [], []
        for member in member_rows:
            peer = require(c, "assets", member["asset_id"])
            if peer["installation_id"] != member["installation_id"] or not peer["active"]:
                raise HTTPException(409, "群组成员安装身份已变化")
            alert = require(c, "alerts", member["alert_id"]) if member["alert_id"] else None
            event = require(c, "health_events", alert["event_id"]) if alert else None
            peer_evidence = obj(event["evidence"]) if event and event["created_at"] <= cutoff else {}
            peer_rows = rows(c, """SELECT * FROM inspection_observations WHERE session_id=:s AND asset_id=:a AND installation_id=:n
                                AND available_at<=:cutoff AND round<=:round ORDER BY id DESC LIMIT 100""",
                             {"s": run["session_id"], "a": peer["id"], "n": member["installation_id"], "cutoff": cutoff, "round": run["round"]})
            peer_observations = []
            for record in reversed(peer_rows):
                visible = versioned_evidence(c, "inspection_observations", record, cutoff)
                if visible is not None:
                    # Peer evidence is explicitly scoped to the member. It is
                    # not an observation of the primary physical installation.
                    visible["peer_installation_id"] = visible.pop("installation_id")
                    visible["evidence_id"] = f"obs-{visible['id']}"
                    peer_observations.append(visible)
            peer_members.append({"asset_id": peer["id"], "peer_installation_id": member["installation_id"], "asset_name": peer["name"],
                 "alert_id": member["alert_id"], "evidence": peer_evidence, "evidence_id": f"incident-member-{group['id']}-{peer['id']}",
                 "observations": peer_observations,
                 "provenance": event["provenance"] if event else peer["provenance"], "not_confirmed_common_cause": True})
            member_versions.append({"asset_id": peer["id"], "version": peer["version"], "installation_id": peer["installation_id"],
                                    "alert_id": alert["id"] if alert else None, "alert_version": alert["version"] if alert else None})
        group_context["groups"] = [{"group_id": group["id"], "relation_type": group["relation_type"], "reason": group["reason"], "evidence": obj(group["evidence"]),
                                    "members": peer_members, "window_start": group["window_start"], "window_end": group["window_end"], "causality": "not_established"}]
        group_snapshot = {"id": group["id"], "version": group["version"], "members": member_versions}
    asset_context = {**asset, **{key: value for key, value in profile.get("query", {}).items() if key in ("chemistry", "protocol_id", "source_id", "physical_cell_id")}}
    # A diagnostic event starts with session feedback and may later acquire one
    # or more authorized inspection orders. Bind those exact historical aliases
    # on the server; neither another session nor a future approval is history.
    history_root_ids = [f"session:{run['session_id']}"]
    history_root_ids.extend(f"order:{proposal['order_id']}" for proposal in rows(c,
        "SELECT DISTINCT order_id FROM work_proposals WHERE session_id=:s AND order_id IS NOT NULL AND updated_at<=:cutoff ORDER BY order_id",
        {"s": run["session_id"], "cutoff": cutoff}))
    snapshot = {"asset_id": run["asset_id"], "installation_id": run["installation_id"], "visible_cutoff": cutoff, "round": run["round"],
                "root_scenario_id": f"order:{order['id']}" if order else f"session:{run['session_id']}",
                "history_root_ids": history_root_ids,
                "asset": asset_context, "observations": observations, "prediction": profile, "group_context": group_context,
                "completed_test_ids": sorted({observation["test_id"] for observation in observations if observation.get("test_id")}),
                "attempted_test_ids": sorted({observation["test_id"] for observation in observations if observation.get("test_id")}),
                "test_catalog": [{**test, "authorized": identifier in allowed} for identifier, test in catalog.items()],
                "authorization": authorization, "previous_reports": previous_reports, "feedback": feedback,
                "context_snapshot": obj(context["content"]), "context_snapshot_id": str(context["id"]), "context_version": context["context_version"],
                "_run": run, "_asset_version": asset["version"], "_order": order, "_actor": job["created_by"], "_group_snapshot": group_snapshot}
    execute(c, "UPDATE agent_runs SET status='running' WHERE id=:i", {"i": run["id"]})
    return snapshot


def agent_compute(request, cancelled):
    if cancelled():
        raise RuntimeError("任务取消")
    from .agent import run_agent
    from .agent import SkillLibrary
    from .config import APP_ROOT
    from .config import REPO_ROOT
    skill_path = REPO_ROOT / "content_v1"
    library = SkillLibrary(skill_path) if (skill_path / "skills").is_dir() else None
    result = run_agent({k: v for k, v in request.items() if not k.startswith("_")}, skill_library=library)
    if cancelled():
        raise RuntimeError("任务取消")
    return result


def agent_complete(c, job, result, request):
    run = request["_run"]
    asset = require(c, "assets", run["asset_id"])
    if asset["installation_id"] != run["installation_id"] or asset["version"] != request["_asset_version"]:
        raise HTTPException(409, "诊断运行期间资产或安装身份已更新")
    if request["_order"]:
        current_order = require(c, "orders", request["_order"]["id"])
        if current_order["version"] != request["_order"]["version"]:
            raise HTTPException(409, "检查工单在运行期间已更新")
    if request.get("_group_snapshot"):
        group = require(c, "incident_groups", request["_group_snapshot"]["id"])
        if group["version"] != request["_group_snapshot"]["version"] or group["status"] != "ACTIVE":
            raise HTTPException(409, "运行期间关联群组发生拆分或更新")
        for member in request["_group_snapshot"]["members"]:
            peer = require(c, "assets", member["asset_id"])
            if peer["version"] != member["version"] or peer["installation_id"] != member["installation_id"]:
                raise HTTPException(409, "运行期间群组成员身份已更新")
            if member["alert_id"]:
                alert = require(c, "alerts", member["alert_id"])
                if alert["version"] != member["alert_version"]:
                    raise HTTPException(409, "运行期间群组成员告警已更新")
    report = result["report"]
    if report.get("installation_id") != run["installation_id"]:
        raise RuntimeError("诊断输出安装身份不一致")
    version = one(c, "SELECT coalesce(max(report_version),0)+1 n FROM agent_reports WHERE session_id=:s", {"s": run["session_id"]})["n"]
    provenance = "self_synthetic" if asset["provenance"] == "simulated" else "measured_declared"
    report_id = insert(c, "agent_reports", {"agent_run_id": run["id"], "session_id": run["session_id"], "asset_id": run["asset_id"], "installation_id": run["installation_id"],
                    "round": run["round"], "report_version": version, "context_snapshot_id": run["context_snapshot_id"], "report": js(report), "tool_trace": js(result.get("tool_trace", [])),
                    "provenance": provenance, "status": report["status"], "created_at": now()})
    retrieved = set(result.get("run", {}).get("retrieved_memory_ids", []))
    frozen_keys = {item["memory_id"] for item in request["context_snapshot"].get("memories", [])}
    for memory_key in sorted(retrieved & frozen_keys):
        memory = one(c, "SELECT * FROM memory_items WHERE memory_key=:k AND context_snapshot_id<=:snapshot ORDER BY version DESC LIMIT 1",
                     {"k": memory_key, "snapshot": run["context_snapshot_id"]})
        if memory:
            execute(c, "UPDATE memory_items SET last_used=:t WHERE id=:i", {"t": now(), "i": memory["id"]})
            audit(c, job["created_by"], "memory_retrieved", "memory_item", memory["id"],
                  {"report_id": report_id, "context_snapshot_id": run["context_snapshot_id"], "memory_version": memory["version"], "helpfulness_evaluated": False})
    execute(c, "UPDATE agent_runs SET status='succeeded',finished_at=:t,version=version+1 WHERE id=:i", {"t": now(), "i": run["id"]})
    session_status = "UNRESOLVED" if report.get("termination", {}).get("reason") in ("budget_exhausted", "no_useful_test") else "OPEN"
    execute(c, "UPDATE diagnostic_sessions SET round=max(round,:r),status=:status,version=version+1 WHERE id=:s", {"r": run["round"], "s": run["session_id"], "status": session_status})
    proposal_id = None
    suggested = [item["test_id"] for item in report.get("suggested_tests", []) if item.get("test_id") in test_catalog()]
    suggested = list(dict.fromkeys(suggested))
    authorized = set(request["authorization"]["authorized_test_ids"])
    new_tests = [test for test in suggested if test not in authorized]
    if new_tests and not one(c, "SELECT id FROM work_proposals WHERE session_id=:s AND status='PENDING_APPROVAL'", {"s": run["session_id"]}):
        actor = {"id": job["created_by"], "role": "researcher"}
        proposal = insert_proposal(c, {"report_id": report_id, "title": asset["name"] + " · 诊断补测提案", "allowed_tests": new_tests, "required_tests": new_tests[:1],
                      "required_qualifications": sorted({q for test in new_tests for q in test_catalog()[test].get("required_qualifications", ["battery"])}),
                      "max_rounds": 3, "duration_minutes": sum(test_catalog()[test].get("duration_minutes", 15) for test in new_tests), "severity": "routine"}, actor)
        proposal_id = proposal["id"]
        report["proposal_id"] = str(proposal_id)
        execute(c, "UPDATE agent_reports SET report=:r WHERE id=:i", {"r": js(report), "i": report_id})
    # Further rounds use the existing bounded authorization; a report never grants tests itself.
    if request["_order"] and suggested and set(suggested).issubset(authorized) and run["round"] < request["authorization"]["round_budget"]:
        last_round = one(c, "SELECT * FROM inspection_rounds WHERE order_id=:o AND round=:r", {"o": request["_order"]["id"], "r": run["round"]})
        if last_round and last_round["status"] == "SUBMITTED" and not one(c, "SELECT id FROM inspection_rounds WHERE order_id=:o AND round=:r", {"o": request["_order"]["id"], "r": run["round"] + 1}):
            insert(c, "inspection_rounds", {"order_id": request["_order"]["id"], "session_id": run["session_id"], "round": run["round"] + 1,
                   "status": "OPEN", "authorized_tests": js(sorted(authorized)), "required_tests": js(suggested[:1]), "created_at": now()})
    audit(c, job["created_by"], "agent_report_append", "agent_report", report_id, {"run_id": run["id"], "context_snapshot_id": run["context_snapshot_id"], "proposal_id": proposal_id})
    return {"run_id": run["id"], "session_id": run["session_id"], "report_id": report_id, "report_version": version,
            "status": report["status"], "proposal_id": proposal_id, "execution_mode": result.get("run", {}).get("execution_mode", result.get("execution_mode", "unknown")),
            "run": result.get("run", {})}


def incident_snapshot(c, job):
    payload = obj(job["payload"])
    start = (datetime.fromisoformat(payload["visible_cutoff"]) - timedelta(minutes=payload["window_minutes"])).isoformat()
    members = []
    source_versions = {}
    catalog = test_catalog()
    for asset_id in payload["asset_ids"]:
        asset = require(c, "assets", asset_id)
        if not asset["active"]:
            raise HTTPException(409, "群组成员已经退役")
        alert = one(c, """SELECT a.*,e.installation_id,e.provenance,e.created_at event_at,e.evidence FROM alerts a JOIN health_events e ON e.id=a.event_id
                      WHERE a.asset_id=:a AND e.installation_id=:n AND e.created_at>=:start AND e.created_at<=:end AND a.status!='RESOLVED' ORDER BY a.id DESC LIMIT 1""",
                    {"a": asset_id, "n": asset["installation_id"], "start": start, "end": payload["visible_cutoff"]})
        observations = []
        records = rows(c, """SELECT * FROM inspection_observations WHERE asset_id=:a AND installation_id=:n AND available_at<=:end
                            AND measured_at>=:start AND measured_at<=:end ORDER BY id DESC LIMIT 500""",
                       {"a": asset_id, "n": asset["installation_id"], "start": start, "end": payload["visible_cutoff"]})
        for record in reversed(records):
            visible = versioned_evidence(c, "inspection_observations", record, payload["visible_cutoff"])
            if visible is None:
                continue
            conditions = visible.get("comparison_context") or {}
            authorization = conditions.get("authorization_ref", {})
            qualified = conditions.get("qualification_evidence", {})
            proposal = one(c, "SELECT * FROM work_proposals WHERE id=:p AND order_id=:o AND status='APPROVED'",
                           {"p": authorization.get("proposal_id"), "o": record["order_id"]})
            round_row = one(c, "SELECT * FROM inspection_rounds WHERE id=:r AND order_id=:o", {"r": authorization.get("round_id"), "o": record["order_id"]})
            scope = one(c, "SELECT * FROM order_assets WHERE order_id=:o AND asset_id=:a AND installation_id=:n",
                        {"o": record["order_id"], "a": asset_id, "n": asset["installation_id"]})
            minimum = set(catalog.get(record["test_id"], {}).get("required_qualifications", []))
            visible["_authorization_verified"] = bool(proposal and round_row and scope and authorization.get("test_id") == record["test_id"]
                and record["test_id"] in catalog and record["test_id"] in obj(round_row["authorized_tests"], []) and qualified.get("author_id") == record["author_id"]
                and minimum.issubset(set(qualified.get("required_qualifications", []))))
            observations.append(visible)
            source_versions[("inspection_observations", record["id"])] = record["version"]
            if proposal:
                source_versions[("work_proposals", proposal["id"])] = proposal["version"]
            if round_row:
                source_versions[("inspection_rounds", round_row["id"])] = round_row["version"]
        members.append({"asset": asset, "alert": alert, "observations": observations})
    return {"kind": "incident_analysis", "payload": payload, "members": members, "window_start": start,
            "_source_versions": [{"table": table, "id": identifier, "version": version} for (table, identifier), version in source_versions.items()],
            "_catalog_sha256": fingerprint(catalog)}


def incident_compute(request, cancelled):
    if cancelled():
        raise RuntimeError("任务取消")
    from .diagnosis.group_adapter import measurement_groups
    members = request["members"]
    numeric = measurement_groups(members, window_start=request["window_start"], cutoff=request["payload"]["visible_cutoff"], cancelled=cancelled)
    active = [v for v in members if v["alert"]]
    groups = {}
    for member in active:
        groups.setdefault(member["asset"]["parent_id"], []).append(member)
    candidates = list(numeric["groups"])
    covered = {member["asset"]["id"] for group in candidates for member in group["members"]}
    for parent, peers in groups.items():
        peers = [peer for peer in peers if peer["asset"]["id"] not in covered]
        if parent is None or len(peers) < 2:
            continue
        relevant = [analysis for analysis in numeric["analyses"] if analysis["comparison"]["parent_id"] == parent]
        detail = next((analysis for analysis in relevant if analysis["numeric_correlation_supported"]), relevant[0] if relevant else {})
        reasons = sorted({reason for peer in peers for reason in numeric["rejections"].get(str(peer["asset"]["id"]), [])})
        candidates.append({**detail, "members": peers, "relation_type": "topology_association", "confirmed_common_cause": False,
            "numeric_algorithm_executed": bool(relevant), "numeric_correlation_supported": bool(detail.get("numeric_correlation_supported")),
            "numeric_support": detail.get("numeric_support", {"status": "unsupported", "reasons": reasons or ["comparable_normal_reference_and_aligned_measurements_missing"]}),
            "reason": "数值关联未达到冻结阈值，保留拓扑关联且不确认共因" if relevant else "同一拓扑父节点且告警窗口重叠；可比对齐残差资格不足，不确认共因"})
    return {"groups": candidates, "numeric_analyses": numeric["analyses"], "measurement_rejections": numeric["rejections"],
            "unmatched_asset_ids": [member["asset"]["id"] for member in members if not any(member in group["members"] for group in candidates)],
            "numeric_algorithm_executed": numeric["numeric_algorithm_executed"], "numeric_correlation_supported": numeric["numeric_correlation_supported"]}


def incident_complete(c, job, result, request):
    for member in request["members"]:
        current = require(c, "assets", member["asset"]["id"])
        if current["version"] != member["asset"]["version"] or current["installation_id"] != member["asset"]["installation_id"]:
            raise HTTPException(409, "群组分析期间资产已经变化")
        if member["alert"] and require(c, "alerts", member["alert"]["id"])["version"] != member["alert"]["version"]:
            raise HTTPException(409, "群组分析期间告警已经变化")
    for source in request.get("_source_versions", []):
        if require(c, source["table"], source["id"])["version"] != source["version"]:
            raise HTTPException(409, "群组分析期间来源观察或授权范围已经变化")
    if request.get("_catalog_sha256") != fingerprint(test_catalog()):
        raise HTTPException(409, "群组分析期间测试目录资格已经变化")
    group_ids = []
    for candidate in result["groups"]:
        evidence = {"member_alert_ids": [v["alert"]["id"] for v in candidate["members"] if v["alert"]], "confirmed_common_cause": False,
                    "numeric_correlation_supported": candidate["numeric_correlation_supported"], "numeric_algorithm_executed": candidate["numeric_algorithm_executed"],
                    "numeric_support": candidate["numeric_support"], "numeric_analysis": candidate.get("numeric_analysis", {}),
                    "comparison": candidate.get("comparison"), "source_refs": candidate.get("source_refs", []),
                    "alternative_explanations": candidate.get("alternative_explanations", ["shared acquisition issue", "shared environment", "coincident individual anomalies"]),
                    "measurement_rejections": result["measurement_rejections"], "source_trust": "declared_measurements_and_normal_reference",
                    "topology_origin": "simulated" if any(v["asset"]["provenance"] == "simulated" for v in candidate["members"]) else "declared"}
        identifier = insert(c, "incident_groups", {"title": "同步残差关联检查组" if candidate["relation_type"] == "synchronous_association" else "拓扑关联检查组",
                            "status": "ACTIVE", "relation_type": candidate["relation_type"], "reason": candidate["reason"], "evidence": js(evidence),
                            "window_start": request["window_start"], "window_end": request["payload"]["visible_cutoff"], "provenance": "self_synthetic" if evidence["topology_origin"] == "simulated" else "measured_declared",
                            "created_by": job["created_by"], "created_at": now()})
        for member in candidate["members"]:
            insert(c, "incident_members", {"group_id": identifier, "asset_id": member["asset"]["id"], "installation_id": member["asset"]["installation_id"],
                                        "alert_id": member["alert"]["id"] if member["alert"] else None, "evidence": js({"event_at": member["alert"]["event_at"] if member["alert"] else None})})
        group_ids.append(identifier)
        audit(c, job["created_by"], "incident_group_create", "incident_group", identifier, evidence)
    return {"group_ids": group_ids, "unmatched_asset_ids": result["unmatched_asset_ids"], "numeric_analyses": result["numeric_analyses"],
            "measurement_rejections": result["measurement_rejections"], "numeric_algorithm_executed": result["numeric_algorithm_executed"],
            "numeric_correlation_supported": result["numeric_correlation_supported"]}
