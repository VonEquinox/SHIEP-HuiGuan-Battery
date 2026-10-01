from __future__ import annotations

import hashlib
from fastapi import APIRouter, Depends, Header, HTTPException
from .db import tx, rows, one, execute, insert, obj, js, now, audit, notify
from .security import allow
from .services import require
from .jobs import enqueue
from .dispatch import contracts as S
from .dispatch.jobs import make_snapshot, source_fingerprint, absolute_time, ensure_resources
from .dispatch.solver import validate_assignments, evaluate_objectives, OBJECTIVE_NAMES

router = APIRouter(prefix="/api/v2/dispatch", tags=["dispatch"])
read_access = allow("admin", "dispatcher", "researcher", "viewer")
human_dispatch = allow("admin", "dispatcher")


def _public(plan):
    plan = dict(plan)
    plan["input_snapshot"] = obj(plan["input_snapshot"])
    plan["result"] = obj(plan["result"], None)
    if plan["status"] == "QUEUED" and plan.get("job_status") in ("failed", "cancelled", "interrupted"):
        plan["status"] = plan["job_status"].upper()
    return plan


def _fresh(c, plan):
    if source_fingerprint(c) != plan["input_hash"]:
        raise HTTPException(409, "排班、人员、资源或工单已改变，请刷新并重新求解")


def _key(key):
    if not key or len(key) > 128:
        raise HTTPException(422, "缺少合法Idempotency-Key")
    return key


@router.get("/resources")
def resources(user=Depends(read_access)):
    with tx() as c:
        r = ensure_resources(c)
        r["payload"] = obj(r["payload"])
        return r


@router.put("/resources")
def update_resources(data: S.ResourceUpdate, user=Depends(human_dispatch)):
    with tx() as c:
        r = ensure_resources(c)
        if r["version"] != data.version:
            raise HTTPException(409, "排程资源版本冲突")
        for e in data.payload.engineers:
            person = one(c, "SELECT p.id,u.role,u.active FROM personnel p JOIN users u ON u.id=p.user_id WHERE p.user_id=:i", {"i": e.id})
            if not person or person["role"] != "technician" or not person["active"]:
                raise HTTPException(422, "班次必须绑定已有的有效维修人员")
        execute(c, "UPDATE dispatch_resources SET payload=:p,version=version+1,updated_at=:t,updated_by=:u WHERE id=1 AND version=:v",
                {"p": js(data.payload.model_dump()), "t": now(), "u": user["id"], "v": data.version})
        audit(c, user["id"], "dispatch_resources_updated", "dispatch_resources", 1, {"version": data.version + 1})
        return {"id": 1, "version": data.version + 1, "payload": data.payload.model_dump()}


@router.get("/orders/{identifier}/requirements")
def order_requirements(identifier: int, user=Depends(read_access)):
    with tx() as c:
        require(c, "orders", identifier)
        r = one(c, "SELECT * FROM dispatch_requirements WHERE order_id=:i", {"i": identifier})
        if not r:
            return {"order_id": identifier, "version": 0, "duration_minutes": 60, "required_qualifications": [], "required_tools": {}, "predecessors": [], "severity": "routine", "due_at": None, "release_at": None}
        for k, default in (("required_qualifications", []), ("predecessors", []), ("required_tools", {})):
            r[k] = obj(r[k], default)
        return r


@router.put("/orders/{identifier}/requirements")
def update_requirements(identifier: int, data: S.RequirementUpdate, user=Depends(human_dispatch)):
    with tx() as c:
        order = require(c, "orders", identifier)
        if order["status"] != "CREATED" or order["assignee_id"] is not None:
            raise HTTPException(409, "仅未分配工单可修改排程要求")
        r = one(c, "SELECT * FROM dispatch_requirements WHERE order_id=:i", {"i": identifier})
        version = r["version"] if r else 0
        if version != data.version:
            raise HTTPException(409, "任务要求版本冲突")
        if identifier in data.predecessors:
            raise HTTPException(422, "工单不能依赖自身")
        for pred in data.predecessors:
            require(c, "orders", pred)
        values = data.model_dump(mode="json", exclude={"version"})
        for key in ("required_qualifications", "predecessors", "required_tools"):
            values[key] = js(values[key])
        values.update(order_id=identifier, version=version + 1, updated_at=now(), updated_by=user["id"])
        if r:
            execute(c, "UPDATE dispatch_requirements SET " + ",".join(f"{k}=:{k}" for k in values if k != "order_id") + " WHERE order_id=:order_id", values)
        else:
            insert(c, "dispatch_requirements", values)
        audit(c, user["id"], "dispatch_requirement_updated", "order", identifier, {"version": version + 1})
        return {"order_id": identifier, "version": version + 1}


