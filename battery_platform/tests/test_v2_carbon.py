"""Independent mathematical oracles and durable carbon publication/export checks."""
from __future__ import annotations

import itertools
import math
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.carbon.engine import (CarbonInputError, budget_support, operating_npv,
                               pareto_front, renewal_counts, solve_scenario, state_inventory)
from app.carbon.jobs import complete, compute, snapshot
from app.carbon.schemas import CashFlow, Factor, LedgerRequest, PolicyRule, Scenario, StateModel
from app.carbon.storage import add_ledger, content_hash, export_ledger, reverse_ledger
from app.db import execute, insert, js, now, one, rows, tx


def factor(**updates):
    data = {"code": "grid", "version": "golden-1", "value": 0.5, "activity_unit": "kWh",
            "gas_scope": "kgCO2e", "boundary": "use", "source_url": "https://example.org/golden-factor",
            "source_title": "Hand calculation fixture, not an official real-world factor", "jurisdiction": "test-region",
            "valid_from": "2020-01-01", "valid_to": "2100-01-01", "deviation": 0.1,
            "uncertainty_key": "shared-grid", "provenance": "real", "review_status": "verified"}
    data.update(updates)
    return Factor.model_validate(data)


def costs(**updates):
    data = {"initial_cost": 0, "discount_rate": 0, "flows": [{"period": 1, "energy": 20}],
            "price_year": 2026, "quote_reference": "golden calculation only"}
    data.update(updates)
    return data


def scenario(**updates):
    candidate = {"id": "baseline", "label": "baseline", "intervention": "continue",
                 "constraints": dict.fromkeys(("safety", "technical", "service", "personnel", "scenario"), True),
                 "functional_unit_matches": True, "confirmed_by": "human-fixture",
                 "confirmation_reference": "manual golden confirmation", "costs": costs(),
                 "activities": [{"process": "metered_energy", "period": 1, "quantity": 100,
                     "unit": "kWh", "factor_id": 1, "basis": "settled", "provenance": "real",
                     "source_reference": "golden meter record", "source_version": "1"}]}
    other = {**candidate, "id": "candidate", "label": "candidate",
             "activities": [{**candidate["activities"][0], "quantity": 80}], "costs": costs(flows=[{"period": 1, "energy": 15}])}
    data = {"name": "golden-fixture", "version": 1, "functional_unit": {
            "output_kwh_per_period": [50], "start_date": "2026-01-01", "region": "test-region",
            "usage_scenario": "golden unit case", "service_requirements": "provide common 50 kWh",
            "start_state": "existing pack", "terminal_handling": "report remaining state; no permanent avoidance",
            "boundary": ["use"], "gas_scope": "kgCO2e", "baseline_basis": "counterfactual metered fixture"},
            "baseline_id": "baseline", "candidates": [candidate, other], "basis": "settled",
            "provenance": "real", "gamma": 1, "gamma_scan": [0, 0.5, 1], "shadow_price_rmb_per_t": 100}
    data.update(updates)
    return Scenario.model_validate(data)


def state_model(**updates):
    data = {"states": [
        {"name": "old-0", "age_years": 0, "cohort": "existing", "available": True, "efficiency": 0.5, "health": 0.8},
        {"name": "old-1", "age_years": 1, "cohort": "existing", "available": True, "efficiency": 1, "health": 0.7},
        {"name": "old-2", "age_years": 2, "cohort": "existing", "available": True, "efficiency": 1, "health": 0.6},
        {"name": "new-0", "age_years": 0, "cohort": "new", "available": True, "efficiency": 0.8, "health": 1}],
        "initial_distribution": [0.5, 0.5, 0, 0],
        "transitions": [[[0, 0.5, 0, 0.5], [0, 0, 0.75, 0.25], [0, 0, 1, 0], [0, 0, 0, 1]]],
        "replacement_edges": [{"period": 1, "source": 0, "destination": 3}, {"period": 1, "source": 1, "destination": 3}],
        "new_initial_distribution": [0, 0, 0, 1], "energy_factor_id": 1, "replacement_factor_id": 2,
        "rated_capacity_kwh": 4, "parameter_origin": "user_scenario", "parameter_evidence": "explicit synthetic scenario"}
    data.update(updates)
    return StateModel.model_validate(data)


