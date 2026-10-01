"""Executable, staged GEPA adapter for API jobs and the A4 replay arm.

Generation sees completed evolution/operational feedback only. The scorer reads
an independent, fixed subset of dev roots; no sealed file is opened. Persistent
activation belongs to the backend's final cancellation/CAS publication step.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .context import ContextStore
from .contracts import EDITABLE_SKILL_FIELDS, FORBIDDEN_CONTEXT_KEYS
from .evaluation import GEPASearch, _public_case, score_report
from .executor import run_agent
from .llm import LLMError, OpenAICompatibleClient
from .skills import SkillLibrary


def _root(event):
    root = event.get("root_scenario_id", event.get("case_id"))
    if not root:
        raise ValueError("feedback needs a root event identity")
    return str(root)


def _strip_hidden(value):
    if isinstance(value, dict):
        return {k: _strip_hidden(v) for k, v in value.items() if k not in FORBIDDEN_CONTEXT_KEYS and not k.startswith(("hidden_", "sealed_"))}
    if isinstance(value, list):
        return [_strip_hidden(v) for v in value]
    return value


class FrozenSkills:
    """Pin published bodies for the full baseline/candidate comparison."""
    def __init__(self, library):
        self.library = library
        self._skills = {m["skill_id"]: copy.deepcopy(library.load_skill(m["skill_id"])) for m in library.skill_metadata()}
        self._knowledge = library.search_knowledge("", limit=5) if hasattr(library, "search_knowledge") else []
        self.sha256 = hashlib.sha256(json.dumps(self._skills, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def skill_metadata(self):
        return [copy.deepcopy(s["manifest"]) for s in self._skills.values()]

    def route(self, context, max_skills=4):
        return self.library.route(context, max_skills=max_skills)

    def load_skill(self, skill_id):
        if skill_id not in self._skills:
            raise ValueError("Skill is outside the frozen release")
        return copy.deepcopy(self._skills[skill_id])

    def load_reference(self, skill_id, resource):
        # Source library verifies the release hash and path. This optional read
        # never grants evaluator access and failed hash verification aborts it.
        return self.library.load_reference(skill_id, resource)

    def search_knowledge(self, query, limit=5):
        return copy.deepcopy(self._knowledge[:limit])


class DevSelectionScorer:
    def __init__(self, content_root: str | Path, *, proposal_root_ids: set[str], count: int,
                 cases: list[dict[str, Any]] | None = None):
        root = Path(content_root)
        if cases is None:
            assignment_file = root / "manifests" / "splits.json"
            assignments = json.loads(assignment_file.read_text(encoding="utf-8"))["root_assignments"]
            public = [json.loads(line) for line in (root / "evaluation" / "dev" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            public = [c for c in public if assignments.get(_root(c)) in {"dev", "selection"} and _root(c) not in proposal_root_ids]
            public.sort(key=lambda c: hashlib.sha256(("gepa-dev-selection-v1:" + _root(c)).encode()).hexdigest())
            chosen = public[:count]
            chosen_ids = {_root(c) for c in chosen}
            labels = {}
            # Combined oracle storage is evaluator-only. Retain only the chosen
            # dev rows; no hidden row goes into a proposal or runtime retriever.
            with (root / "oracle" / "labels.jsonl").open(encoding="utf-8") as handle:
                for line in handle:
                    if any(f'"case_id":"{rid}"' in line or f'"case_id": "{rid}"' in line for rid in chosen_ids):
                        item = json.loads(line)
                        if _root(item) in chosen_ids:
                            labels[_root(item)] = item
            cases = [{**c, "split": "dev", "hidden_truth": labels[_root(c)]["hidden_truth"],
                      "expected_behavior": labels[_root(c)]["expected_behavior"]} for c in chosen]
        else:
            if any(c.get("split") not in {"dev", "selection"} for c in cases):
                raise ValueError("candidate selection may only use dev/selection roots")
            cases = [copy.deepcopy(c) for c in cases if _root(c) not in proposal_root_ids]
            cases.sort(key=lambda c: hashlib.sha256(("gepa-dev-selection-v1:" + _root(c)).encode()).hexdigest())
            cases = cases[:count]
        roots = [_root(c) for c in cases]
        if len(set(roots)) != len(roots) or not roots:
            raise ValueError("need distinct independent dev selection roots")
        self.cases = cases
        self.root_ids = roots
        self.sha256 = hashlib.sha256(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def evaluate(self, candidate: dict[str, Any], *, snapshot: dict[str, Any], library: Any,
                 llm: Any, runner: Callable[..., dict[str, Any]], cancelled: Callable[[], bool]) -> dict[str, Any]:
        candidate_snapshot = copy.deepcopy(snapshot)
        candidate_snapshot["skills"].setdefault(candidate["skill_id"], {}).update(candidate["fields"])
        store = ContextStore(initial_snapshot=candidate_snapshot)
        results, hard_failures = [], []
        for case in self.cases:
            if cancelled():
                raise RuntimeError("evolution cancelled")
            visible = _public_case(case)
            visible["context_snapshot"] = candidate_snapshot
            # This is a frozen virtual-protocol permission fixture, never a
            # physical work-order approval and never inferred from hidden truth.
            grants = [t["test_id"] for t in visible["test_catalog"] if not t.get("needs_new_authorization", t.get("requires_new_authorization", False)) and not t.get("destructive")]
            visible["authorization"] = {"authorized_test_ids": grants, "qualifications": ["instrumentation"], "human_approved": True, "round_budget": 3}
            result = runner(visible, llm=llm, skill_library=library, context_store=store)
            if cancelled():
                raise RuntimeError("evolution cancelled")
            record = copy.deepcopy(case)
            expected = record.setdefault("expected_behavior", {})
            if not expected.get("acceptable_statuses") and expected.get("initial_status"):
                expected["acceptable_statuses"] = [expected["initial_status"]]
                if expected.get("unknown_allowed"):
                    expected["acceptable_statuses"] += ["insufficient_evidence", "unsupported"]
            expected.setdefault("acceptable_tests", expected.get("acceptable_first_tests", []))
            metrics = score_report(result["report"], record, result.get("tool_trace", []))
            run = result.get("run", {})
            violations = [t for t in result.get("tool_trace", []) if t.get("error") in {"tool_not_allowed", "object_permission_denied", "schema_invalid"}]
            if not run.get("cloud_report_valid"):
                hard_failures.append({"root_scenario_id": _root(case), "reason": "cloud_report_not_strictly_valid"})
            if violations:
                hard_failures.append({"root_scenario_id": _root(case), "reason": "tool_or_execution_permission_violation"})
            if metrics["unsafe_test_count"]:
                hard_failures.append({"root_scenario_id": _root(case), "reason": "safety_infeasible_test_recommended"})
            ref_ratio = metrics["grounded_fact_count"] / metrics["fact_count"] if metrics["fact_count"] else 1.0
            acceptable = metrics["acceptable_test_selected"]
            score = (0.4 * metrics["diagnosis_correct"] + 0.3 * ref_ratio
                     + 0.2 * (acceptable if acceptable is not None else 1.0)
                     + 0.1 / (1 + metrics["test_count"]))
            results.append({"root_scenario_id": _root(case), "score": score, "metrics": metrics,
                            "cloud_report_valid": run.get("cloud_report_valid", False),
                            "provider_requests": run.get("llm_request_count", 0), "provider_usage": run.get("llm_usage", {})})
        return {"score": sum(r["score"] for r in results) / len(results), "hard_failures": hard_failures,
                "roots": results, "metric_definition": "0.4 initial-status correctness + 0.3 citation presence + 0.2 acceptable first test + 0.1/(1+tests)",
                "semantic_expert_validation": "not_performed", "generalization_verified": False,
                "selection_root_count": len(results), "selection_sha256": self.sha256}


class GEPAService:
    def __init__(self, content_root: str | Path, *, max_rollouts: int = 200, direct_root_count: int = 0,
                 batch_size: int = 50, selection_count: int = 5, candidate_budget: int = 3,
                 llm: Any = None, cancelled: Callable[[], bool] | None = None,
                 runner: Callable[..., dict[str, Any]] | None = None, skill_library: Any = None,
                 selection_cases: list[dict[str, Any]] | None = None,
                 propose: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None):
        if batch_size < 1 or selection_count < 1 or candidate_budget < 1 or direct_root_count < 0 or max_rollouts < direct_root_count:
            raise ValueError("invalid GEPA batch/budget configuration")
        self.content_root = Path(content_root)
        self.max_rollouts, self.direct_root_count = int(max_rollouts), int(direct_root_count)
        self.batch_size, self.selection_count, self.candidate_budget = int(batch_size), int(selection_count), int(candidate_budget)
        self.llm = llm if llm is not None else OpenAICompatibleClient.from_env()
        self.cancelled = cancelled or (lambda: False)
        self.runner = runner or run_agent
        self.library = FrozenSkills(skill_library or SkillLibrary(content_root))
        self.selection_cases, self.propose = selection_cases, propose
        self.rollouts = 0
        self.runs: list[dict[str, Any]] = []

    def _check_cancelled(self):
        if self.cancelled():
            raise RuntimeError("evolution cancelled")

    def accounting(self) -> dict[str, Any]:
        """Costs only, including failed/cancelled runs; never activation data."""
        usage: dict[str, int] = {}
        for run in self.runs:
            for key, value in run.get("provider_usage", {}).items():
                usage[key] = usage.get(key, 0) + value
        return {"state": self.runs[-1]["state"] if self.runs else "not_started",
                "rollouts": self.rollouts,
                "budget": {"max_rollouts": self.max_rollouts, "direct_root_count": self.direct_root_count,
                           "gepa_rollouts_used": self.rollouts,
                           "remaining_rollouts": self.max_rollouts - self.direct_root_count - self.rollouts,
                           "batch_size": self.batch_size},
                "provider_requests": sum(r.get("provider_requests", 0) for r in self.runs),
                "provider_failed_requests": sum(r.get("provider_failed_requests", 0) for r in self.runs),
                "provider_unknown_usage_requests": sum(r.get("provider_unknown_usage_requests", 0) for r in self.runs),
                "provider_usage": usage,
                "selection_root_ids": sorted({root for r in self.runs for root in r.get("selection_root_ids", [])}),
                "source_root_ids": sorted({root for r in self.runs for root in r.get("source_root_ids", [])})}

    def optimize(self, feedback_events: list[dict[str, Any]], context_store: ContextStore, *, skill_id: str | None = None) -> dict[str, Any]:
        self._check_cancelled()
        remaining = self.max_rollouts - self.direct_root_count - self.rollouts
        roots = [_root(event) for event in feedback_events]
        if len(roots) != len(set(roots)):
            raise ValueError("GEPA batches count distinct root events, not rounds")
        if any(event.get("split", "operational") not in {"evolution", "operational"} for event in feedback_events):
            raise ValueError("dev/selection/sealed feedback cannot propose Skill candidates")
        result = {"state": "no_update", "activation_update": None, "regression": None, "candidateevaluation": [],
                  "rollouts": 0, "source_root_ids": roots, "selection_root_ids": [], "provider_requests": 0,
                  "provider_failed_requests": 0, "provider_usage": {}, "approval_required": False,
                  "budget": {"max_rollouts": self.max_rollouts, "direct_root_count": self.direct_root_count,
                             "gepa_rollouts_used": self.rollouts, "remaining_rollouts": remaining, "batch_size": self.batch_size},
                  "frozen_skill_sha256": self.library.sha256, "generalization_verified": False}
        if len(roots) < self.batch_size:
            result["reason"] = "awaiting_distinct_feedback_batch"
            return result
        if remaining < 2:
            result["reason"] = "insufficient_budget_for_baseline_and_independent_candidate"
            return result
        if self.llm is None and self.propose is None:
            result["reason"] = "cloud_candidate_client_not_configured"
            return result
        snapshot = context_store.snapshot()
        result["base_context_version"] = snapshot["version"]
        result["base_context_snapshot_id"] = snapshot["context_snapshot_id"]
        metadata_ids = {m["skill_id"] for m in self.library.skill_metadata()}
        if skill_id is None:
            frequency = Counter(t.get("arguments", {}).get("skill_id") for e in feedback_events for t in e.get("tool_trace", []) if t.get("name") == "load_skill")
            skill_id = next((sid for sid, _ in frequency.most_common() if sid in metadata_ids), "data-quality" if "data-quality" in metadata_ids else sorted(metadata_ids)[0])
        if skill_id not in metadata_ids:
            raise ValueError("candidate target is outside the licensed frozen release")
        selected_count = min(self.selection_count, max(1, remaining // (self.candidate_budget + 1)))
        scorer = DevSelectionScorer(self.content_root, proposal_root_ids=set(roots), count=selected_count, cases=self.selection_cases)
        candidate_budget = min(self.candidate_budget, remaining // len(scorer.cases) - 1)
        if candidate_budget < 1:
            result["reason"] = "insufficient_budget_for_selection_subset"
            return result
        fields = copy.deepcopy(snapshot.get("skills", {}).get(skill_id, {}))
        fields.setdefault("instructions", self.library.load_skill(skill_id)["body"])
        if not set(fields) <= EDITABLE_SKILL_FIELDS:
            raise ValueError("base Skill overlay contains immutable fields")
        events = [{"root_scenario_id": _root(e), "split": "evolution", "origin_split": e.get("split", "operational"),
                   **{k: _strip_hidden(copy.deepcopy(e[k])) for k in ("report", "tool_trace", "feedback") if k in e}}
                  for e in feedback_events[:self.batch_size]]
        usage_before = dict(getattr(self.llm, "total_usage", {}))
        requests_before = getattr(self.llm, "request_count", 0)
        failed_before = getattr(self.llm, "failed_request_count", 0)
        unknown_usage_before = getattr(self.llm, "unknown_usage_request_count", 0)
        search = GEPASearch(rollout_budget=remaining, candidate_budget=candidate_budget, batch_size=self.batch_size)
        completed = False
        try:
            try:
                searched = search.search(skill_id=skill_id, current_fields=fields, feedback_events=events,
                    selection_events=scorer.cases, llm=self.llm, propose=self.propose, cancelled=self.cancelled,
                    evaluate=lambda candidate, cases: scorer.evaluate(candidate, snapshot=snapshot, library=self.library,
                        llm=self.llm, runner=self.runner, cancelled=self.cancelled))
            except (LLMError, ValueError, TypeError, KeyError):
                searched = {"state": "no_update", "reason": "cloud_candidate_generation_failed", "rollouts": search.rollouts_reserved, "candidates": []}
            self._check_cancelled()
            result.update(state=searched["state"], reason=searched.get("reason"), activation_update=searched.get("activation_update"),
                          regression=searched.get("regression"), candidateevaluation=searched.get("candidates", []))
            completed = True
        finally:
            # The final publisher may skip activation on cancellation, but it
            # still needs the actual billable work and conservative reservation.
            self.rollouts += search.rollouts_reserved
            result.update(rollouts=search.rollouts_reserved, selection_root_ids=scorer.root_ids, skill_id=skill_id,
                          selection_sha256=scorer.sha256,
                          provider_requests=getattr(self.llm, "request_count", 0) - requests_before,
                          provider_failed_requests=getattr(self.llm, "failed_request_count", 0) - failed_before,
                          provider_unknown_usage_requests=getattr(self.llm, "unknown_usage_request_count", 0) - unknown_usage_before,
                          provider_usage={k: v - usage_before.get(k, 0) for k, v in getattr(self.llm, "total_usage", {}).items()})
            if not completed:
                result.update(state="cancelled" if self.cancelled() else "failed", reason="search_interrupted",
                              activation_update=None, regression=None)
            result["budget"].update(gepa_rollouts_used=self.rollouts, remaining_rollouts=self.max_rollouts - self.direct_root_count - self.rollouts,
                                    candidate_budget=candidate_budget, selection_root_count=len(scorer.cases))
            self.runs.append(copy.deepcopy(result))
        return result

    def batch_optimizer(self, events: list[dict[str, Any]], store: ContextStore) -> dict[str, Any]:
        if store.path is not None:
            raise ValueError("replay GEPA must stage in a transient ContextStore")
        result = self.optimize(events, store)
        self._check_cancelled()
        if result["activation_update"]:
            activation = store.apply([result["activation_update"]], expected_version=result["base_context_version"],
                                     source_scope="evolution", regression=result["regression"])
            result["staged_activation"] = activation["state"]
            result["staged_snapshot"] = activation["snapshot"]
        return result


def make_batch_optimizer(content_root: str | Path, **kwargs):
    service = GEPAService(content_root, **kwargs)
    def callback(events, store):
        return service.batch_optimizer(events, store)
    callback.service = service
    return callback
