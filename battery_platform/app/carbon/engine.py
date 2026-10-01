"""Finite-candidate deterministic accounting and affine budget robustness.

All emissions are physical kg, undiscounted. Currency is RMB, discounted by
elapsed years. Gamma describes an uncertainty budget, never a probability.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta
from typing import Callable

from .schemas import Candidate, Factor, PolicyRule, Scenario, StateModel


class CarbonInputError(ValueError):
    pass


def budget_support(coefficients: dict[str, float], gamma: float) -> float:
    """Exact support of |z_j|<=1, sum |z_j|<=Gamma by sorted coefficients."""
    if not math.isfinite(gamma) or gamma < 0:
        raise CarbonInputError("Gamma must be finite and nonnegative")
    values = sorted((abs(v) for v in coefficients.values()), reverse=True)
    if any(not math.isfinite(v) for v in values):
        raise CarbonInputError("uncertainty coefficients must be finite")
    full = min(int(gamma), len(values))
    return sum(values[:full]) + (
        (gamma - full) * values[full] if full < len(values) else 0
    )


def robust_range(nominal: float, coefficients: dict[str, float], gamma: float) -> dict:
    width = budget_support(coefficients, gamma)
    return {
        "nominal": nominal,
        "lower_under_set": nominal - width,
        "upper_under_set": nominal + width,
        "coefficients": dict(coefficients),
        "gamma": gamma,
        "approximation_error": 0,
        "uncertainty_method": "affine_Bertsimas_Sim_fixed_activity_inventory",
    }


def renewal_counts(old_remaining_pmf: list[float], new_lifetime_pmf: list[float], horizon: int) -> dict:
    """PMFs start at duration 1; missing mass is surviving beyond their support.

    No zero-time renewals. Existing remaining-life and new lifetime stay distinct.
    """
    if not isinstance(horizon, int) or not 0 <= horizon <= 120:
        raise CarbonInputError("renewal horizon must be an integer in 0..120")
    for pmf in (old_remaining_pmf, new_lifetime_pmf):
        if any(not math.isfinite(x) or x < 0 for x in pmf) or sum(pmf) > 1 + 1e-9:
            raise CarbonInputError("lifetime PMF must be nonnegative with total <=1")
    new, old = [0.0] * (horizon + 1), [0.0] * (horizon + 1)
    for h in range(1, horizon + 1):
        new[h] = sum(new_lifetime_pmf[:h]) + sum(
            p * new[h - s] for s, p in enumerate(new_lifetime_pmf[:h], 1)
        )
        old[h] = sum(old_remaining_pmf[:h]) + sum(
            p * new[h - s] for s, p in enumerate(old_remaining_pmf[:h], 1)
        )
    return {"old": old, "new": new}


def _probability(v, label):
    if any(not math.isfinite(x) or x < 0 for x in v) or not math.isclose(sum(v), 1, abs_tol=1e-9):
        raise CarbonInputError(f"{label}: probabilities must be nonnegative and sum to one")


def state_inventory(model: StateModel, output_kwh: list[float], period_years: float,
                    intervention: str = "continue") -> dict:
    states, horizon = model.states, len(output_kwh)
    n = len(states)
    if len(model.initial_distribution) != n or len(model.transitions) != horizon:
        raise CarbonInputError("state dimensions or transition horizon differ from functional unit")
    if len({s.name for s in states}) != n:
        raise CarbonInputError("state names must be unique")
    _probability(model.initial_distribution, "initial distribution")
    if model.parameter_origin == "validated_model":
        raise CarbonInputError("validated-model state adapter is not established: submit explicit user scenarios or measured parameters; a client applicability flag cannot validate lifetime/efficiency")
    if intervention == "repair" and model.parameter_origin not in ("user_scenario", "validated_intervention"):
        raise CarbonInputError("repair effects need explicit scenario inputs or measured intervention evidence")
    auxiliary = model.auxiliary_kwh_per_period or [0.0] * horizon
    if len(auxiliary) != horizon or (model.auxiliary_in_efficiency and any(auxiliary)):
        raise CarbonInputError("auxiliary energy horizon mismatch or double counting in efficiency")
    edges = {(e.period, e.source, e.destination) for e in model.replacement_edges}
    if len(edges) != len(model.replacement_edges):
        raise CarbonInputError("replacement edges are duplicated")
    if any(t > horizon or s >= n or d >= n for t, s, d in edges):
        raise CarbonInputError("replacement edge is outside state dimensions")
    reset = model.new_initial_distribution
    if edges:
        if reset is None or len(reset) != n:
            raise CarbonInputError("replacement requires an independent new-initial distribution")
        _probability(reset, "new initial distribution")
        if any(prob and (state.cohort != "new" or state.age_years != 0) for state, prob in zip(states, reset)):
            raise CarbonInputError("replacement must reset to a new cohort at age zero")
        if model.replacement_factor_id is None:
            raise CarbonInputError("replacement activity requires a manufacturing factor")
    p = list(model.initial_distribution)
    distributions, energy, unmet, replacement = [list(p)], [], [], []
    for t, (demand, matrix) in enumerate(zip(output_kwh, model.transitions), 1):
        if len(matrix) != n or any(len(row) != n for row in matrix):
            raise CarbonInputError("transition matrix must be square")
        for source, row in enumerate(matrix):
            _probability(row, f"transition period {t}, row {source}")
            replacing = sum(prob for destination, prob in enumerate(row) if (t, source, destination) in edges)
            if replacing and any(
                not math.isclose(
                    row[d] if (t, source, d) in edges else 0,
                    replacing * reset[d], abs_tol=1e-9,
                ) for d in range(n)
            ):
                raise CarbonInputError("replacement transitions differ from the independent new-initial distribution")
            for destination, prob in enumerate(row):
                if not prob:
                    continue
                s, d = states[source], states[destination]
                if (t, source, destination) in edges:
                    if not reset[destination]:
                        raise CarbonInputError("replacement destination is not a new-initial state")
                    continue
                # An unavailable absorbing state can persist. Normal operating
                # transitions advance age and cannot silently reset the cohort.
                if p[source] > 1e-12 and d.available and (
                    s.cohort != d.cohort
                    or not math.isclose(d.age_years, s.age_years + period_years, abs_tol=1e-9)
                ):
                    raise CarbonInputError("operating transition must advance age without relabelling an old battery as new")
                if p[source] > 1e-12 and d.health > s.health + 1e-9 and intervention != "repair":
                    raise CarbonInputError("inspection/ordinary ageing must not improve physical health")
        unserved = demand * sum(prob for state, prob in zip(states, p) if not state.available)
        input_energy = sum(prob * demand / state.efficiency for state, prob in zip(states, p) if state.available)
        if model.standby_efficiency is not None:
            input_energy += unserved / model.standby_efficiency
            unserved = 0
        energy.append(input_energy + auxiliary[t - 1])
        unmet.append(unserved)
        replacement.append(sum(p[s] * matrix[s][d] for period, s, d in edges if period == t))
        p = [sum(p[s] * matrix[s][d] for s in range(n)) for d in range(n)]
        _probability(p, f"distribution at period {t}")
        distributions.append(list(p))
    return {
        "energy_kwh": energy, "replacement_count": replacement, "unmet_kwh": unmet,
        "distributions": distributions,
        "terminal_distribution": [{"state": s.model_dump(), "probability": prob} for s, prob in zip(states, p)],
        "terminal_claim": "state at common horizon; deferral is not permanent lifecycle avoidance",
    }


def policy_eligibility(rule: PolicyRule, benefit, scenario: Scenario) -> dict:
    start = scenario.functional_unit.start_date
    when = start + timedelta(days=round(365.2425 * scenario.functional_unit.period_years * benefit.period))
    missing = []
    failures = []
    if rule.jurisdiction != scenario.functional_unit.region:
        failures.append("jurisdiction")
    if benefit.entity != rule.eligible_entity:
        failures.append("entity")
    if not rule.valid_from <= when <= rule.valid_to or not rule.effective:
        failures.append("effective rule/date")
    if rule.review_status != "verified":
        missing.append("verified rule version")
    if rule.provenance == "synthetic" and scenario.provenance != "synthetic":
        failures.append("synthetic policy cannot substantiate real cash")
    for name in rule.technology_conditions:
        v = benefit.conditions.get(name)
        if v is False:
            failures.append(f"condition:{name}")
        elif v is not True:
            missing.append(f"condition:{name}")
    missing.extend(f"document:{name}" for name in rule.required_documents if not benefit.documents.get(name))
    if not benefit.trade_or_grant_reference:
        missing.append("transaction/grant basis")
    if scenario.basis == "settled" and not benefit.receipt_reference:
        missing.append("receipt fact")
    status = "ineligible" if failures else "insufficient_evidence" if missing else "eligible"
    return {
        "id": benefit.id, "rule_id": rule.rule_id, "rule_version": rule.version,
        "eligibility": status, "missing": missing, "failures": failures,
        "cash_status": "established" if status == "eligible" else "not_established",
        "amount": min(benefit.amount, rule.cap) if status == "eligible" else 0,
        "requested_amount": benefit.amount, "capped": benefit.amount > rule.cap,
        "realized": status == "eligible" and scenario.basis == "settled",
        "qualification_scope": "encoded-condition match only; not legal advice or credit issuance",
    }


def operating_npv(costs, horizon: int, period_years: float, energy_kwh=None) -> dict:
    if len({f.period for f in costs.flows}) != len(costs.flows) or any(f.period > horizon for f in costs.flows):
        raise CarbonInputError("cost periods must be unique and within the horizon")
    flows = {f.period: f for f in costs.flows}
    total = costs.initial_cost
    coefficients = defaultdict(float)
    periods = []
    for t in range(1, horizon + 1):
        f = flows.get(t)
        discount = (1 + costs.discount_rate) ** (t * period_years)
        values = {k: getattr(f, k) if f else 0 for k in ("energy", "inspection", "labor", "replacement", "downtime", "other")}
        if costs.energy_price_per_kwh is not None:
            if energy_kwh is None:
                raise CarbonInputError("automatic electricity costs require a state-generated energy inventory")
            if values["energy"]:
                raise CarbonInputError("automatic and manual electricity costs must not be counted twice")
            values["energy"] = energy_kwh[t - 1] * costs.energy_price_per_kwh
            if costs.energy_price_deviation:
                coefficients[costs.energy_price_uncertainty_key] += energy_kwh[t - 1] * costs.energy_price_deviation / discount
        if f:
            for key, value in f.uncertainty_coefficients.items():
                if not key:
                    raise CarbonInputError("cost uncertainty keys must be explicit")
                coefficients[key] += value / discount
        present = sum(values.values()) / discount
        total += present
        periods.append({"period": t, "components": values, "discount_denominator": discount, "present_value": present})
    residual_pv = costs.residual_value / (1 + costs.discount_rate) ** (horizon * period_years)
    return {"operating_npv": total - residual_pv, "coefficients": dict(coefficients), "periods": periods,
            "initial_cost": costs.initial_cost, "residual_present_value": residual_pv,
            "discount_rate": costs.discount_rate, "price_year": costs.price_year, "currency": costs.currency,
            "residual_basis": costs.residual_basis, "quote_reference": costs.quote_reference}


def _validate_factor(activity, factor: Factor, scenario: Scenario):
    unit = scenario.functional_unit
    if activity["unit"] != factor.activity_unit:
        raise CarbonInputError(f"unit mismatch: {activity['unit']} cannot use factor per {factor.activity_unit}")
    if factor.gas_scope != unit.gas_scope:
        raise CarbonInputError("CO2 and CO2e factors cannot be silently combined")
    if factor.boundary not in unit.boundary:
        raise CarbonInputError("factor process boundary is outside this accounting boundary")
    if factor.jurisdiction not in (unit.region, "global"):
        raise CarbonInputError("factor geography does not match the functional unit")
    when = unit.start_date + timedelta(days=round(365.2425 * unit.period_years * (activity["period"] - 1)))
    if not factor.valid_from <= when <= factor.valid_to:
        raise CarbonInputError("factor version is not valid for the activity period")
    if factor.provenance == "synthetic" and scenario.provenance != "synthetic":
        raise CarbonInputError("synthetic factor cannot substantiate real accounting")


def _candidate_inventory(candidate: Candidate, scenario: Scenario, factors: dict[int, Factor]):
    horizon = len(scenario.functional_unit.output_kwh_per_period)
    activities = [a.model_dump(mode="json") for a in candidate.activities]
    state = None
    if candidate.state_model:
        if scenario.basis == "settled":
            raise CarbonInputError("state-predicted future inventory cannot be booked as settled measurements")
        state = state_inventory(candidate.state_model, scenario.functional_unit.output_kwh_per_period,
                                scenario.functional_unit.period_years, candidate.intervention)
        model = candidate.state_model
        # Externally supplied energy/replacement rows could double count generated
        # process inventory. Reject those factor/process overlaps explicitly.
        reserved = {model.energy_factor_id, model.replacement_factor_id}
        if any(a["factor_id"] in reserved for a in activities):
            raise CarbonInputError("manual activities duplicate state-generated electricity/manufacturing factors")
        for period, energy in enumerate(state["energy_kwh"], 1):
            activities.append({"process": "state_service_energy", "period": period, "quantity": energy,
                "unit": "kWh", "factor_id": model.energy_factor_id, "basis": "projected",
                "provenance": "synthetic" if scenario.provenance == "synthetic" else "unverified",
                "source_reference": model.parameter_evidence, "source_version": str(scenario.version),
                "credit": False, "prediction_id": None})
        if model.replacement_factor_id:
            f = factors.get(model.replacement_factor_id)
            if not f or f.activity_unit not in ("battery_unit", "rated_kWh"):
                raise CarbonInputError("replacement manufacturing factor must use battery units or rated capacity")
            if f.activity_unit == "rated_kWh" and model.rated_capacity_kwh is None:
                raise CarbonInputError("capacity manufacturing factor requires rated battery capacity")
            multiplier = model.rated_capacity_kwh if f.activity_unit == "rated_kWh" else 1
            for period, count in enumerate(state["replacement_count"], 1):
                activities.append({"process": "state_replacement_manufacture", "period": period,
                    "quantity": count * multiplier, "unit": f.activity_unit, "factor_id": model.replacement_factor_id,
                    "basis": "projected", "provenance": "synthetic" if scenario.provenance == "synthetic" else "unverified",
                    "source_reference": model.parameter_evidence, "source_version": str(scenario.version),
                    "credit": False, "prediction_id": None})
    nominal = 0.0
    coefficients = defaultdict(float)
    credits = set()
    for a in activities:
        if a["period"] > horizon:
            raise CarbonInputError("activity period exceeds common service horizon")
        if scenario.basis == "settled" and (a["basis"] != "settled" or a["provenance"] == "unverified"):
            raise CarbonInputError("settled accounting requires actual sourced activity records")
        if a["provenance"] == "synthetic" and scenario.provenance != "synthetic":
            raise CarbonInputError("synthetic activity cannot substantiate real accounting")
        factor = factors.get(a["factor_id"])
        if factor is None:
            raise CarbonInputError(f"factor {a['factor_id']} is missing")
        _validate_factor(a, factor, scenario)
        sign = -1 if a.get("credit") else 1
        if a.get("credit"):
            flow = a.get("material_flow_id")
            if flow in credits:
                raise CarbonInputError("the same material flow cannot receive multiple recovery credits")
            credits.add(flow)
        a["emission_kg"] = sign * a["quantity"] * factor.value
        a["factor_snapshot"] = factor.model_dump(mode="json")
        nominal += a["emission_kg"]
        if factor.deviation:
            coefficients[factor.uncertainty_key] += sign * a["quantity"] * factor.deviation
    if not activities:
        raise CarbonInputError("empty inventory cannot substantiate a zero-emission claim")
    return activities, nominal, dict(coefficients), state


def pareto_front(rows: list[dict], cost_key="cost_nominal", carbon_key="carbon_nominal") -> list[str]:
    """Strict dominance; retain equally scoring alternatives with distinct IDs."""
    return [a["id"] for a in rows if not any(
        b[cost_key] <= a[cost_key] and b[carbon_key] <= a[carbon_key]
        and (b[cost_key] < a[cost_key] or b[carbon_key] < a[carbon_key])
        for b in rows
    )]


def epsilon_solutions(rows, epsilons, cost_key="cost_upper", carbon_key="carbon_upper"):
    answers = []
    for epsilon in sorted(set(epsilons)):
        valid = [r for r in rows if r[carbon_key] <= epsilon + 1e-9]
        chosen = min(valid, key=lambda x: (x[cost_key], x[carbon_key], x["id"])) if valid else None
        answers.append({"epsilon_kg": epsilon, "candidate_id": chosen["id"] if chosen else None,
                        "status": "feasible" if chosen else "infeasible",
                        "cost_rmb": chosen[cost_key] if chosen else None})
    return answers


def solve_scenario(scenario: Scenario, factors: dict[int, Factor], rules: dict[int, PolicyRule] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> dict:
    rules = rules or {}
    results = []
    # The uncertainty set is defined before feasibility screening. Unused
    # sources have zero coefficients; retaining them does not add exposure.
    sources = {f.uncertainty_key for f in factors.values() if f.deviation}
    for c in scenario.candidates:
        for flow in c.costs.flows:
            sources.update(flow.uncertainty_coefficients)
        if c.costs.energy_price_deviation:
            sources.add(c.costs.energy_price_uncertainty_key)
    for c in scenario.candidates:
        if cancelled and cancelled():
            raise InterruptedError("carbon solve cancelled before publishing any accounting rows")
        checks = c.constraints.model_dump()
        bad = [name for name, v in checks.items() if v is False]
        unknown = [name for name, v in checks.items() if v is None]
        if c.functional_unit_matches is False:
            bad.append("different functional unit: report independently")
        elif c.functional_unit_matches is None:
            unknown.append("functional-unit equivalence")
        r = {"id": c.id, "label": c.label, "intervention": c.intervention,
             "status": "infeasible" if bad else "insufficient_evidence" if unknown else "feasible",
             "reasons": bad or unknown}
        if bad or unknown:
            results.append(r)
            continue
        activities, nominal, coefs, state = _candidate_inventory(c, scenario, factors)
        if state and any(v > 1e-9 for v in state["unmet_kwh"]):
            r.update(status="infeasible", reasons=["unmet common energy service; no explicit standby service"], terminal_state=state)
            results.append(r)
            continue
        costs = operating_npv(c.costs, len(scenario.functional_unit.output_kwh_per_period),
                              scenario.functional_unit.period_years, state["energy_kwh"] if state else None)
        benefits = []
        ids = [b.id for b in c.policy_benefits]
        embedded = {name for f in c.costs.flows for name in f.embedded_benefit_ids}
        if len(ids) != len(set(ids)) or set(ids) & embedded:
            raise CarbonInputError("policy benefit duplicated or already included in a cost flow")
        eligible_pv = realized_pv = 0
        policy_amounts = defaultdict(float)
        for benefit in c.policy_benefits:
            if benefit.period > len(scenario.functional_unit.output_kwh_per_period):
                raise CarbonInputError("policy cash flow exceeds the service horizon")
            rule = rules.get(benefit.rule_version_id)
            if rule is None:
                raise CarbonInputError("policy rule version is missing")
            eligibility = policy_eligibility(rule, benefit, scenario)
            # Rule cap is per candidate/project across all included periods.
            # Multiple payment rows must not each receive the full project cap.
            remaining = max(0, rule.cap - policy_amounts[benefit.rule_version_id])
            if eligibility["amount"] > remaining:
                eligibility["amount"] = remaining
                eligibility["capped"] = True
            policy_amounts[benefit.rule_version_id] += eligibility["amount"]
            pv = eligibility["amount"] / (1 + c.costs.discount_rate) ** (benefit.period * scenario.functional_unit.period_years)
            eligibility["present_value"] = pv
            eligible_pv += pv
            realized_pv += pv if eligibility["realized"] else 0
            benefits.append(eligibility)
        cost_nominal = costs["operating_npv"] - eligible_pv
        r.update(activities=activities, terminal_state=state, carbon=robust_range(nominal, coefs, scenario.gamma),
                 cost={**costs, **robust_range(cost_nominal, costs["coefficients"], scenario.gamma),
                       "eligible_cash_npv": eligible_pv, "realized_cash_npv": realized_pv,
                       "projected_eligible_cash_npv": eligible_pv - realized_pv, "policy_qualification": benefits,
                       "cash_basis": scenario.basis},
                 carbon_nominal=nominal, cost_nominal=cost_nominal,
                 carbon_upper=nominal + budget_support(coefs, scenario.gamma),
                 cost_upper=cost_nominal + budget_support(costs["coefficients"], scenario.gamma))
        sources.update(coefs)
        sources.update(costs["coefficients"])
        results.append(r)
    if len(sources) > 32:
        raise CarbonInputError("at most 32 shared uncertainty sources are supported per solve")
    if scenario.gamma > len(sources) or any(g > len(sources) for g in scenario.gamma_scan):
        raise CarbonInputError(f"Gamma must be within 0..{len(sources)} shared uncertainty dimensions")
    baseline = next(r for r in results if r["id"] == scenario.baseline_id)
    viable = [r for r in results if r["status"] == "feasible"]
    for r in viable:
        if baseline["status"] != "feasible":
            r["benefit"] = None
            r["operating_savings_npv"] = None
            r["shadow_value_rmb"] = None
            continue
        keys = set(baseline["carbon"]["coefficients"]) | set(r["carbon"]["coefficients"])
        differences = {k: baseline["carbon"]["coefficients"].get(k, 0) - r["carbon"]["coefficients"].get(k, 0) for k in keys}
        benefit = robust_range(baseline["carbon_nominal"] - r["carbon_nominal"], differences, scenario.gamma)
        benefit["always_better_under_set"] = benefit["lower_under_set"] > 0
        benefit["conclusion"] = "positive throughout defined set" if benefit["always_better_under_set"] else "cannot confirm improvement throughout defined set"
        r["benefit"] = benefit
        r["operating_savings_npv"] = baseline["cost"]["operating_npv"] - r["cost"]["operating_npv"]
        r["shadow_value_rmb"] = scenario.shadow_price_rmb_per_t * benefit["nominal"] / 1000
        r["shadow_value_label"] = "internal scenario value, not cash income"
    epsilons = scenario.epsilon_values or [r["carbon_upper"] for r in viable]
    scans = []
    for gamma in sorted(set([0.0, scenario.gamma, *scenario.gamma_scan])):
        if cancelled and cancelled():
            raise InterruptedError("carbon solve cancelled during Gamma scan")
        points = [{**r, "carbon_upper": r["carbon_nominal"] + budget_support(r["carbon"]["coefficients"], gamma),
                   "cost_upper": r["cost_nominal"] + budget_support(r["cost"]["coefficients"], gamma)} for r in viable]
        scans.append({"gamma": gamma, "frontier": pareto_front(points, "cost_upper", "carbon_upper"),
                      "epsilon_solutions": epsilon_solutions(points, epsilons),
                      "candidates": [{k: p[k] for k in ("id", "carbon_upper", "cost_upper")} for p in points]})
    sensitivity = []
    for source in sorted(sources):
        if cancelled and cancelled():
            raise InterruptedError("carbon solve cancelled during sensitivity")
        # The finite affine problem changes only where costs cross or a carbon
        # constraint switches feasibility. Enumerate exact breakpoints, then
        # evaluate the open intervals and the boundary points themselves.
        breaks = {-1.0, 0.0, 1.0}
        for a in viable:
            carbon_slope = a["carbon"]["coefficients"].get(source, 0)
            if carbon_slope:
                for epsilon in epsilons:
                    point = (epsilon - a["carbon_nominal"]) / carbon_slope
                    if -1 <= point <= 1:
                        breaks.add(point)
            for b in viable:
                slope = a["cost"]["coefficients"].get(source, 0) - b["cost"]["coefficients"].get(source, 0)
                if slope:
                    point = (b["cost_nominal"] - a["cost_nominal"]) / slope
                    if -1 <= point <= 1:
                        breaks.add(point)
        breaks = sorted(breaks)
        shifts = sorted(set(breaks + [(a + b) / 2 for a, b in zip(breaks, breaks[1:])]))
        if len(shifts) * len(viable) * len(epsilons) > 200_000:
            sensitivity.append({"source": source, "status": "resource_limit",
                                "reason": "exact switch analysis exceeds bounded sensitivity work budget; narrow epsilon grid"})
            continue
        outcomes = []
        for shift in shifts:
            if cancelled and cancelled():
                raise InterruptedError("carbon solve cancelled during sensitivity intervals")
            points = [{**r, "carbon_nominal": r["carbon_nominal"] + shift * r["carbon"]["coefficients"].get(source, 0),
                       "cost_nominal": r["cost_nominal"] + shift * r["cost"]["coefficients"].get(source, 0)} for r in viable]
            choices = epsilon_solutions(points, epsilons, "cost_nominal", "carbon_nominal")
            outcomes.append({"normalized_shift": shift, "frontier": pareto_front(points), "epsilon_solutions": choices})
        intervals = [{"normalized_from": a, "normalized_to": b, "endpoints_included": False,
                      "epsilon_solutions": next(o["epsilon_solutions"] for o in outcomes if o["normalized_shift"] == (a + b) / 2)}
                     for a, b in zip(breaks, breaks[1:])]
        definitions = [{"factor_id": i, "nominal": f.value, "deviation": f.deviation,
                        "activity_unit": f.activity_unit, "gas_scope": f.gas_scope,
                        "physical_interval": [f.value - f.deviation, f.value + f.deviation]}
                       for i, f in factors.items() if f.uncertainty_key == source and f.deviation]
        sensitivity.append({"source": source, "valid_interval": [-1, 1], "parameter_definitions": definitions,
                            "breakpoints": breaks, "recommendation_intervals": intervals, "outcomes": outcomes,
                            "ranking_changes": len({tuple(x["candidate_id"] for x in o["epsilon_solutions"]) for o in outcomes}) > 1})
    return {
        "functional_unit": scenario.functional_unit.model_dump(mode="json"), "baseline_id": scenario.baseline_id,
        "basis": scenario.basis, "claim_type": scenario.claim_type, "provenance": scenario.provenance,
        "scenario_version": scenario.version, "gamma": scenario.gamma, "uncertainty_sources": sorted(sources),
        "candidates": results, "nominal_frontier": pareto_front(viable),
        "robust_frontier": pareto_front(viable, "cost_upper", "carbon_upper"),
        "epsilon_solutions": epsilon_solutions(viable, epsilons), "gamma_scan": scans,
        "sensitivity": sensitivity,
        "independent_interval_comparison": [{"id": r["id"],
            "carbon_upper": r["carbon_nominal"] + sum(abs(x) for x in r["carbon"]["coefficients"].values()),
            "cost_upper": r["cost_nominal"] + sum(abs(x) for x in r["cost"]["coefficients"].values())} for r in viable],
        "method_limits": ["Gamma is not a confidence level", "affine robustness holds with deterministic fixed activities",
            "nonlinear efficiency/transition uncertainty needs explicit separately labelled input scenarios; not included in Gamma",
            "sensitivity switch intervals are exact only for one affine source at a time with other sources nominal",
            "finite candidate enumeration; no module-combination integer optimization", "settled is not third-party verification"],
    }
