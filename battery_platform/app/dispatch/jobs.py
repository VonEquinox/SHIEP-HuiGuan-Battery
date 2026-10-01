"""Dispatch worker contract: snapshot/read, compute/no DB transaction, complete/write."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from ..db import rows, one, obj, js, execute, now, audit
from ..services import require
from .solver import solve


ACTIVE = ("ASSIGNED", "ACCEPTED", "IN_PROGRESS", "RESOLVED", "VERIFIED")


def ensure_resources(c):
    execute(c, "INSERT OR IGNORE INTO dispatch_resources(id,payload,updated_at) VALUES(1,'{}','')")
    return require(c, "dispatch_resources", 1)


def _date(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise HTTPException(422, "排程时间必须带时区")
    return date.astimezone(timezone.utc)


def source_fingerprint(c):
    """Include all schedule-relevant state, including V1 manual assignments.

    Conservative global invalidation prevents one selected-task snapshot from
    overwriting another dispatcher or a technician's live acceptance action.
    """
    state = {
        "orders": rows(c, "SELECT id,asset_id,status,assignee_id,required_skill,version FROM orders ORDER BY id"),
        "assets": rows(c, "SELECT id,location,active,installation_id,version FROM assets ORDER BY id"),
        "personnel": rows(c, "SELECT * FROM personnel ORDER BY id"),
        "users": rows(c, "SELECT id,active,role,version FROM users ORDER BY id"),
        "requirements": rows(c, "SELECT * FROM dispatch_requirements ORDER BY order_id"),
        "order_assets": rows(c, "SELECT * FROM order_assets ORDER BY order_id,asset_id"),
        "resources": ensure_resources(c),
        "reservations": rows(c, "SELECT a.* FROM dispatch_assignments a JOIN dispatch_plans p ON p.id=a.plan_id WHERE p.status='CONFIRMED' ORDER BY a.id"),
    }
    return hashlib.sha256(js(state).encode()).hexdigest()


def make_snapshot(c, request):
    base = _date(request["horizon_start"])
    horizon = request["horizon_minutes"]
    selected = request["order_ids"]
    resources_row = ensure_resources(c)
    resources = obj(resources_row["payload"])
    data = {"horizon_minutes": horizon, "engineers": [], "tasks": [],
            "tool_capacities": resources.get("tool_capacities", {}),
            "tool_windows": resources.get("tool_windows", {}),
            "travel_minutes": resources.get("travel_minutes", {}),
            "completed_predecessors": [], "selected_order_ids": selected,
            "tool_reservations": [],
            "order_versions": {}, "resource_version": resources_row["version"],
            "warnings": [], "provenance": resources.get("provenance", "declared"),
            "scenario_id": resources.get("scenario_id")}
    def offset(value, default, rounding=math.ceil):
        return default if not value else int(rounding((_date(value) - base).total_seconds() / 60))
    all_orders = rows(c, "SELECT o.*,a.location,a.active asset_active FROM orders o JOIN assets a ON a.id=o.asset_id ORDER BY o.id")
    orders = {o["id"]: o for o in all_orders}
    requirements = {r["order_id"]: r for r in rows(c, "SELECT * FROM dispatch_requirements")}
    for identifier in selected:
        order = orders.get(identifier)
        if not order:
            raise HTTPException(404, "工单不存在")
        if order["status"] != "CREATED" or order["assignee_id"] is not None:
            raise HTTPException(409, "仅尚未分配的CREATED正式工单可进入新排程")
        if not order["asset_active"]:
            raise HTTPException(409, "工单资产已停用，请复核映射")
        if not order["location"].strip() or "|" in order["location"]:
            raise HTTPException(422, "工单资产须声明明确地点，且地点不可包含|分隔符")
        mappings = rows(c, "SELECT oa.asset_id,oa.installation_id,a.installation_id current_installation,a.active FROM order_assets oa JOIN assets a ON a.id=oa.asset_id WHERE oa.order_id=:i", {"i": identifier})
        if any(not m["active"] or m["installation_id"] != m["current_installation"] for m in mappings):
            raise HTTPException(409, "群组工单资产安装标识已变化，请重新复核")
        r = requirements.get(identifier, {})
        qualifications = sorted(set(obj(r.get("required_qualifications"), [])) | {order["required_skill"]})
        due = offset(r.get("due_at"), horizon, math.floor)
        data["tasks"].append({"id": identifier, "duration": r.get("duration_minutes", 60),
                              "release": max(0, offset(r.get("release_at"), 0)), "due": due,
                              "severity": r.get("severity", "routine"), "qualifications": qualifications,
                              "hard_deadline": bool(r.get("hard_deadline", 0)),
                              "location": order["location"], "tools": obj(r.get("required_tools"), {}),
                              "predecessors": obj(r.get("predecessors"), [])})
        data["order_versions"][str(identifier)] = order["version"]
    data["completed_predecessors"] = [o["id"] for o in all_orders if o["status"] in ("VERIFIED", "CLOSED")]
    latest = {}
    for reservation in rows(c, "SELECT a.* FROM dispatch_assignments a JOIN dispatch_plans p ON p.id=a.plan_id WHERE p.status='CONFIRMED' ORDER BY a.id"):
        latest[reservation["order_id"]] = reservation
    active_by_engineer = {}
    for order in all_orders:
        if order["status"] in ACTIVE and order["assignee_id"]:
            active_by_engineer.setdefault(order["assignee_id"], []).append(order)
    people = {p["user_id"]: p for p in rows(c, "SELECT p.*,u.active,u.role FROM personnel p JOIN users u ON u.id=p.user_id")}
    resource_map = {e["id"]: e for e in resources.get("engineers", [])}
    # Preserve reservations even when the dispatcher omits their engineer or
    # that engineer is now off call; shared tools cannot become double-booked.
    for eid in active_by_engineer:
        if eid not in resource_map:
            resource_map[eid] = {"id": eid, "shifts": [[0, horizon]], "max_minutes": horizon, "home_location": "", "external_reservation": True}
    for resource in resource_map.values():
        person = people.get(resource["id"])
        accept_new = bool(person and person["active"] and person["role"] == "technician" and person["on_call"] and not resource.get("external_reservation"))
        e = {**resource, "qualifications": obj(person["skills"], []) if person else [],
             "can_accept_new": accept_new,
             "max_tasks": person["max_workload"] if person else max(1, len(active_by_engineer.get(resource["id"], []))), "existing_load": 0, "existing_minutes": 0,
             "max_minutes": min(resource["max_minutes"], horizon)}
        data["engineers"].append(e)
        unknown_busy = []
        for order in active_by_engineer.get(e["id"], []):
            reservation = latest.get(order["id"])
            r = requirements.get(order["id"], {})
            if order["status"] in ("RESOLVED", "VERIFIED"):
                e["existing_load"] += 1
                continue
            if not reservation or reservation["engineer_id"] != e["id"]:
                unknown_busy.append(order["id"])
                e["existing_load"] += 1
                data["tool_reservations"].append({"order_id": order["id"], "start": 0, "end": horizon, "tools": obj(r.get("required_tools"), {})})
                continue
            s = offset(reservation["start_at"], 0, math.floor)
            f = offset(reservation["end_at"], 0)
            if f <= 0 or s >= horizon:
                e["existing_load"] += 1
                if f <= 0:
                    unknown_busy.append(order["id"])
                    data["tool_reservations"].append({"order_id": order["id"], "start": 0, "end": horizon, "tools": obj(r.get("required_tools"), {})})
                continue
            start, end = max(0, s), min(horizon, f)
            data["tasks"].append({"id": order["id"], "duration": end - start, "release": start,
                                  "due": end, "severity": "routine", "qualifications": [],
                                  "location": order["location"], "tools": obj(r.get("required_tools"), {}),
                                  "predecessors": [], "locked": {"engineer_id": e["id"], "start": start}})
            if s <= 0:
                e["home_location"] = order["location"]
            elif resource.get("external_reservation") and not e["home_location"]:
                # This person is outside the new-task resource pool. Preserve
                # only their already declared work/tool reservation; do not
                # invent an off-roster journey from an unknown starting point.
                e["home_location"] = order["location"]
        if unknown_busy:
            # V1 work has no declared time interval. Do not guess availability.
            e["can_accept_new"] = False
            data["warnings"].append({"engineer_id": e["id"], "code": "unscheduled_existing_work", "order_ids": unknown_busy})
    if len(data["tasks"]) > 100:
        raise HTTPException(422, "已有任务过多，请缩小排程范围")
    return {"data": data, "source_hash": source_fingerprint(c), "horizon_start": base.isoformat(), "request": request}


def snapshot(c, job):
    plan = one(c, "SELECT * FROM dispatch_plans WHERE job_id=:j", {"j": job["id"]})
    if not plan:
        raise ValueError("Dispatch plan missing")
    saved = obj(plan["input_snapshot"])
    return {**saved, "plan_id": plan["id"], "time_limit_seconds": saved["request"]["time_limit_seconds"]}


def compute(request, cancelled):
    return solve(request["data"], request["time_limit_seconds"], cancelled)


def complete(c, job, result, request):
    stale = source_fingerprint(c) != request["source_hash"]
    status = "STALE" if stale else "DRAFT" if result["status"] in ("optimal", "feasible") else "FAILED"
    result = {**result, "warnings": request["data"].get("warnings", []), "stale": stale}
    execute(c, "UPDATE dispatch_plans SET status=:s,result=:r,updated_at=:t,version=version+1 WHERE id=:i AND status='QUEUED'",
            {"s": status, "r": js(result), "t": now(), "i": request["plan_id"]})
    audit(c, job["created_by"], "dispatch_solved", "dispatch_plan", request["plan_id"], {"status": status, "solver_status": result["status"]})
    return {"plan_id": request["plan_id"], "status": status, "solver_status": result["status"]}


def absolute_time(plan, minute):
    return (_date(plan["horizon_start"]) + timedelta(minutes=minute)).isoformat()