def test_budget_exact_fractional_vertices_and_monotonicity():
    coefficients = {"x": -5, "y": 3, "z": 1}
    previous = -math.inf
    for gamma in (0, 0.5, 1, 1.5, 2, 2.5, 3):
        exhaustive = max(sum(coefficients[k] * v for k, v in zip(coefficients, point))
                         for point in itertools.product((-1, -0.5, 0, 0.5, 1), repeat=3)
                         if sum(abs(x) for x in point) <= gamma)
        actual = budget_support(coefficients, gamma)
        assert actual == exhaustive
        assert actual >= previous
        previous = actual


def test_inventory_shared_error_cancellation_negative_effect_and_gamma_zero():
    s = scenario()
    result = solve_scenario(s, {1: factor()})
    candidate = result["candidates"][1]
    assert candidate["carbon"]["nominal"] == 40
    assert candidate["benefit"]["nominal"] == 10
    assert candidate["benefit"]["lower_under_set"] == 8
    assert candidate["cost"]["realized_cash_npv"] == 0
    assert candidate["shadow_value_rmb"] == 1
    assert result["gamma_scan"][0]["candidates"][1]["carbon_upper"] == 40
    identical = s.model_copy(deep=True)
    identical.candidates[1].activities[0].quantity = 100
    equal = solve_scenario(identical, {1: factor()})["candidates"][1]["benefit"]
    assert equal["nominal"] == equal["lower_under_set"] == equal["upper_under_set"] == 0
    identical.candidates[1].activities[0].quantity = 120
    negative = solve_scenario(identical, {1: factor()})["candidates"][1]["benefit"]
    assert negative["nominal"] == -10
    assert negative["lower_under_set"] == -12
    assert not negative["always_better_under_set"]


@pytest.mark.parametrize("updates,match", [
    ({"activity_unit": "rated_kWh"}, "unit mismatch"),
    ({"gas_scope": "kgCO2"}, "CO2 and CO2e"),
    ({"boundary": "manufacture"}, "outside"),
    ({"jurisdiction": "another-region"}, "geography"),
    ({"valid_to": "2025-01-01"}, "not valid"),
])
def test_refuses_mismatched_factor(updates, match):
    with pytest.raises(CarbonInputError, match=match):
        solve_scenario(scenario(), {1: factor(**updates)})


def test_refuses_missing_source_and_wrong_boundary_and_zero_inventory():
    with pytest.raises(ValidationError):
        factor(source_url="")
    with pytest.raises(ValidationError):
        scenario(claim_type="product_footprint")
    s = scenario()
    s.candidates[0].activities = []
    with pytest.raises(CarbonInputError, match="empty inventory"):
        solve_scenario(s, {1: factor()})


def test_state_expectation_is_expected_inverse_and_new_cohort_reset():
    model = state_model()
    result = state_inventory(model, [100], 1)
    assert result["energy_kwh"] == [150]
    assert result["energy_kwh"][0] != 100 / 0.75
    assert result["replacement_count"] == [0.375]
    assert result["distributions"][-1] == [0, 0.25, 0.375, 0.375]
    assert sum(result["distributions"][-1]) == 1
    assert model.states[0].health == 0.8  # never rewrite the existing SOH
    bad = model.model_copy(deep=True)
    bad.states[3].cohort = "existing"
    with pytest.raises(CarbonInputError, match="new cohort"):
        state_inventory(bad, [100], 1)
    bad = model.model_copy(deep=True)
    bad.transitions[0][0] = [0.5, 0, 0, 0.5]
    with pytest.raises(CarbonInputError, match="advance age"):
        state_inventory(bad, [100], 1)


def test_state_manufacturing_uses_rated_capacity_and_no_aux_duplicate():
    s = scenario(basis="projected")
    s.functional_unit.output_kwh_per_period = [100]
    s.functional_unit.boundary = ["use", "manufacture"]
    s.candidates[0].activities = []
    s.candidates[0].state_model = state_model()
    manufacture = factor(code="manufacture", activity_unit="rated_kWh", boundary="manufacture", value=10, deviation=0)
    result = solve_scenario(s, {1: factor(), 2: manufacture})
    baseline = result["candidates"][0]
    assert baseline["carbon"]["nominal"] == 150 * 0.5 + 0.375 * 4 * 10
    assert baseline["activities"][1]["quantity"] == 1.5
    duplicate = state_model(auxiliary_in_efficiency=True, auxiliary_kwh_per_period=[3])
    with pytest.raises(CarbonInputError, match="double counting"):
        state_inventory(duplicate, [100], 1)