@router.post("/plans", status_code=202)
def create_plan(data: S.PlanCreate, user=Depends(human_dispatch), idempotency_key: str = Header(default="")):
    request = data.model_dump(mode="json")
    with tx() as c:
        job_id = enqueue(c, "dispatch", request, user, _key(idempotency_key))
        old = one(c, "SELECT * FROM dispatch_plans WHERE job_id=:j", {"j": job_id})
        if old:
            return {"plan_id": old["id"], "job_id": job_id, "status": old["status"], "version": old["version"]}
        snapshot = make_snapshot(c, request)
        identifier = insert(c, "dispatch_plans", {
            "job_id": job_id, "status": "QUEUED", "horizon_start": snapshot["horizon_start"],
            "horizon_minutes": data.horizon_minutes, "input_snapshot": js(snapshot),
            "input_hash": snapshot["source_hash"], "created_by": user["id"],
            "created_at": now(), "updated_at": now(),
        })
        audit(c, user["id"], "dispatch_plan_requested", "dispatch_plan", identifier, {"job_id": job_id, "order_ids": data.order_ids})
        return {"plan_id": identifier, "job_id": job_id, "status": "QUEUED", "version": 1}


@router.get("/plans")
def list_plans(user=Depends(read_access)):
    with tx() as c:
        return [_public(p) for p in rows(c, "SELECT p.*,j.status job_status,j.error job_error FROM dispatch_plans p LEFT JOIN jobs j ON j.id=p.job_id ORDER BY p.id DESC LIMIT 100")]


@router.get("/plans/{identifier}")
def get_plan(identifier: int, user=Depends(read_access)):
    with tx() as c:
        plan = one(c, "SELECT p.*,j.status job_status,j.error job_error FROM dispatch_plans p LEFT JOIN jobs j ON j.id=p.job_id WHERE p.id=:i", {"i": identifier})
        if not plan:
            raise HTTPException(404, "排程草案不存在")
        return _public(plan)


@router.patch("/plans/{identifier}")
def edit_plan(identifier: int, data: S.PlanEdit, user=Depends(human_dispatch)):
    with tx() as c:
        plan = require(c, "dispatch_plans", identifier)
        if plan["status"] != "DRAFT" or plan["version"] != data.version:
            raise HTTPException(409, "草案状态或版本已改变")
        _fresh(c, plan)
        snapshot = obj(plan["input_snapshot"])
        problem = snapshot["data"]
        submitted = [a.model_dump() for a in data.assignments]
        merged = {a["order_id"]: a for a in submitted}
        if len(merged) != len(submitted):
            raise HTTPException(422, "同一工单不能重复分配")
        for task in problem["tasks"]:
            if task.get("locked") and task["id"] not in merged:
                merged[task["id"]] = {"order_id": task["id"], "engineer_id": task["locked"]["engineer_id"], "start": task["locked"]["start"], "end": task["locked"]["start"] + task["duration"], "locked": True}
        assignments = list(merged.values())
        errors = validate_assignments(problem, assignments)
        if errors:
            raise HTTPException(422, {"message": "草案违反排程硬约束", "violations": errors})
        result = obj(plan["result"])
        result.update(assignments=sorted(assignments, key=lambda a: (a["start"], a["order_id"])),
                      unassigned=[{"order_id": t["id"], "reasons": ["dispatcher_left_unassigned"]} for t in problem["tasks"] if t["id"] not in merged],
                      objectives=dict(zip(OBJECTIVE_NAMES, evaluate_objectives(problem, assignments))),
                      lexicographic_complete=False, status="feasible", edited_by=user["id"], stages=[])
        execute(c, "UPDATE dispatch_plans SET result=:r,version=version+1,updated_at=:t WHERE id=:i AND version=:v",
                {"r": js(result), "t": now(), "i": identifier, "v": data.version})
        audit(c, user["id"], "dispatch_plan_edited", "dispatch_plan", identifier, {"version": data.version + 1, "assignments": assignments})
        return _public(require(c, "dispatch_plans", identifier))


