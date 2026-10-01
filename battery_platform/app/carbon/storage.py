from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from fastapi import HTTPException
from ..db import audit, execute, insert, js, now, obj, one, rows
from .schemas import Factor, LedgerRequest, PolicyRule, Scenario


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def require(c, table, identifier):
    # Callers provide constant table names.
    found = one(c, f"SELECT * FROM {table} WHERE id=:i", {"i": identifier})
    if not found:
        raise HTTPException(404, f"{table} object not found")
    return found


def public(record):
    return {**record, "payload": obj(record["payload"])}


def referenced_ids(scenario: Scenario):
    factors = {a.factor_id for candidate in scenario.candidates for a in candidate.activities}
    for candidate in scenario.candidates:
        if candidate.state_model:
            factors.add(candidate.state_model.energy_factor_id)
            if candidate.state_model.replacement_factor_id:
                factors.add(candidate.state_model.replacement_factor_id)
    rules = {b.rule_version_id for candidate in scenario.candidates for b in candidate.policy_benefits}
    return sorted(factors), sorted(rules)


def input_snapshot(c, scenario_record, gamma=None):
    scenario = Scenario.model_validate(obj(scenario_record["payload"]))
    if gamma is not None:
        scenario = scenario.model_copy(update={"gamma": gamma})
    factors, rules = referenced_ids(scenario)
    factor_records = {str(i): public(require(c, "carbon_factors", i)) for i in factors}
    rule_records = {str(i): public(require(c, "policy_benefits", i)) for i in rules}
    predictions = {}
    for candidate in scenario.candidates:
        for activity in candidate.activities:
            if not activity.prediction_id:
                continue
            if activity.basis == "settled":
                raise HTTPException(409, "a model-predicted activity cannot be labelled as a settled meter record")
            prediction = require(c, "predictions", activity.prediction_id)
            model = require(c, "models", prediction["model_id"])
            if prediction["applicability"] != "within_observed_range":
                raise HTTPException(409, "activity prediction is outside the model's observed support")
            predictions[str(activity.prediction_id)] = {"prediction": prediction,
                "model_id": model["id"], "artifact_hash": model["artifact_hash"], "model_metadata": obj(model["metadata"])}
        state = candidate.state_model
        if state and state.parameter_origin == "validated_model":
            outputs = []
            for identifier in state.parameter_prediction_output_ids:
                output = require(c, "prediction_outputs", identifier)
                if output["support"] != "supported" or output["head"] not in ("rul", "efficiency", "threshold_risk"):
                    raise HTTPException(409, "unsupported/SOH-only outputs cannot substantiate a life/efficiency transition model")
                outputs.append(output)
            if not outputs or not any(o["head"] == "efficiency" for o in outputs) or not any(o["head"] in ("rul", "threshold_risk") for o in outputs):
                raise HTTPException(409, "validated-model state inputs require supported efficiency and lifetime/risk prediction references")
            raise HTTPException(409, "a registered prediction-to-transition adapter has not been validated for this service; use explicit user-scenario intervals")
    return {"scenario_id": scenario_record["id"], "scenario_version": scenario_record["version"],
            "scenario_content_hash": scenario_record["content_hash"],
            "scenario": scenario.model_dump(mode="json"), "factors": factor_records, "rules": rule_records,
            "numerical_prediction_snapshots": predictions}


def publish_result(c, job, result, request):
    current_job = require(c, "jobs", job["id"])
    if current_job["cancel_requested"] or current_job["status"] != "running":
        raise InterruptedError("carbon job cancelled/interrupted before publication")
    scenario = require(c, "carbon_scenarios", request["scenario_id"])
    if (scenario["version"] != request["scenario_version"]
        or scenario["content_hash"] != request["scenario_content_hash"]
        or content_hash(obj(scenario["payload"])) != request["scenario_content_hash"]):
        raise HTTPException(409, "scenario input version changed during solve")
    for table, key in (("carbon_factors", "factors"), ("policy_benefits", "rules")):
        for identifier, snapshot in request[key].items():
            current = require(c, table, int(identifier))
            if current["content_hash"] != snapshot["content_hash"] or content_hash(obj(current["payload"])) != snapshot["content_hash"]:
                raise HTTPException(409, "immutable factor/policy input changed during solve")
    if previous := one(c, "SELECT id FROM carbon_results WHERE job_id=:j", {"j": job["id"]}):
        return {"result_id": previous["id"], "scenario_id": scenario["id"]}
    result_id = insert(c, "carbon_results", {
        "scenario_id": scenario["id"], "scenario_version": request["scenario_version"],
        "job_id": job["id"], "input_hash": content_hash(request), "input_snapshot": js(request),
        "payload": js(result), "created_by": job["created_by"], "created_at": now(),
    })
    for candidate in result["candidates"]:
        for ordinal, activity in enumerate(candidate.get("activities", [])):
            insert(c, "carbon_activities", {"result_id": result_id, "candidate_id": candidate["id"],
                "ordinal": ordinal, "factor_id": activity["factor_id"], "payload": js(activity)})
    audit(c, job["created_by"], "carbon_solve_complete", "carbon_result", result_id,
          {"input_hash": content_hash(request), "scenario_id": scenario["id"]})
    return {"result_id": result_id, "scenario_id": scenario["id"]}