def test_unavailable_service_requires_standby_and_inspection_cannot_heal():
    m = state_model()
    m.replacement_edges = []
    m.new_initial_distribution = None
    m.states[0].available = False
    m.initial_distribution = [1, 0, 0, 0]
    m.transitions = [[[1, 0, 0, 0] for _ in m.states]]
    assert state_inventory(m, [100], 1)["unmet_kwh"] == [100]
    m.standby_efficiency = 0.8
    assert state_inventory(m, [100], 1)["energy_kwh"] == [125]
    m = state_model()
    m.states[1].health = 0.9
    with pytest.raises(CarbonInputError, match="must not improve"):
        state_inventory(m, [100], 1, "inspect")


def test_initial_replacement_generates_manufacture_and_inspection_shares_start():
    m = state_model(initial_distribution=[0, 0, 0, 1], initial_replacement_count=1)
    m.states.append(m.states[3].model_copy(update={"name": "new-1", "age_years": 1, "health": 0.95}))
    m.initial_distribution.append(0)
    m.new_initial_distribution.append(0)
    for row in m.transitions[0]:
        row.append(0)
    m.transitions[0].append([0, 0, 0, 0, 1])
    m.transitions[0][3] = [0, 0, 0, 0, 1]
    computed = state_inventory(m, [100], 1, "replace_pack")
    assert computed["replacement_count"] == [1]
    assert computed["energy_kwh"] == [125]
    m.initial_replacement_count = 0
    with pytest.raises(CarbonInputError, match="initial manufacture"):
        state_inventory(m, [100], 1, "replace_pack")
    s = scenario(basis="projected")
    s.functional_unit.boundary = ["use", "manufacture"]
    for candidate in s.candidates:
        candidate.activities = []
        candidate.state_model = state_model()
    s.candidates[1].intervention = "inspect"
    s.candidates[1].state_model.states[0].health = 0.95
    with pytest.raises(CarbonInputError, match="physical initial state"):
        solve_scenario(s, {1: factor(), 2: factor(code="manufacture", boundary="manufacture", activity_unit="rated_kWh")})


def test_renewal_remaining_and_new_life_are_not_interchangeable():
    # Existing pack fails after 1 period, all subsequent new packs last 2.
    assert renewal_counts([1], [0, 1], 5) == {
        "old": [0, 1, 1, 2, 2, 3], "new": [0, 0, 1, 1, 2, 2]}
    with pytest.raises(CarbonInputError):
        renewal_counts([0.8, 0.5], [1], 5)


def test_cost_npv_shadow_cash_and_policy_cap_are_separate():
    c = CashFlow.model_validate(costs(initial_cost=100, discount_rate=0.1,
        flows=[{"period": 1, "energy": 110}], residual_value=11, residual_basis="terminal resale quote"))
    assert operating_npv(c, 1, 1)["operating_npv"] == pytest.approx(190)
    rule = PolicyRule.model_validate({"rule_id": "golden-rule", "version": "1", "official_url": "https://example.org/golden-policy",
        "jurisdiction": "test-region", "eligible_entity": "test-company", "valid_from": "2020-01-01", "valid_to": "2100-01-01",
        "cap": 7, "required_documents": ["registration", "verification"], "technology_conditions": ["eligible-tech"],
        "effective": True, "review_status": "verified", "provenance": "real"})
    s = scenario()
    data = s.model_dump(mode="json")
    benefit = {"id": "cash-1", "rule_version_id": 1, "period": 1, "amount": 10, "entity": "test-company",
               "documents": {"registration": "registered-project", "verification": "verified-activity"},
               "conditions": {"eligible-tech": True}, "trade_or_grant_reference": "documented grant", "receipt_reference": "actual receipt"}
    data["candidates"][1]["policy_benefits"] = [benefit, {**benefit, "id": "cash-2", "receipt_reference": "second actual receipt"}]
    solved = solve_scenario(Scenario.model_validate(data), {1: factor()}, {1: rule})["candidates"][1]
    assert solved["cost"]["eligible_cash_npv"] == 7
    assert solved["cost"]["realized_cash_npv"] == 7
    assert solved["cost"]["operating_npv"] == 15
    assert solved["cost"]["nominal"] == 8
    assert solved["shadow_value_rmb"] == 1
    data["candidates"][1]["policy_benefits"][0]["documents"] = {}
    data["candidates"][1]["policy_benefits"] = data["candidates"][1]["policy_benefits"][:1]
    unknown = solve_scenario(Scenario.model_validate(data), {1: factor()}, {1: rule})["candidates"][1]
    assert unknown["cost"]["eligible_cash_npv"] == 0
    assert unknown["cost"]["policy_qualification"][0]["cash_status"] == "not_established"


