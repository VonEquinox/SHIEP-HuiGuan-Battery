"""Bounded GEPA-style text search and isolated A0–A4 replay evaluation.

This implements project adapters, not a claim to reproduce upstream algorithms
or establish generalization from a small synthetic smoke run.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Callable

from .context import ContextStore, evolve_context
from .contracts import EDITABLE_SKILL_FIELDS, FORBIDDEN_CONTEXT_KEYS, public_context
from .executor import run_agent, _evidence_ids

ARMS = {
    "A0": {"llm": False, "memory": False, "ace": False, "gepa": False},
    "A1": {"llm": True, "memory": False, "ace": False, "gepa": False},
    "A2": {"llm": True, "memory": True, "ace": False, "gepa": False},
    "A3": {"llm": True, "memory": True, "ace": True, "gepa": False},
    "A4": {"llm": True, "memory": True, "ace": True, "gepa": True},
}


def _root(event: dict[str, Any]) -> str:
    value = event.get("root_scenario_id", event.get("case_id"))
    if not value:
        raise ValueError("evaluation requires a root event ID")
    return str(value)


def _check_events(events: list[dict[str, Any]], scopes: set[str]) -> set[str]:
    roots = set()
    for event in events:
        if event.get("split") not in scopes:
            raise ValueError("event split is not allowed for this evaluation stage")
        root = _root(event)
        if root in roots:
            raise ValueError("count each root event once, not repeated rounds")
        roots.add(root)
    return roots


def validate_skill_candidate(candidate: dict[str, Any], skill_id: str) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    if set(candidate) - {"candidate_id", "skill_id", "fields", "reason", "supporting_root_ids"}:
        raise ValueError("candidate modifies noneditable metadata")
    if candidate.get("skill_id") != skill_id:
        raise ValueError("candidate targets a different Skill")
    fields = candidate.get("fields", {})
    if not fields or not set(fields) <= EDITABLE_SKILL_FIELDS:
        raise ValueError("candidate exceeds editable Skill whitelist")
    if any(not isinstance(v, (str, list)) or len(json.dumps(v)) > 24000 for v in fields.values()):
        raise ValueError("candidate field exceeds type/size budget")
    return copy.deepcopy(candidate)


class GEPASearch:
    def __init__(self, *, rollout_budget: int = 200, candidate_budget: int = 4, batch_size: int = 50):
        self.rollout_budget = max(1, int(rollout_budget))
        self.candidate_budget = max(1, int(candidate_budget))
        self.batch_size = max(1, int(batch_size))

    def search(self, *, skill_id: str, current_fields: dict[str, Any],
               feedback_events: list[dict[str, Any]], selection_events: list[dict[str, Any]],
               evaluate: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
               propose: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
               llm: Any = None, cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
        cancelled = cancelled or (lambda: False)
        if cancelled():
            raise RuntimeError("evolution cancelled")
        feedback_roots = _check_events(feedback_events, {"evolution"})
        selection_roots = _check_events(selection_events, {"selection", "dev"})
        if feedback_roots & selection_roots:
            raise ValueError("proposal and selection root events must be independent")
        if not feedback_events or not selection_events:
            return {"state": "no_update", "reason": "Need separate feedback and selection roots", "rollouts": 0, "candidates": []}
        if not set(current_fields) <= EDITABLE_SKILL_FIELDS:
            raise ValueError("search baseline exceeds editable fields")
        # Only completed, observable trajectories and feedback propose text changes.
        input_events = [{k: copy.deepcopy(e[k]) for k in ("root_scenario_id", "case_id", "split", "report", "tool_trace", "feedback") if k in e}
                        for e in feedback_events[:self.batch_size]]
        proposal_input = {"skill_id": skill_id, "current_fields": current_fields,
                          "feedback_events": input_events, "editable_fields": sorted(EDITABLE_SKILL_FIELDS)}
        if propose:
            candidates = propose(copy.deepcopy(proposal_input))
        elif llm:
            answer = llm.generate_json([{"role": "system", "content": "Propose local battery Skill text changes from observed feedback only. Return JSON {candidates:[{candidate_id,skill_id,fields,reason,supporting_root_ids}]}. Never change permissions, safety rules, splits or labels."},
                                        {"role": "user", "content": json.dumps(proposal_input, ensure_ascii=False)}])
            candidates = answer.get("candidates", [])
        else:
            return {"state": "no_update", "reason": "No candidate proposer configured", "rollouts": 0, "candidates": []}
        if not isinstance(candidates, list):
            raise ValueError("candidate proposal must be an array")
        evaluations, rollouts = [], 0
        baseline_candidate = {"candidate_id": "baseline", "skill_id": skill_id, "fields": current_fields}
        chosen = None
        baseline_score = None
        # Failed candidates consume the same reserved evaluation budget. The
        # evaluator cannot signal a falsely cheap failure by omitting its costs.
        for candidate in [baseline_candidate, *candidates[:self.candidate_budget]]:
            if cancelled():
                raise RuntimeError("evolution cancelled")
            reserved = len(selection_events)
            if rollouts + reserved > self.rollout_budget:
                break
            rollouts += reserved
            try:
                checked = validate_skill_candidate(candidate, skill_id)
                if not set(checked.get("supporting_root_ids", [])) <= feedback_roots:
                    raise ValueError("candidate cites an unavailable proposal root")
                metrics = evaluate(checked, copy.deepcopy(selection_events))
                if cancelled():
                    raise RuntimeError("evolution cancelled")
                score = float(metrics["score"])
                if not math.isfinite(score):
                    raise ValueError("invalid dev score")
                failures = metrics.get("hard_failures", [])
                evaluation = {"candidate": checked, "metrics": metrics, "state": "passed" if not failures else "rejected", "rollouts_reserved": reserved}
                if candidate["candidate_id"] == "baseline":
                    baseline_score = score
                    if failures:
                        baseline_score = None
                elif not failures and baseline_score is not None and score >= baseline_score and (chosen is None or score > chosen["metrics"]["score"]):
                    chosen = evaluation
            except Exception:
                if cancelled():
                    raise RuntimeError("evolution cancelled") from None
                evaluation = {"candidate_id": candidate.get("candidate_id", "invalid") if isinstance(candidate, dict) else "invalid", "state": "rejected", "reason": "candidate schema/evaluation failed", "rollouts_reserved": reserved}
            evaluations.append(evaluation)
        return {"state": "candidate_ready" if chosen else "no_update", "chosen": chosen,
                "candidates": evaluations, "rollouts": rollouts, "rollout_budget": self.rollout_budget,
                "proposal_root_count": len(feedback_roots), "selection_root_count": len(selection_roots),
                "split": "dev", "generalization_verified": False,
                "activation_update": None if not chosen else {"operation": "SKILL_REVISE", "skill_id": skill_id, "fields": chosen["candidate"]["fields"]},
                "regression": None if not chosen else {"passed": True, "hard_failures": [], "split": "dev", "metrics": chosen["metrics"]}}


def _public_case(case: dict[str, Any]) -> dict[str, Any]:
    source = copy.deepcopy(case.get("visible_state", case.get("initial_visible", {})))
    if isinstance(source, list):
        source = {"observations": source}
    asset = case.get("asset", case.get("asset_context", case.get("entity", {})))
    source.setdefault("asset", asset)
    source.setdefault("asset_id", case.get("asset_id", asset.get("asset_id", "replay-asset")))
    source.setdefault("installation_id", case.get("installation_id", asset.get("installation_id", "replay-installation")))
    source.setdefault("visible_cutoff", source.get("cutoff", case.get("visible_cutoff", case.get("cutoff", "2026-01-01T00:00:00Z"))))
    if source.get("asset_context") and not source.get("asset"):
        source["asset"] = source["asset_context"]
    source.setdefault("test_catalog", case.get("test_catalog", []))
    source.setdefault("authorization", case.get("authorization", {}))
    source.setdefault("round", 1)
    return public_context(source, cutoff=source["visible_cutoff"], installation_id=source["installation_id"])


def score_report(report: dict[str, Any], case: dict[str, Any], tool_trace: list[dict[str, Any]]) -> dict[str, Any]:
    """Program scoring belongs to the evaluator, never the executing Agent."""
    expected = case.get("expected_behavior", {})
    truth = case.get("hidden_truth", {})
    truth_codes = set(truth.get("confirmed_hypotheses", truth.get("hypotheses", [])))
    if truth.get("root_cause"):
        truth_codes.add(str(truth["root_cause"]))
    predicted = {h["code"] for h in report.get("hypotheses", []) if h["level"] in {"confirmed", "suspected"}}
    allowed_statuses = set(expected.get("acceptable_statuses", []))
    status_correct = report.get("status") in allowed_statuses if allowed_statuses else report.get("status") in {"insufficient_evidence", "unsupported"} if truth.get("unresolved") else bool(predicted & truth_codes)
    facts = report.get("facts", [])
    grounded = sum(bool(f.get("evidence_ids")) for f in facts)
    selected = {t["test_id"] for t in report.get("suggested_tests", [])}
    acceptable_tests = set(expected.get("acceptable_tests", case.get("oracle", {}).get("acceptable_tests", [])))
    forbidden_tests = set(expected.get("safety_infeasible_tests", case.get("oracle", {}).get("safety_infeasible_tests", [])))
    legal_calls = sum(t.get("status") == "rejected" for t in tool_trace)
    # Open-set/unresolved is a valid outcome. This does not count an uninspected
    # root as a true negative without its independent label.
    independently_labeled = bool(truth.get("independently_labeled", case.get("origin") == "synthetic" or case.get("synthetic")))
    requires_inspection = truth.get("requires_inspection")
    alerted = report.get("priority", {}).get("class") in {"needs_inspection", "urgent_review"}
    return {"diagnosis_correct": int(status_correct), "fact_count": len(facts), "grounded_fact_count": grounded,
            "test_count": len(selected), "acceptable_test_selected": int(bool(selected & acceptable_tests)) if acceptable_tests else None,
            "unsafe_test_count": len(selected & forbidden_tests), "tool_rejection_count": legal_calls,
            "missed": int(not alerted and requires_inspection) if independently_labeled and requires_inspection is not None else None,
            "false_alarm": int(alerted and not requires_inspection) if independently_labeled and requires_inspection is not None else None,
            "label_provenance": "independent_replay_truth" if independently_labeled else "insufficient_for_miss_estimation"}


class ReplayEvaluator:
    """Evaluates one root once. Hidden branches remain in this evaluator only.

    Each arm receives the same frozen input and starting context. Only evolution
    feedback is applied *after* its report is frozen. Sealed outputs are marked
    selection-ineligible and are never supplied to memory/candidate callbacks.
    """
    def evaluate(self, arm: str, cases: list[dict[str, Any]], *, llm: Any = None,
                 skill_library: Any = None, initial_snapshot: dict[str, Any] | None = None,
                 runner: Callable[..., dict[str, Any]] = run_agent,
                 frozen_config: dict[str, Any] | None = None, milestone: bool = False,
                 batch_optimizer: Callable[[list[dict[str, Any]], ContextStore], Any] | None = None,
                 batch_size: int = 50, replay_environment: Any = None,
                 replay_authorized_test_ids: list[str] | None = None,
                 allow_context_updates: bool = True) -> dict[str, Any]:
        if arm not in ARMS:
            raise ValueError("unknown experiment arm")
        roots = _check_events(cases, {"dev", "selection", "evolution", "sealed"})
        sealed = any(c["split"] == "sealed" for c in cases)
        if sealed and (not milestone or any(c["split"] != "sealed" for c in cases)):
            raise ValueError("sealed evaluation requires an isolated predefined milestone")
        if sealed and batch_optimizer:
            raise ValueError("sealed results cannot be passed to an optimizer")
        store = ContextStore(initial_snapshot=initial_snapshot)
        frozen = copy.deepcopy(frozen_config or {})
        config_digest = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
        records, feedback_batch = [], []
        for case in cases:
            visible = _public_case(case)
            replay_session = None
            if case["split"] == "evolution" and replay_environment is not None:
                if not replay_authorized_test_ids:
                    raise ValueError("branch replay requires explicit frozen virtual test grants")
                replay_session = replay_environment.begin(_root(case))
                visible = _public_case(replay_session.visible)
                visible["authorization"] = {"authorized_test_ids": replay_authorized_test_ids,
                                            "qualifications": ["instrumentation"], "round_budget": 3, "human_approved": True}
            visible["context_snapshot"] = store.snapshot()
            result = runner(visible, llm=(llm if ARMS[arm]["llm"] else False),
                            skill_library=(skill_library if arm != "A0" else None), context_store=store)
            report = copy.deepcopy(result["report"])
            metrics = score_report(report, case, result.get("tool_trace", []))
            record = {"root_scenario_id": _root(case), "split": case["split"], "report": report,
                      "context_snapshot_id": result.get("run", {}).get("context_snapshot_id"),
                      "metrics": metrics, "run": result.get("run", {}), "update_state": "no_update"}
            # Dev/selection are read-only, avoiding order-dependent tuning of the
            # set used to compare candidates. Sealed labels never leave scorer.
            if case["split"] == "evolution" and ARMS[arm]["memory"] and allow_context_updates:
                feedback = copy.deepcopy(case.get("feedback", case.get("expected_feedback", {})))
                if replay_session is not None:
                    eligible_tests = [t["test_id"] for t in report.get("suggested_tests", []) if t["authorization"] == "authorized" and t["test_id"] in replay_authorized_test_ids]
                    if eligible_tests:
                        chosen_test = eligible_tests[0]
                        replay_environment.authorize(replay_session, chosen_test, approved_by="synthetic_evaluator")
                        try:
                            record["revealed"] = replay_environment.reveal(replay_session, chosen_test)
                        except (PermissionError, ValueError):
                            record["replay_boundary_error"] = "selected_branch_not_reachable"
                    reachable_feedback = replay_environment.visible_feedback(replay_session)
                    feedback = copy.deepcopy(reachable_feedback[0]) if reachable_feedback else {}
                elif not set(feedback.get("evidence_ids", [])) <= _evidence_ids(visible):
                    feedback = {}
                    record["update_reason"] = "feedback_requires_unrevealed_observations"
                if not feedback:
                    records.append(record)
                    continue
                feedback.update(root_scenario_id=_root(case), split="evolution", installation_id=visible["installation_id"])
                feedback.setdefault("available_at", feedback.get("observed_at", visible["visible_cutoff"]))
                if ARMS[arm]["ace"]:
                    updated = evolve_context(store, feedback, report)
                else:
                    # Reflexion-style episodic memory retains the concrete error
                    # and correction; it performs no Skill text revision.
                    mid = "episode-" + _root(case)
                    updated = store.apply([{"operation": "ADD", "memory_id": mid, "item": {
                        "insight": str(feedback.get("free_text", "Unresolved inspection episode")),
                        "trigger": "inspection episode", "scope": {"installation_id": visible["installation_id"]},
                        "supporting_case_ids": [_root(case)], "source_trust": "reported",
                        "origin": "synthetic_replay", "available_at": visible["visible_cutoff"]}}],
                        expected_version=store.snapshot()["version"], source_scope="evolution")
                record["update_state"] = updated["state"]
                feedback_batch.append({"root_scenario_id": _root(case), "split": "evolution", "report": report,
                                       "tool_trace": result.get("tool_trace", []), "feedback": feedback})
                if ARMS[arm]["gepa"] and batch_optimizer and len(feedback_batch) >= batch_size:
                    record["gepa_result"] = batch_optimizer(copy.deepcopy(feedback_batch), store)
                    feedback_batch = []
            records.append(record)
        labeled = [r for r in records if r["metrics"]["missed"] is not None]
        facts = sum(r["metrics"]["fact_count"] for r in records)
        return {"arm": arm, "label": "synthetic/replay diagnosis experiment", "root_count": len(roots),
                "records": records, "frozen_config": frozen, "frozen_config_sha256": config_digest,
                "selection_eligible": not sealed, "generalization_verified": False,
                "metrics": {"diagnosis_accuracy": sum(r["metrics"]["diagnosis_correct"] for r in records) / len(records) if records else None,
                            "grounded_assertion_ratio": sum(r["metrics"]["grounded_fact_count"] for r in records) / facts if facts else None,
                            "mean_test_count": sum(r["metrics"]["test_count"] for r in records) / len(records) if records else None,
                            "unsafe_test_count": sum(r["metrics"]["unsafe_test_count"] for r in records),
                            "independently_labeled_root_count": len(labeled),
                            "misses": sum(r["metrics"]["missed"] for r in labeled) if labeled else None,
                            "false_alarms": sum(r["metrics"]["false_alarm"] for r in labeled) if labeled else None},
                "final_context_snapshot": store.snapshot(),
                "context_changes": [update for entry in store.audit() if entry.get("state") == "active" for update in entry.get("updates", [])]}

    def replay_session(self, arm: str, environment: Any, case_id: str, *,
                       authorized_test_ids: list[str], llm: Any = None, skill_library: Any = None,
                       context_store: ContextStore | None = None, round_budget: int = 3,
                       milestone: bool = False, selected_outcomes: dict[str, str] | None = None) -> dict[str, Any]:
        """Bridge to evaluator-only branch environments with explicit test grants.

        The executor gets only environment.visible; it receives no reference to
        the environment, hidden lookup tables or future branch selectors. Round
        reports are grouped under a single root event, never independent scores.
        """
        if arm not in ARMS or not 1 <= round_budget <= 20:
            raise ValueError("invalid arm or round budget")
        session = environment.begin(case_id)
        split = session.visible.get("split", session.visible.get("split_tags", {}).get("split", "dev"))
        if split == "sealed" and not milestone:
            raise ValueError("sealed replay requires a predefined isolated milestone")
        store = context_store or ContextStore()
        rounds, seen_feedback, history = [], set(), []
        for number in range(1, round_budget + 1):
            visible = _public_case(session.visible)
            visible["round"] = number
            visible["authorization"] = {**visible.get("authorization", {}), "authorized_test_ids": authorized_test_ids,
                                         "qualifications": ["instrumentation"], "round_budget": round_budget}
            visible["completed_test_ids"] = [r["test_id"] for r in session.completed]
            visible["previous_reports"] = copy.deepcopy(history[-3:])
            visible["context_snapshot"] = store.snapshot()
            result = run_agent(visible, llm=llm if ARMS[arm]["llm"] else False,
                               skill_library=skill_library if arm != "A0" else None, context_store=store)
            frozen_report = copy.deepcopy(result["report"])
            history.append(frozen_report)
            entry = {"round": number, "report": frozen_report, "run": result["run"], "tool_trace": result["tool_trace"]}
            candidates = [t for t in frozen_report["suggested_tests"] if t["authorization"] == "authorized" and t["test_id"] in authorized_test_ids]
            if not candidates:
                entry["termination"] = "no_authorized_next_test"
                rounds.append(entry)
                break
            chosen = candidates[0]["test_id"]
            environment.authorize(session, chosen, approved_by="synthetic_evaluator")
            try:
                revealed = environment.reveal(session, chosen, result=(selected_outcomes or {}).get(chosen))
            except (PermissionError, ValueError):
                entry["termination"] = "selected_branch_not_reachable"
                rounds.append(entry)
                break
            entry["revealed"] = revealed
            if split == "evolution" and ARMS[arm]["memory"]:
                for feedback in environment.visible_feedback(session):
                    fid = feedback.get("feedback_id")
                    if fid in seen_feedback:
                        continue
                    seen_feedback.add(fid)
                    feedback = {**feedback, "root_scenario_id": case_id, "installation_id": visible["installation_id"],
                                "split": "evolution", "available_at": feedback.get("observed_at", visible["visible_cutoff"])}
                    if ARMS[arm]["ace"]:
                        updated = evolve_context(store, feedback, frozen_report)
                    else:
                        updated = store.apply([{"operation": "ADD", "memory_id": f"episode-{case_id}-{fid}", "item": {
                            "insight": feedback.get("free_text", "Unresolved inspection episode"),
                            "trigger": "inspection episode", "scope": {"installation_id": visible["installation_id"]},
                            "supporting_case_ids": [case_id], "source_trust": "reported",
                            "origin": "synthetic_replay", "available_at": feedback["available_at"]}}],
                            expected_version=store.snapshot()["version"], source_scope="evolution")
                    entry.setdefault("feedback_updates", []).append({"feedback_id": fid, "state": updated["state"]})
            rounds.append(entry)
            if not revealed.get("new_evidence"):
                entry["termination"] = "no_new_evidence"
                break
        return {"arm": arm, "root_scenario_id": case_id, "root_count": 1, "split": split,
                "rounds": rounds, "selection_eligible": split != "sealed",
                "generalization_verified": False, "semantic_expert_validation": "not_performed",
                "environment_checks": environment.score(session, history[-1]) if history else None,
                "context_snapshot": store.snapshot()}