def _claim(result, candidate_id, claim_type):
    candidate = next((r for r in result["candidates"] if r["id"] == candidate_id), None)
    if not candidate or candidate["status"] != "feasible":
        raise HTTPException(409, "only a feasible calculated candidate can enter the ledger")
    if claim_type == "comparative_avoided":
        if not candidate.get("benefit"):
            raise HTTPException(409, "a valid calculated common-service baseline is required")
        # Keep adverse/negative comparative effects, never truncate to zero.
        return candidate, candidate["benefit"]["nominal"]
    return candidate, candidate["carbon"]["nominal"]


def add_ledger(c, body: LedgerRequest, actor):
    record = require(c, "carbon_results", body.result_id)
    result = obj(record["payload"])
    if body.claim_type != result["claim_type"] or body.basis != result["basis"]:
        raise HTTPException(409, "ledger claim type/basis must match the frozen calculation")
    candidate, amount = _claim(result, body.candidate_id, body.claim_type)
    rows_to_check = list(candidate["activities"])
    if body.claim_type == "comparative_avoided":
        baseline = next(r for r in result["candidates"] if r["id"] == result["baseline_id"])
        rows_to_check += baseline["activities"]
    provenance = result["provenance"]
    if provenance != "synthetic":
        if any(a["provenance"] == "synthetic" or a["factor_snapshot"]["provenance"] == "synthetic" for a in rows_to_check):
            provenance = "synthetic"
        elif any(a["provenance"] != "real" or a["factor_snapshot"]["provenance"] != "real"
                 or a["factor_snapshot"]["review_status"] != "verified" for a in rows_to_check):
            provenance = "unverified"
    if body.basis == "settled" and any(a["basis"] != "settled" for a in rows_to_check):
        raise HTTPException(409, "predicted inventory cannot be silently promoted to settled accounting")
    previous_calculation = one(c, """SELECT l.* FROM carbon_ledger l
        JOIN carbon_results previous ON previous.id=l.result_id
        WHERE previous.scenario_id=:s AND previous.scenario_version=:v
        AND l.candidate_id=:a AND l.claim_type=:k AND l.basis=:b
        AND l.reversal_of IS NULL AND l.result_id<>:r""", {
        "s": record["scenario_id"], "v": record["scenario_version"], "a": body.candidate_id,
        "k": body.claim_type, "b": body.basis, "r": body.result_id})
    if previous_calculation:
        raise HTTPException(409, "the same frozen scenario claim is already booked from another solve; recomputing Gamma cannot create another emission entry")
    if previous := one(c, """SELECT * FROM carbon_ledger WHERE result_id=:r AND candidate_id=:a
            AND claim_type=:k AND basis=:b AND reversal_of IS NULL""", {
            "r": body.result_id, "a": body.candidate_id, "k": body.claim_type, "b": body.basis}):
        if (previous["review_status"], previous["evidence_reference"], previous["accounting_period"]) != (
            body.review_status, body.evidence_reference, body.accounting_period):
            raise HTTPException(409, "ledger entry is immutable; reverse it and calculate a corrected result")
        return previous
    unit = result["functional_unit"]
    boundary = {"processes": sorted(unit["boundary"]), "region": unit["region"],
                "accounting_method": unit["accounting_method"], "boundary_kind": unit["boundary_kind"],
                "manufacturing_history_treatment": unit["manufacturing_history_treatment"]}
    identifier = insert(c, "carbon_ledger", {
        "result_id": body.result_id, "candidate_id": body.candidate_id, "claim_type": body.claim_type,
        "basis": body.basis, "review_status": body.review_status, "provenance": provenance,
        "accounting_period": body.accounting_period,
        "boundary_key": js(boundary), "gas_scope": unit["gas_scope"],
        "emission_kg": amount, "evidence_reference": body.evidence_reference,
        "created_by": actor, "created_at": now(),
    })
    audit(c, actor, "carbon_ledger_add", "carbon_ledger", identifier, {"result_id": body.result_id})
    return require(c, "carbon_ledger", identifier)