def test_pareto_feasibility_and_exact_sensitivity_switch():
    assert pareto_front([{"id": "a", "cost_nominal": 1, "carbon_nominal": 4},
        {"id": "b", "cost_nominal": 2, "carbon_nominal": 2},
        {"id": "c", "cost_nominal": 3, "carbon_nominal": 4}]) == ["a", "b"]
    s = scenario(epsilon_values=[42])
    solved = solve_scenario(s, {1: factor()})
    source = solved["sensitivity"][0]
    # candidate 40+8*z fits epsilon42 iff z<=0.25
    assert 0.25 in source["breakpoints"]
    assert source["ranking_changes"]
    s.candidates[1].constraints.safety = False
    s.candidates[0].constraints.technical = None
    result = solve_scenario(s, {1: factor()})
    assert result["candidates"][0]["status"] == "insufficient_evidence"
    assert result["candidates"][1]["status"] == "infeasible"
    assert not result["robust_frontier"]


def test_no_model_needed_for_legal_meter_inventory_and_cancel_is_atomic():
    assert solve_scenario(scenario(), {1: factor()})["candidates"][1]["carbon"]["nominal"] == 40
    with pytest.raises(InterruptedError):
        solve_scenario(scenario(), {1: factor()}, cancelled=lambda: True)


def test_client_cannot_turn_soh_or_applicability_flag_into_validated_life_model():
    m = state_model(parameter_origin="validated_model", model_applicable=True)
    with pytest.raises(CarbonInputError, match="adapter is not established"):
        state_inventory(m, [100], 1)


def test_recovery_credit_duplicate_material_flow_is_refused():
    s = scenario()
    a = s.candidates[1].activities[0].model_copy(update={"credit": True, "material_flow_id": "flow-1", "allocation_method": "explicit substitution"})
    s.candidates[1].activities = [a, a]
    with pytest.raises(CarbonInputError, match="multiple recovery credits"):
        solve_scenario(s, {1: factor()})


def _stored_case(s=None, publish=True):
    s = s or scenario()
    with tx() as c:
        actor = one(c, "SELECT id FROM users WHERE username='admin'")["id"]
        f = factor().model_dump(mode="json")
        factor_id = insert(c, "carbon_factors", {"code": "grid", "version": "golden-1", "payload": js(f),
            "content_hash": content_hash(f), "created_by": actor, "created_at": now()})
        for candidate in s.candidates:
            for activity in candidate.activities:
                activity.factor_id = factor_id
        p = s.model_dump(mode="json")
        sid = insert(c, "carbon_scenarios", {"name": s.name, "version": s.version, "payload": js(p),
            "content_hash": content_hash(p), "created_by": actor, "created_at": now()})
        jid = insert(c, "jobs", {"kind": "carbon_solve", "status": "running", "payload": js({"scenario_id": sid, "expected_version": 1}),
            "created_by": actor, "created_at": now(), "idempotency_key": "carbon-golden-job", "request_hash": "golden"})
        job = one(c, "SELECT * FROM jobs WHERE id=:j", {"j": jid})
        request = snapshot(c, job)
    result = compute(request)
    summary = None
    if publish:
        with tx() as c:
            summary = complete(c, job, result, request)
    return job, request, result, summary, actor


def test_snapshot_publication_and_cancelled_job_never_creates_partial_rows():
    job, request, result, summary, actor = _stored_case()
    with tx() as c:
        assert len(rows(c, "SELECT * FROM carbon_activities WHERE result_id=:r", {"r": summary["result_id"]})) == 2
        assert complete(c, job, result, request) == summary
        execute(c, "UPDATE jobs SET cancel_requested=1 WHERE id=:j", {"j": job["id"]})
        with pytest.raises(InterruptedError):
            complete(c, job, result, request)


