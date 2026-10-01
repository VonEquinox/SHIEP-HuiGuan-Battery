from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from .db import audit, insert, js, now, obj, rows, tx
from .jobs import enqueue
from .security import allow, current_user
from .carbon.schemas import Factor, LedgerRequest, PolicyRule, ReversalRequest, Scenario, SolveRequest
from .carbon.storage import (add_ledger, content_hash, export_ledger, input_snapshot,
                             public, require, reverse_ledger)

router = APIRouter(prefix="/api/v2/carbon", tags=["independent-carbon"])
WRITERS = ("admin", "researcher")


@router.get("/factors")
def factors(user=Depends(current_user)):
    with tx() as c:
        return [public(r) for r in rows(c, "SELECT * FROM carbon_factors ORDER BY id DESC")]


@router.post("/factors", status_code=201)
def create_factor(body: Factor, user=Depends(allow(*WRITERS))):
    if body.review_status == "verified" and user["role"] != "admin":
        raise HTTPException(403, "only administrator can record factor-source verification")
    payload = body.model_dump(mode="json")
    with tx() as c:
        identifier = insert(c, "carbon_factors", {"code": body.code, "version": body.version,
            "payload": js(payload), "content_hash": content_hash(payload), "created_by": user["id"], "created_at": now()})
        audit(c, user["id"], "carbon_factor_version_create", "carbon_factor", identifier)
        return public(require(c, "carbon_factors", identifier))


@router.get("/policy-benefits")
def rules(user=Depends(current_user)):
    with tx() as c:
        return [public(r) for r in rows(c, "SELECT * FROM policy_benefits ORDER BY id DESC")]


@router.post("/policy-benefits", status_code=201)
def create_rule(body: PolicyRule, user=Depends(allow("admin"))):
    payload = body.model_dump(mode="json")
    with tx() as c:
        identifier = insert(c, "policy_benefits", {"rule_id": body.rule_id, "version": body.version,
            "payload": js(payload), "content_hash": content_hash(payload), "created_by": user["id"], "created_at": now()})
        audit(c, user["id"], "carbon_policy_version_create", "policy_benefit", identifier)
        return public(require(c, "policy_benefits", identifier))


@router.get("/scenarios")
def scenarios(user=Depends(current_user)):
    with tx() as c:
        return [public(r) for r in rows(c, "SELECT * FROM carbon_scenarios ORDER BY id DESC")]


@router.post("/scenarios", status_code=201)
def create_scenario(body: Scenario, user=Depends(allow(*WRITERS))):
    payload = body.model_dump(mode="json")
    with tx() as c:
        # Validate references at admission. All calculation validation runs in the
        # worker, outside the SQLite writer lock, and can refuse the solve.
        input_snapshot(c, {"id": 0, "version": body.version, "content_hash": content_hash(payload), "payload": js(payload)})
        if body.parent_scenario_id is not None:
            parent = require(c, "carbon_scenarios", body.parent_scenario_id)
            if body.version != parent["version"] + 1:
                raise HTTPException(409, "a new scenario revision must increment the parent version")
        identifier = insert(c, "carbon_scenarios", {"name": body.name, "version": body.version,
            "payload": js(payload), "content_hash": content_hash(payload), "created_by": user["id"], "created_at": now()})
        audit(c, user["id"], "carbon_scenario_create", "carbon_scenario", identifier)
        return public(require(c, "carbon_scenarios", identifier))


@router.get("/scenarios/{identifier}")
def scenario(identifier: int, user=Depends(current_user)):
    with tx() as c:
        r = public(require(c, "carbon_scenarios", identifier))
        r["results"] = rows(c, "SELECT id,job_id,scenario_version,created_at FROM carbon_results WHERE scenario_id=:i ORDER BY id DESC", {"i": identifier})
        return r


@router.post("/scenarios/{identifier}/solve", status_code=202)
def solve(identifier: int, body: SolveRequest, request: Request, user=Depends(allow(*WRITERS))):
    with tx() as c:
        s = require(c, "carbon_scenarios", identifier)
        if s["version"] != body.expected_version:
            raise HTTPException(409, "scenario version conflict; refresh before solving")
        job_id = enqueue(c, "carbon_solve", {"scenario_id": identifier, **body.model_dump()},
                         user, request.headers.get("Idempotency-Key", ""))
        return {"job_id": job_id, "scenario_id": identifier}


@router.get("/results/{identifier}")
def result(identifier: int, user=Depends(current_user)):
    with tx() as c:
        record = require(c, "carbon_results", identifier)
        return {k: v for k, v in record.items() if k not in ("payload", "input_snapshot")} | {
            "result": obj(record["payload"]), "input_snapshot": obj(record["input_snapshot"])}


@router.get("/ledger")
def ledger(user=Depends(current_user)):
    with tx() as c:
        return rows(c, "SELECT * FROM carbon_ledger ORDER BY id DESC")


@router.post("/ledger", status_code=201)
def create_ledger(body: LedgerRequest, user=Depends(allow(*WRITERS))):
    if body.review_status == "reviewed" and user["role"] != "admin":
        raise HTTPException(403, "only administrator can record a carbon review")
    with tx() as c:
        return add_ledger(c, body, user["id"])


@router.post("/ledger/{identifier}/reverse", status_code=201)
def reversal(identifier: int, body: ReversalRequest, user=Depends(allow("admin"))):
    with tx() as c:
        return reverse_ledger(c, identifier, body.reason, user["id"])


@router.get("/exports")
def export(formal: bool = Query(True), user=Depends(current_user)):
    with tx() as c:
        return export_ledger(c, formal)