def reverse_ledger(c, identifier, reason, actor):
    original = require(c, "carbon_ledger", identifier)
    if original["reversal_of"] is not None:
        raise HTTPException(409, "cannot reverse a correction row")
    if previous := one(c, "SELECT * FROM carbon_ledger WHERE reversal_of=:i", {"i": identifier}):
        if previous["correction_reason"] != reason:
            raise HTTPException(409, "entry already reversed with a different recorded reason")
        return previous
    values = {k: original[k] for k in (
        "result_id", "candidate_id", "claim_type", "basis", "review_status", "provenance",
        "accounting_period", "boundary_key", "gas_scope", "evidence_reference",
    )}
    values.update(emission_kg=-original["emission_kg"], reversal_of=identifier,
                  correction_reason=reason, created_by=actor, created_at=now())
    new_id = insert(c, "carbon_ledger", values)
    audit(c, actor, "carbon_ledger_reverse", "carbon_ledger", new_id, {"reversal_of": identifier, "reason": reason})
    return require(c, "carbon_ledger", new_id)


def export_ledger(c, formal: bool):
    records = rows(c, "SELECT * FROM carbon_ledger ORDER BY id")
    grouped = defaultdict(lambda: {"emission_kg": 0.0, "entry_ids": []})
    included, excluded = [], []
    results = {}
    reversed_ids = {r["reversal_of"] for r in records if r["reversal_of"] is not None}
    active_measurements = {}
    for record in records:
        reasons = []
        if formal:
            if record["provenance"] != "real":
                reasons.append("synthetic_or_unverified_provenance")
            if record["basis"] != "settled":
                reasons.append("projected_inventory")
            if record["review_status"] != "reviewed":
                reasons.append("not_reviewed")
            result = results.setdefault(record["result_id"], obj(require(c, "carbon_results", record["result_id"])["payload"]))
            try:
                candidate, expected = _claim(result, record["candidate_id"], record["claim_type"])
                if record["claim_type"] != result["claim_type"] or record["basis"] != result["basis"]:
                    reasons.append("invalid_claim_basis")
                if record["emission_kg"] != (-expected if record["reversal_of"] else expected):
                    reasons.append("invalid_calculated_amount")
                if record["reversal_of"] is None and record["id"] not in reversed_ids:
                    scope = (record["claim_type"], record["boundary_key"], record["accounting_period"], record["gas_scope"])
                    measurement_ids = {(a["source_reference"], a["source_version"], a["period"], a["process"], a["unit"])
                                       for a in candidate["activities"]}
                    if record["claim_type"] == "comparative_avoided":
                        baseline = next(r for r in result["candidates"] if r["id"] == result["baseline_id"])
                        measurement_ids |= {(a["source_reference"], a["source_version"], a["period"], a["process"], a["unit"])
                                            for a in baseline["activities"]}
                    if any((scope, identity) in active_measurements for identity in measurement_ids):
                        reasons.append("duplicate_actual_activity_claim")
                    elif not reasons:
                        for identity in measurement_ids:
                            active_measurements[(scope, identity)] = record["id"]
            except HTTPException:
                reasons.append("invalid_claim")
            # A reversal can only offset its original within the same report group.
            if record["reversal_of"]:
                original = require(c, "carbon_ledger", record["reversal_of"])
                if any(record[k] != original[k] for k in ("claim_type", "basis", "review_status", "provenance", "accounting_period", "boundary_key", "gas_scope")):
                    reasons.append("invalid_reversal")
                if record["emission_kg"] != -original["emission_kg"]:
                    reasons.append("invalid_reversal_amount")
        if reasons:
            excluded.append({"id": record["id"], "reasons": reasons})
            continue
        included.append(record)
        # Comparative avoidance and own emissions deliberately remain separate.
        key = (record["claim_type"], record["basis"], record["boundary_key"], record["accounting_period"], record["gas_scope"])
        grouped[key]["emission_kg"] += record["emission_kg"]
        grouped[key]["entry_ids"].append(record["id"])
    groups = [{"claim_type": k[0], "basis": k[1], "boundary": obj(k[2], []),
               "accounting_period": k[3], "gas_scope": k[4], **v} for k, v in grouped.items()]
    return {"formal": formal, "groups": groups, "records": included, "excluded": excluded,
            "scope": "reviewed actual activity accounting; does not assert third-party verification or credit eligibility" if formal else "internal report including clearly labelled synthetic/projected records"}
