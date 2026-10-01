"""The executable GEPA adapter stages changes and protects selection boundaries."""
from __future__ import annotations

import copy
import json

import pytest

from app.agent import ContextStore, GEPAService, ReplayEvaluator, run_agent


class Library:
    def skill_metadata(self):
        return [{"skill_id": "data-quality", "version": "1", "allowed_tools": ["get_signal_evidence"]}]
    def load_skill(self, skill_id):
        assert skill_id == "data-quality"
        return {"manifest": self.skill_metadata()[0], "body": "Retain unknowns and counterevidence."}
    def route(self, context, max_skills=4):
        return self.skill_metadata()


class Client:
    model = "test-only-stub"
    def __init__(self):
        self.request_count, self.failed_request_count = 0, 0
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    def account(self):
        self.request_count += 1
        for key, value in {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}.items():
            self.total_usage[key] += value
    def generate_json(self, messages, schema=None):
        self.account()
        assert "EVAL_SECRET" not in json.dumps(messages)
        return {"candidates": [
            {"candidate_id": "invalid", "skill_id": "data-quality", "fields": {"allowed_tools": ["approve"]}},
            {"candidate_id": "safe", "skill_id": "data-quality", "fields": {"instructions": "Preserve uncertain observations and competing explanations."}, "supporting_root_ids": ["operational-1"]}]}


def visible():
    return {"asset_id": "a", "installation_id": "i", "visible_cutoff": "2026-09-01T12:00:00Z",
            "asset": {"chemistry": "LFP"}, "observations": [{"evidence_id": "e", "summary": "A channel differs from independent readings."}],
            "test_catalog": [{"test_id": "T_CHANNEL_CHECK", "required_qualifications": ["instrumentation"], "distinguishes": ["a", "b"]}]}


def cases():
    return [{"case_id": f"dev-{i}", "root_scenario_id": f"dev-{i}", "split": "dev", "synthetic": True,
             "initial_visible": visible(), "hidden_truth": {"root_cause": "EVAL_SECRET", "requires_inspection": True},
             "expected_behavior": {"initial_status": "insufficient_evidence", "unknown_allowed": True, "acceptable_first_tests": ["T_CHANNEL_CHECK"]}}
            for i in range(2)]


def events():
    return [{"root_scenario_id": "operational-1", "split": "operational", "report": {"status": "insufficient_evidence"},
             "feedback": {"free_text": "Please retain counterevidence", "oracle": "HIDDEN_INPUT"}, "tool_trace": []}]


def runner(payload, *, llm, skill_library, context_store):
    assert "EVAL_SECRET" not in json.dumps(payload)
    if llm is not None:
        llm.account()
    result = run_agent(payload, llm=False, skill_library=skill_library, context_store=context_store)
    result["run"].update(cloud_report_valid=True, execution_mode="test_only_stub", llm_request_count=1)
    return result


def service(tmp_path, **kwargs):
    return GEPAService(tmp_path, max_rollouts=7, direct_root_count=1, batch_size=1, selection_count=2,
                       candidate_budget=2, llm=Client(), runner=runner, skill_library=Library(), selection_cases=cases(), **kwargs)


def test_real_adapter_uses_independent_scorer_and_stages_without_mutating_store(tmp_path):
    store = ContextStore()
    adapter = service(tmp_path)
    result = adapter.optimize(events(), store)
    assert result["state"] == "candidate_ready" and result["rollouts"] == 6
    assert result["budget"]["remaining_rollouts"] == 0
    assert result["candidateevaluation"][1]["state"] == "rejected"
    assert result["activation_update"]["fields"]["instructions"].startswith("Preserve")
    assert result["selection_root_ids"] == adapter.runs[0]["selection_root_ids"]
    assert set(result["selection_root_ids"]).isdisjoint(result["source_root_ids"])
    assert store.snapshot()["version"] == 0
    assert result["provider_requests"] == 5  # one proposer + four actual dev reports; bad candidate reserves budget
    assert result["provider_usage"]["total_tokens"] == 75
    assert result["frozen_skill_sha256"] and result["selection_sha256"]


def test_replay_callback_activates_only_transient_validated_skill(tmp_path):
    store = ContextStore()
    result = service(tmp_path).batch_optimizer(events(), store)
    assert result["staged_activation"] == "active" and store.snapshot()["version"] == 1
    assert store.snapshot()["skills"]["data-quality"]["instructions"].startswith("Preserve")
    with pytest.raises(ValueError, match="transient"):
        service(tmp_path).batch_optimizer(events(), ContextStore(tmp_path / "persisted.json"))


def test_default_batch_and_exhausted_rollout_budget_do_not_call_provider(tmp_path):
    client = Client()
    waiting = GEPAService(tmp_path, llm=client, skill_library=Library(), selection_cases=cases()).optimize(events(), ContextStore())
    assert waiting["reason"] == "awaiting_distinct_feedback_batch" and client.request_count == 0
    exhausted = GEPAService(tmp_path, max_rollouts=1, batch_size=1, llm=client, skill_library=Library(), selection_cases=cases()).optimize(events(), ContextStore())
    assert exhausted["reason"] == "insufficient_budget_for_baseline_and_independent_candidate" and client.request_count == 0


def test_cancel_after_dev_rollout_never_activates(tmp_path):
    flag = {"cancelled": False}
    def cancel_runner(*args, **kwargs):
        result = runner(*args, **kwargs)
        flag["cancelled"] = True
        return result
    adapter = GEPAService(tmp_path, max_rollouts=4, batch_size=1, selection_count=1, candidate_budget=1,
                          llm=Client(), skill_library=Library(), selection_cases=cases(), runner=cancel_runner,
                          cancelled=lambda: flag["cancelled"])
    store = ContextStore()
    with pytest.raises(RuntimeError, match="cancelled"):
        adapter.batch_optimizer(events(), store)
    assert store.snapshot()["version"] == 0


def test_sealed_feedback_and_selection_and_duplicate_roots_are_rejected(tmp_path):
    adapter = service(tmp_path)
    with pytest.raises(ValueError, match="feedback"):
        adapter.optimize([{**events()[0], "split": "sealed"}], ContextStore())
    with pytest.raises(ValueError, match="distinct"):
        adapter.optimize(events() * 2, ContextStore())
    adapter.selection_cases = [{**cases()[0], "split": "sealed"}]
    with pytest.raises(ValueError, match="selection"):
        adapter.optimize(events(), ContextStore())


def test_unrevealed_oracle_feedback_cannot_update_prequential_context():
    case = {"case_id": "evolution-root", "split": "evolution", "initial_visible": visible(), "synthetic": True,
            "hidden_truth": {"unresolved": True}, "feedback": {"free_text": "A future measurement identifies the cause", "evidence_ids": ["future-observation"]}}
    result = ReplayEvaluator().evaluate("A3", [case], llm=False)
    assert result["final_context_snapshot"]["version"] == 0
    assert result["records"][0]["update_reason"] == "feedback_requires_unrevealed_observations"


def test_fixed_context_comparison_can_disable_episodic_updates():
    case = {"case_id": "evolution-root", "split": "evolution", "initial_visible": visible(), "synthetic": True,
            "hidden_truth": {"unresolved": True}, "feedback": {"free_text": "Retain unknowns", "evidence_ids": ["e"]}}
    result = ReplayEvaluator().evaluate("A2", [case], llm=False, allow_context_updates=False)
    assert result["final_context_snapshot"]["version"] == 0 and result["records"][0]["update_state"] == "no_update"
