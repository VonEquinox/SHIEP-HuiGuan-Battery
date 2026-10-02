"""Identifiable Memory controls across API, replay and executor boundaries."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from app import api_evolution
from app.agent import ContextStore, ReplayEvaluator, run_agent

CUTOFF = "2026-09-01T12:00:00Z"
MARKER = "IDENTIFIABLE_LEARNED_MEMORY_ONLY"


def memory(mid="existing-memory", root="control-root"):
    return {"memory_id": mid, "version": 1, "scope": {"installation_id": "control-installation", "chemistry": "LFP"},
            "trigger": "inspection", "insight": MARKER, "supporting_case_ids": [root],
            "source_trust": "reported", "source_scope": "operational", "state": "active",
            "available_at": "2026-09-01T10:00:00Z", "counterexamples": []}


def starting_snapshot():
    snapshot = ContextStore().snapshot()
    snapshot["memories"] = [memory()]
    snapshot["changes"] = [{"operation": "ADD", "memory_id": "existing-memory", "item": {"insight": MARKER}}]
    snapshot["skills"] = {"static-skill": {"instructions": "Retain observed evidence and uncertainty."}}
    return snapshot


def visible():
    return {"asset_id": "control-asset", "installation_id": "control-installation", "visible_cutoff": CUTOFF,
            "asset": {"chemistry": "LFP"}, "symptoms": "inspection", "test_catalog": [],
            "observations": [{"evidence_id": "observed", "summary": "The independent check is inconclusive."}],
            "prediction": {"prediction_id": "same-numerical-model", "support": {"status": "insufficient_data"}, "heads": {}}}


def case():
    return {"case_id": "control-root", "root_scenario_id": "control-root", "split": "dev",
            "initial_visible": visible(), "synthetic": True, "hidden_truth": {"unresolved": True},
            "expected_behavior": {"acceptable_statuses": ["insufficient_evidence"]}}


class Library:
    def __init__(self, _root=None, overrides=None):
        self.overrides = overrides or {}

    def with_context_overrides(self, overrides):
        return Library(overrides=copy.deepcopy(overrides))

    def route(self, context, max_skills=4):
        if context.get("memory_enabled") is False:
            assert MARKER not in json.dumps(context)
        return [{"skill_id": "static-skill"}]

    def load_skill(self, skill_id):
        return {"manifest": {"skill_id": skill_id, "allowed_tools": ["search_knowledge", "read_prediction"]},
                "body": "The same static Skill is used in both experimental controls."}

    def search_knowledge(self, query, limit=5):
        return [{"knowledge_id": "same-authorized-knowledge", "text": "Preserve unknowns."}]


class ProbeClient:
    """Attempts a Memory tool call even when it is absent from definitions."""
    model = "test-only-memory-probe"

    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools, **kwargs):
        self.calls += 1
        if self.calls == 1:
            first = json.loads(messages[-1]["content"])
            self.initial = first["context"]
            self.report = first["report_template"]
            self.tool_names = {tool["function"]["name"] for tool in tools}
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "memory-probe", "type": "function", "function": {"name": "search_memory", "arguments": '{"query":"inspection"}'}}]}}]}
        return {"choices": [{"message": {"role": "assistant", "content": json.dumps(self.report)}}]}


def run_probe(payload, *, client, context_store, skill_library=None):
    return run_agent(payload, llm=client, context_store=context_store, skill_library=skill_library or Library(),
                     tools={"search_memory": lambda arguments: [memory("tool-memory", "other-root")]})


@pytest.mark.parametrize("arm", ["A0", "A1"])
def test_no_memory_arm_suppresses_snapshot_history_similarity_and_external_tool(arm):
    snapshot = starting_snapshot()
    captured = []
    client = ProbeClient()

    def runner(payload, **kwargs):
        captured.append(copy.deepcopy(payload))
        assert not kwargs["context_store"].snapshot()["memories"]
        assert MARKER not in json.dumps(payload)
        return run_probe(payload, client=client, context_store=kwargs["context_store"], skill_library=kwargs["skill_library"])

    result = ReplayEvaluator().evaluate(arm, [case()], initial_snapshot=snapshot, skill_library=Library(), runner=runner,
                                       memory_enabled=True, frozen_config={"memory_enabled": True})
    run = result["records"][0]["run"]
    assert captured[0]["context_snapshot"]["skills"] == snapshot["skills"]
    assert not captured[0]["context_snapshot"]["changes"]
    assert result["frozen_config"]["memory_enabled"] is False
    assert run["memory_enabled"] is False
    assert run["initial_memory_ids"] == run["tool_memory_ids"] == run["retrieved_memory_ids"] == run["memory_ids"] == []
    assert run["history_memory_ids"] == [] and run["memory_retrieval_budget"]["unique_retrieved"] == 0
    assert client.initial["memories"] == client.initial["memory_history"] == []
    assert "search_memory" not in client.tool_names
    assert "search_knowledge" in client.tool_names and "read_prediction" in client.tool_names
    assert result["records"][0]["run"]["cloud_report_valid"]
    assert result["final_context_snapshot"] == snapshot


def test_memory_control_retrieves_identifiable_history_and_tool_with_same_static_inputs():
    snapshot = starting_snapshot()
    clients = []

    def runner(payload, **kwargs):
        client = ProbeClient()
        clients.append(client)
        return run_probe(payload, client=client, context_store=kwargs["context_store"], skill_library=kwargs["skill_library"])

    no_memory = ReplayEvaluator().evaluate("A1", [case()], initial_snapshot=snapshot, skill_library=Library(), runner=runner)
    with_memory = ReplayEvaluator().evaluate("A2", [case()], initial_snapshot=snapshot, skill_library=Library(), runner=runner)
    no_client, yes_client = clients
    run = with_memory["records"][0]["run"]
    assert run["initial_memory_ids"] == run["history_memory_ids"] == ["existing-memory"]
    assert run["tool_memory_ids"] == ["tool-memory"]
    assert run["memory_ids"] == ["existing-memory", "tool-memory"]
    assert yes_client.initial["memory_history"][0]["retrieval_mode"] == "event_history"
    assert "search_memory" in yes_client.tool_names
    for field in ("skills", "prediction", "observations", "test_catalog"):
        assert no_client.initial[field] == yes_client.initial[field]
    assert no_memory["final_context_snapshot"] == with_memory["final_context_snapshot"] == snapshot


def test_executor_explicit_no_memory_policy_overrides_populated_payload_and_external_tool():
    snapshot = starting_snapshot()
    payload = {**visible(), "root_scenario_id": "control-root", "context_snapshot": snapshot, "memory_enabled": True,
               "memories": [memory()], "memory_history": [memory()]}
    client = ProbeClient()
    result = run_agent(payload, llm=client, skill_library=Library(), context_store=ContextStore(initial_snapshot=snapshot),
                       memory_enabled=False, tools={"search_memory": lambda arguments: [memory("injected")]})
    assert result["run"]["memory_ids"] == []
    assert result["context_snapshot"]["memories"] == result["context_snapshot"]["changes"] == []
    assert snapshot["memories"][0]["insight"] == MARKER
    trace = [entry for entry in result["tool_trace"] if entry["name"] == "search_memory"]
    assert trace[0]["status"] == "rejected" and trace[0]["error"] == "tool_not_allowed"


def test_no_memory_replay_session_uses_empty_execution_view():
    class Environment:
        def begin(self, case_id):
            return SimpleNamespace(visible={"initial_visible": visible(), "split": "dev"}, completed=[])

        def score(self, session, report):
            return {"label_independent_boundary_check": True}

    snapshot = starting_snapshot()
    client = ProbeClient()
    result = ReplayEvaluator().replay_session("A1", Environment(), "control-root", authorized_test_ids=[],
                                             llm=client, skill_library=Library(), context_store=ContextStore(initial_snapshot=snapshot))
    assert not result["memory_enabled"]
    assert result["rounds"][0]["run"]["memory_ids"] == []
    assert result["context_snapshot"] == snapshot
    assert client.initial["memories"] == client.initial["memory_history"] == []


def test_evolution_api_no_memory_maps_to_explicit_disabled_execution(monkeypatch):
    import app.agent as agent_module
    snapshot = starting_snapshot()
    monkeypatch.setattr(api_evolution, "_evaluation_cases", lambda ids, split: [case()])
    monkeypatch.setattr(agent_module, "SkillLibrary", Library)
    clients = []

    def api_runner(payload, **kwargs):
        client = ProbeClient()
        clients.append(client)
        return run_probe(payload, client=client, context_store=kwargs["context_store"], skill_library=kwargs["skill_library"])

    monkeypatch.setattr(agent_module, "run_agent", api_runner)
    request = {"payload": {"method": "no_memory", "case_ids": ["control-root"], "split": "dev", "base_version": 0, "max_rollouts": 1},
               "base": {"content": json.dumps(snapshot)}}
    result = api_evolution.evolution_compute(request, lambda: False)
    assert result["requested_method"] == "no_memory" and result["frozen_config"]["memory_enabled"] is False
    assert result["records"][0]["run"]["memory_ids"] == []
    assert "search_memory" not in clients[0].tool_names
