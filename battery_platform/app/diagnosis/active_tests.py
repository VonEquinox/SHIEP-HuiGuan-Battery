"""One-step expected decision value, explicitly separate from fault prediction.

Likelihoods, loss and cost must be supplied by a versioned task model. When that
model is unavailable the result contains a rule score, never a probability.
"""
from __future__ import annotations

import math
from typing import Any


def _distribution(values: dict[str, float], label: str) -> dict[str, float]:
    if not values or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(float(v)) or float(v) < 0 for v in values.values()):
        raise ValueError(f"{label} must contain finite nonnegative values")
    if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-7):
        raise ValueError(f"{label} must sum to one")
    return {str(k): float(v) for k, v in values.items()}


def posterior(prior: dict[str, float], likelihood: dict[str, float]) -> dict[str, float]:
    p = _distribution(prior, "prior")
    if set(likelihood) != set(p):
        raise ValueError("likelihood hypotheses must match prior")
    weights = {h: p[h] * float(likelihood[h]) for h in p}
    if any(not math.isfinite(v) or not 0 <= float(likelihood[h]) <= 1 for h, v in weights.items()):
        raise ValueError("likelihood must be finite and between zero and one")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("impossible outcome cannot update posterior")
    return {h: v / total for h, v in weights.items()}


def bayes_risk(prior: dict[str, float], loss_matrix: dict[str, dict[str, float]]) -> float:
    p = _distribution(prior, "prior")
    if not loss_matrix:
        raise ValueError("loss matrix needs allowed decisions")
    risks = []
    for losses in loss_matrix.values():
        if set(losses) != set(p) or any(not math.isfinite(float(v)) or float(v) < 0 for v in losses.values()):
            raise ValueError("loss matrix needs finite nonnegative loss for every hypothesis")
        risks.append(sum(p[h] * float(losses[h]) for h in p))
    return min(risks)


def _eligibility(test: dict[str, Any], context: dict[str, Any]) -> list[str]:
    reasons = []
    tid = test.get("test_id", test.get("id"))
    completed = set(context.get("completed_test_ids", []))
    if tid in completed and not test.get("repeat_authorized", False):
        reasons.append("already_completed")
    if test.get("destructive", False) and not context.get("destructive_authorized", False):
        reasons.append("destructive_test_not_authorized")
    required = set(test.get("required_qualifications", test.get("qualifications", [])))
    if test.get("required_skill"):
        required.add(test["required_skill"])
    if not context.get("proposal_only") and not required <= set(context.get("qualifications", [])):
        reasons.append("qualification_missing")
    for key in ("required_capabilities", "required_sop_ids", "required_site_conditions"):
        available = key.removeprefix("required_")
        if not set(test.get(key, [])) <= set(context.get(available, [])):
            reasons.append(f"{available}_missing")
    if test.get("authorized") is False or ("authorized_test_ids" in context and tid not in context["authorized_test_ids"]):
        reasons.append("requires_new_authorization")
    if test.get("requires_new_authorization", test.get("needs_new_authorization", False)):
        reasons.append("requires_new_authorization")
    if float(test.get("duration_minutes", 0)) > float(context.get("remaining_minutes", float("inf"))):
        reasons.append("time_budget_exceeded")
    if not context.get("proposal_only") and int(context.get("round", 1)) > int(context.get("round_budget", 1000000)):
        reasons.append("round_budget_exceeded")
    return sorted(set(reasons))


def rank_tests(tests: list[dict[str, Any]], *, prior: dict[str, float] | None = None,
               loss_matrix: dict[str, dict[str, float]] | None = None,
               context: dict[str, Any] | None = None, likelihood_source: str | None = None) -> dict[str, Any]:
    """Rank legal tests. A test likelihood maps hypothesis -> outcome -> P(y|h,a).

    Failed/out-of-range outcomes are ordinary outcome bins and their probability
    belongs in the model. Correlated repeated tests require a conditional model
    and an explicit repeat authorization; independence is never assumed here.
    """
    context = context or {}
    ranked, excluded, pending = [], [], []
    current_risk = bayes_risk(prior, loss_matrix) if prior is not None and loss_matrix is not None else None
    for test in tests:
        tid = str(test.get("test_id", test.get("id", "")))
        if not tid:
            raise ValueError("test_id required")
        reasons = _eligibility(test, context)
        destination = ranked
        if reasons:
            item = {"test_id": tid, "reasons": reasons}
            if reasons == ["requires_new_authorization"]:
                destination = pending
            else:
                excluded.append(item)
                continue
        cost = float(test.get("test_cost", test.get("cost", test.get("cost_units", 0))))
        duration = float(test.get("duration_minutes", 0))
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("test duration must be finite and nonnegative")
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("test cost must be finite and nonnegative")
        likelihoods = test.get("likelihoods", test.get("likelihood"))
        if current_risk is not None and likelihoods is not None:
            if not likelihood_source:
                raise ValueError("probabilistic test ranking requires a likelihood source/version")
            if set(likelihoods) != set(prior):
                raise ValueError("likelihood model hypotheses differ")
            rows = {h: _distribution(likelihoods[h], f"likelihood:{tid}:{h}") for h in prior}
            outcomes = set(next(iter(rows.values())))
            if any(set(row) != outcomes for row in rows.values()):
                raise ValueError("likelihood outcome bins differ")
            expected_risk, outcome_probabilities = 0.0, {}
            for outcome in sorted(outcomes):
                ly = {h: rows[h][outcome] for h in prior}
                py = sum(prior[h] * ly[h] for h in prior)
                outcome_probabilities[outcome] = py
                if py > 0:
                    expected_risk += py * bayes_risk(posterior(prior, ly), loss_matrix)
            value = current_risk - expected_risk - cost
            destination.append({"test_id": tid, "method": "bayes_voi", "value": value,
                           "current_risk": current_risk, "expected_risk": expected_risk,
                           "test_cost": cost, "outcome_probabilities": outcome_probabilities,
                           "likelihood_source": likelihood_source,
                           "reason": "Expected reduction in decision loss minus defined test cost"})
        else:
            distinguish = len(set(test.get("distinguishes", test.get("applicable_hypotheses", []))))
            score = distinguish / (1.0 + cost + duration / 60)
            destination.append({"test_id": tid, "method": "rule", "rule_score": score, "value": None,
                           "test_cost": cost, "reason": "Defined hypothesis coverage adjusted for cost/time; likelihood unavailable"})
    ranked.sort(key=lambda x: (-(x["value"] if x["value"] is not None else x["rule_score"]), x["test_id"]))
    pending.sort(key=lambda x: (-(x["value"] if x["value"] is not None else x["rule_score"]), x["test_id"]))
    pending = [{**r, "reasons": ["requires_new_authorization"], "execution_eligible": False,
                "required_qualifications": next((t.get("required_qualifications", t.get("qualifications", [])) for t in tests if str(t.get("test_id", t.get("id"))) == r["test_id"]), [])}
               for r in pending if r["value"] is None or r["value"] > 0]
    selected = [r for r in ranked if r["value"] is None or r["value"] > 0]
    if context.get("evidence_sufficient"):
        selected, stop = [], "evidence_sufficient"
    elif context.get("must_transfer"):
        selected, stop = [], "professional_transfer_required"
    elif not selected:
        stop = "authorization_required" if pending else "no_positive_value_or_feasible_test"
    else:
        stop = None
    return {"ranked": ranked, "selected": selected, "excluded": excluded,
            "pending_authorization": pending, "stop_reason": stop,
            "probability_model_available": current_risk is not None}