def test_cancelled_or_restarted_first_solve_never_publishes_result_or_activity():
    job, request, result, _, actor = _stored_case(publish=False)
    with tx() as c:
        execute(c, "UPDATE jobs SET cancel_requested=1 WHERE id=:j", {"j": job["id"]})
        with pytest.raises(InterruptedError):
            complete(c, job, result, request)
        assert rows(c, "SELECT * FROM carbon_results") == []
        assert rows(c, "SELECT * FROM carbon_activities") == []
        execute(c, "UPDATE jobs SET cancel_requested=0,status='interrupted' WHERE id=:j", {"j": job["id"]})
        with pytest.raises(InterruptedError):
            complete(c, job, result, request)
        assert rows(c, "SELECT * FROM carbon_results") == []


def test_gamma_recompute_does_not_book_another_physical_claim():
    job, request, result, summary, actor = _stored_case()
    with tx() as c:
        body = LedgerRequest(result_id=summary["result_id"], candidate_id="candidate", claim_type="comparative_avoided",
                             basis="settled", review_status="reviewed", evidence_reference="verified meter", accounting_period="2026")
        add_ledger(c, body, actor)
        new_id = insert(c, "jobs", {"kind": "carbon_solve", "status": "running", "payload": job["payload"],
            "created_by": actor, "created_at": now(), "idempotency_key": "second-gamma-solve", "request_hash": "second"})
        second = one(c, "SELECT * FROM jobs WHERE id=:i", {"i": new_id})
        repeated = complete(c, second, result, request)
        with pytest.raises(HTTPException, match="already booked"):
            add_ledger(c, body.model_copy(update={"result_id": repeated["result_id"]}), actor)


def test_factor_hash_change_before_publication_is_rejected():
    job, request, result, summary, actor = _stored_case()
    with tx() as c:
        execute(c, "UPDATE carbon_factors SET content_hash='changed' WHERE id=:i", {"i": next(iter(request["factors"]))})
        with pytest.raises(HTTPException, match="immutable factor"):
            complete(c, job, result, request)


def test_ledger_reversals_and_formal_export_filters_synthetic_and_invalid_claims():
    job, request, result, summary, actor = _stored_case()
    body = LedgerRequest(result_id=summary["result_id"], candidate_id="candidate", claim_type="comparative_avoided",
                         basis="settled", review_status="reviewed", evidence_reference="reviewed golden meter evidence", accounting_period="2026")
    with tx() as c:
        entry = add_ledger(c, body, actor)
        assert add_ledger(c, body, actor)["id"] == entry["id"]
        assert export_ledger(c, True)["groups"][0]["emission_kg"] == 10
        correction = reverse_ledger(c, entry["id"], "wrong meter record; preserve original", actor)
        assert correction["emission_kg"] == -10
        assert reverse_ledger(c, entry["id"], "wrong meter record; preserve original", actor)["id"] == correction["id"]
        assert export_ledger(c, True)["groups"][0]["emission_kg"] == 0
        execute(c, "UPDATE carbon_ledger SET emission_kg=1000 WHERE id=:i", {"i": entry["id"]})
        invalid = export_ledger(c, True)
        assert "invalid_calculated_amount" in invalid["excluded"][0]["reasons"]
        assert not invalid["records"]
        execute(c, "UPDATE carbon_ledger SET provenance='synthetic' WHERE result_id=:r", {"r": summary["result_id"]})
        assert not export_ledger(c, True)["records"]
        assert len(export_ledger(c, False)["records"]) == 2


def test_carbon_api_roles_and_job_idempotency(admin, client):
    from conftest import sign_in
    response = admin.post("/api/v2/carbon/factors", json=factor().model_dump(mode="json"))
    assert response.status_code == 201, response.text
    factor_id = response.json()["id"]
    s = scenario()
    for candidate in s.candidates:
        candidate.activities[0].factor_id = factor_id
    response = admin.post("/api/v2/carbon/scenarios", json=s.model_dump(mode="json"))
    assert response.status_code == 201, response.text
    sid = response.json()["id"]
    first = admin.post(f"/api/v2/carbon/scenarios/{sid}/solve", json={"expected_version": 1}, headers={"Idempotency-Key": "carbon-api-1"})
    second = admin.post(f"/api/v2/carbon/scenarios/{sid}/solve", json={"expected_version": 1}, headers={"Idempotency-Key": "carbon-api-1"})
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    sign_in(client, "tech")
    assert client.post("/api/v2/carbon/factors", json=factor(version="golden-2").model_dump(mode="json")).status_code == 403
    assert client.get("/api/v2/carbon/factors").status_code == 200