@router.post("/plans/{identifier}/confirm")
def confirm_plan(identifier: int, data: S.PlanConfirm, user=Depends(human_dispatch), idempotency_key: str = Header(default="")):
    key = _key(idempotency_key)
    fingerprint = hashlib.sha256(js({"plan_id": identifier, "version": data.version}).encode()).hexdigest()
    with tx() as c:
        plan = require(c, "dispatch_plans", identifier)
        previous = one(c, "SELECT * FROM dispatch_plans WHERE confirmed_by=:u AND confirm_key=:k", {"u": user["id"], "k": key})
        if previous:
            if previous["confirm_request_hash"] != fingerprint:
                raise HTTPException(409, "同一幂等键不能确认不同草案或版本")
            return _public(previous)
        if plan["status"] != "DRAFT" or plan["version"] != data.version:
            raise HTTPException(409, "草案状态或版本已改变，请刷新")
        _fresh(c, plan)
        snapshot = obj(plan["input_snapshot"])
        problem = snapshot["data"]
        result = obj(plan["result"])
        if result.get("status") not in ("optimal", "feasible") or result.get("cancelled"):
            raise HTTPException(409, "尚无可确认的有效排程")
        errors = validate_assignments(problem, result["assignments"])
        if errors:
            raise HTTPException(409, {"message": "排程约束已不成立", "violations": errors})
        selected = set(problem["selected_order_ids"])
        assignments = [a for a in result["assignments"] if a["order_id"] in selected]
        if not assignments:
            raise HTTPException(422, "该草案没有可派发任务，请调整资源重新求解")
        for a in assignments:
            order = require(c, "orders", a["order_id"])
            expected = problem["order_versions"][str(order["id"])]
            if order["version"] != expected or order["status"] != "CREATED" or order["assignee_id"] is not None:
                raise HTTPException(409, "工单已被修改或接单，请刷新并重新求解")
            changed = execute(c, "UPDATE orders SET status='ASSIGNED',assignee_id=:u,updated_at=:t,version=version+1 WHERE id=:i AND version=:v AND status='CREATED' AND assignee_id IS NULL",
                              {"u": a["engineer_id"], "t": now(), "i": order["id"], "v": expected})
            if changed.rowcount != 1:
                raise HTTPException(409, "工单并发修改冲突")
            insert(c, "dispatch_assignments", {"plan_id": identifier, "order_id": order["id"], "engineer_id": a["engineer_id"],
                                              "start_at": absolute_time(plan, a["start"]), "end_at": absolute_time(plan, a["end"]), "order_version": expected + 1})
            insert(c, "order_events", {"order_id": order["id"], "from_status": "CREATED", "to_status": "ASSIGNED", "actor_id": user["id"],
                                       "note": f"人工确认排程草案#{identifier}版本{data.version}", "created_at": now()})
            notify(c, a["engineer_id"], "收到排程任务", f"工单#{order['id']}已由调度员确认分配", f"/operations?order={order['id']}")
        execute(c, "UPDATE dispatch_plans SET status='CONFIRMED',confirmed_by=:u,confirmed_at=:t,confirmed_version=:v,confirm_key=:k,confirm_request_hash=:h,version=version+1,updated_at=:t WHERE id=:i AND version=:v",
                {"u": user["id"], "t": now(), "v": data.version, "k": key, "h": fingerprint, "i": identifier})
        audit(c, user["id"], "dispatch_plan_confirmed", "dispatch_plan", identifier, {"confirmed_version": data.version, "assignments": assignments})
        return _public(require(c, "dispatch_plans", identifier))
