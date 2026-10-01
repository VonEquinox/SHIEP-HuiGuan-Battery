"""Agent service boundaries and numerical contracts, independent of cloud availability."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from app.agent import (ContextConflict, ContextStore, GEPASearch, LLMError,
                       OpenAICompatibleClient, ReplayEvaluator, SkillLibrary,
                       ToolError, ToolRegistry, evolve_context, extract_feedback,
                       public_context, run_agent, validate_report)
from app.diagnosis import analyze_groups, posterior, rank_tests, split_group

CUTOFF = "2026-09-01T12:00:00Z"


def payload():
    return {"asset_id": "asset-a", "installation_id": "installation-a", "visible_cutoff": CUTOFF,
            "observations": [{"evidence_id": "ev-now", "installation_id": "installation-a",
                              "measured_at": "2026-09-01T11:00:00Z", "available_at": "2026-09-01T11:30:00Z",
                              "summary": "A channel differs from its independent reference"}],
            "asset": {"chemistry": "LFP"},
            "test_catalog": [{"test_id": "T_CHANNEL_CHECK", "authorized": True,
                              "required_qualifications": ["instrumentation"], "distinguishes": ["sensor_bias", "individual_issue"],
                              "duration_minutes": 15}],
            "authorization": {"authorized_test_ids": ["T_CHANNEL_CHECK"], "qualifications": ["instrumentation"], "round_budget": 3}}


def test_future_availability_identity_and_hidden_fields_are_not_visible():
    p = payload()
    p["observations"] += [
        {"evidence_id": "ev-future", "timestamp": "2026-09-02T00:00:00Z"},
        {"evidence_id": "ev-backdated", "measured_at": "2026-08-30T00:00:00Z", "available_at": "2026-09-03T00:00:00Z"},
        {"evidence_id": "ev-replaced", "installation_id": "installation-old"},
    ]
    p["hidden_truth"] = {"root_cause": "test-secret"}
    p["metadata"] = {"oracle": {"future": "other-secret"}, "branches": [1], "allowed": "ok"}
    safe = public_context(p, cutoff=CUTOFF, installation_id="installation-a")
    assert [o["evidence_id"] for o in safe["observations"]] == ["ev-now"]
    assert "test-secret" not in json.dumps(safe) and "other-secret" not in json.dumps(safe)
    assert safe["metadata"] == {"allowed": "ok"}


def test_model_source_cycle_cutoff_is_separate_from_iso_availability():
    value = {"query": {"query_time": 24.0, "visible_cutoff": 23.0, "feature_max_time": 23.0},
             "observations": [{"timestamp": "2026-09-03T00:00:00Z", "evidence_id": "future"}]}
    result = public_context(value, cutoff=CUTOFF, installation_id="installation-a")
    assert result["query"]["query_time"] == 24 and not result["observations"]
    value["query"]["feature_max_time"] = 24.0
    assert "query" not in public_context(value, cutoff=CUTOFF, installation_id="installation-a")


def test_rule_executor_preserves_unknown_probability_and_next_round():
    r = run_agent(payload(), llm=False)
    assert r["report"]["status"] == "insufficient_evidence"
    assert r["run"]["execution_mode"] == "rule_baseline"
    assert r["run"]["state"] == "WAIT_FOR_MEASUREMENT"
    p = payload()
    p["round"] = 2
    assert run_agent(p, llm=False)["run"]["states"][0]["state"] == "REASSESS"


def test_initial_unapproved_run_proposes_bounded_checks_without_execution_grant():
    p = payload()
    p["authorization"] = {"human_approved": False, "authorized_test_ids": [], "qualifications": [], "round_budget": 0}
    p["test_catalog"][0]["authorized"] = False
    result = run_agent(p, llm=False)
    assert result["report"]["suggested_tests"] == [{"test_id": "T_CHANNEL_CHECK", "reason": "Additional human authorization required within approved procedure catalogue", "authorization": "required"}]
    assert result["report"]["proposal_id"] is None
    ranked = result["tool_trace"][0]["result"]
    assert not ranked["selected"] and not ranked["pending_authorization"][0]["execution_eligible"]


def test_report_rejects_unknown_reference_and_uncalibrated_probability():
    r = run_agent(payload(), llm=False)["report"]
    kwargs = dict(evidence_ids={"ev-now"}, test_ids={"T_CHANNEL_CHECK"}, installation_id="installation-a", cutoff=CUTOFF,
                  authorized_test_ids={"T_CHANNEL_CHECK"})
    r["facts"][0]["evidence_ids"] = ["ev-future"]
    with pytest.raises(ValueError, match="citation"):
        validate_report(r, **kwargs)
    r["facts"][0]["evidence_ids"] = ["ev-now"]
    r["hypotheses"] = [{"code": "sensor_bias", "level": "suspected", "probability": 0.86, "supports": ["ev-now"]}]
    with pytest.raises(ValueError, match="calibrated"):
        validate_report(r, **kwargs)
    r["hypotheses"][0]["probability_source"] = "prediction:1:fault:sensor_bias"
    validate_report(r, probability_authorities={"prediction:1:fault:sensor_bias": 0.86}, **kwargs)


def test_quantitative_assertion_requires_the_cited_value():
    report = run_agent(payload(), llm=False)["report"]
    report["facts"][0]["claim"] = "通道差异为 86 mV"
    with pytest.raises(ValueError, match="quantitative"):
        validate_report(report, evidence_ids={"ev-now"}, test_ids={"T_CHANNEL_CHECK"}, installation_id="installation-a", cutoff=CUTOFF,
                        authorized_test_ids={"T_CHANNEL_CHECK"}, evidence_records={"ev-now": {"value": 42, "unit": "mV"}})


@pytest.mark.parametrize("name", ["approve", "assign", "carbon_solve", "shell", "sql", "http_get"])
def test_service_tool_permissions_are_enforced(name):
    with pytest.raises(ToolError):
        ToolRegistry({name: lambda x: {}}, installation_id="installation-a", cutoff=CUTOFF)
    tools = ToolRegistry({"get_asset_context": lambda x: {"installation_id": x["installation_id"]}}, installation_id="installation-a", cutoff=CUTOFF)
    with pytest.raises(ToolError):
        tools.call(name, {})


def test_tool_identity_schema_hidden_response_and_budget_guard():
    tools = ToolRegistry({"get_asset_context": lambda x: {"installation_id": x["installation_id"], "hidden_truth": "secret"}},
                         installation_id="installation-a", cutoff=CUTOFF, max_calls=2)
    with pytest.raises(ToolError, match="different"):
        tools.call("get_asset_context", {"installation_id": "installation-b"})
    assert tools.call("get_asset_context", {}) == {"installation_id": "installation-a"}
    with pytest.raises(ToolError, match="budget"):
        tools.call("get_asset_context", {})


def test_bayes_voi_matches_hand_calculation_and_includes_failure_outcome():
    prior = {"a": 0.5, "b": 0.5}
    loss = {"act_a": {"a": 0, "b": 10}, "act_b": {"a": 10, "b": 0}}
    tests = [{"test_id": "good", "test_cost": 0.5,
              "likelihoods": {"a": {"yes": 0.8, "no": 0.1, "failed": 0.1}, "b": {"yes": 0.1, "no": 0.8, "failed": 0.1}}},
             {"test_id": "uninformative", "test_cost": 1,
              "likelihoods": {"a": {"yes": 0.5, "no": 0.5}, "b": {"yes": 0.5, "no": 0.5}}}]
    result = rank_tests(tests, prior=prior, loss_matrix=loss, likelihood_source="synthetic-calibrated:v1")
    assert result["ranked"][0]["current_risk"] == 5
    assert result["ranked"][0]["expected_risk"] == pytest.approx(1.5)
    assert result["ranked"][0]["value"] == pytest.approx(3)
    assert [t["test_id"] for t in result["selected"]] == ["good"]
    assert result["ranked"][1]["value"] == -1
    assert posterior(prior, {"a": 0.8, "b": 0.2}) == {"a": 0.8, "b": 0.2}


def test_invalid_probability_models_do_not_silently_normalize():
    with pytest.raises(ValueError, match="sum"):
        posterior({"a": 0.3, "b": 0.3}, {"a": 0.9, "b": 0.1})
    with pytest.raises(ValueError, match="impossible"):
        posterior({"a": 0.5, "b": 0.5}, {"a": 0, "b": 0})


def test_heuristic_has_no_probability_or_fake_voi_and_filters_authorization():
    result = rank_tests([{ "test_id": "allowed", "distinguishes": ["a", "b"]},
                         {"test_id": "restricted", "requires_new_authorization": True},
                         {"test_id": "unsafe", "destructive": True},
                         {"test_id": "completed"}],
                        context={"authorized_test_ids": ["allowed", "unsafe", "completed"], "completed_test_ids": ["completed"]})
    assert result["selected"][0]["value"] is None
    assert result["selected"][0]["method"] == "rule"
    assert "outcome_probabilities" not in result["selected"][0]
    assert {x["test_id"] for x in result["excluded"]} == {"unsafe", "completed"}
    assert result["pending_authorization"][0]["test_id"] == "restricted"


def test_grouping_alignment_comparability_constant_reference_and_split():
    base = {"parent_id": "cabinet", "chemistry": "LFP", "load_condition": "idle", "temperature_condition": "room",
            "timestamps": ["1", "2", "3", "4"], "values": [5, 8, 7, 6], "reference_values": [-1, -0.5, 0, 0.5, 1],
            "topology_origin": "simulated"}
    entities = [{**base, "installation_id": "a"}, {**base, "installation_id": "b", "values": [6, 9, 8, 7]},
                {**base, "installation_id": "constant", "reference_values": [1, 1, 1]},
                {**base, "installation_id": "wrong-domain", "chemistry": "NCM"},
                {**base, "installation_id": "wrong-time", "timestamps": ["5", "6", "7", "8"]}]
    result = analyze_groups(entities)
    assert result["groups"][0]["members"] == ["a", "b"]
    assert result["groups"][0]["causality"] == "not_established"
    assert result["quality_flags"]["constant"]
    children = split_group(result["groups"][0], [["a"], ["b"]], reason="shared sensor and individual issue differ")
    assert all(c["state"] == "requires_individual_reassessment" for c in children)
    with pytest.raises(ValueError):
        split_group(result["groups"][0], [["a"]], reason="incomplete")


def test_feedback_source_spans_and_intervention_label_guards():
    original = {"free_text": "  复核发现采集偏差。仍有单体差异，尚未完成复核。", "author_id": "engineer-7",
                "performed_actions": ["approved repair"], "verification_status": "reported"}
    extracted = extract_feedback(original)
    assert extracted["free_text"] == original["free_text"]
    assert all(original["free_text"][f["span"]["start"]:f["span"]["end"]] == f["source_text"] for f in extracted["candidate_facts"])
    assert all(f["trust"] == "reported" for f in extracted["candidate_facts"])
    assert extracted["label_guards"]["intervention_prevents_false_positive_label"]
    assert extracted["label_guards"]["unfinished_horizon_is_not_false_positive"]


def test_memory_immediate_retrieval_conflicts_and_cas(tmp_path):
    store = ContextStore(tmp_path / "context.json")
    before = store.snapshot()
    feedback = {"feedback_id": "f1", "root_scenario_id": "root1", "installation_id": "installation-a",
                "free_text": "采集偏差仍待复核。", "measured_at": "2026-09-01T11:00:00Z", "split": "evolution"}
    first = evolve_context(store, feedback)
    assert first["state"] == "active"
    assert first["snapshot"]["memories"][0]["source_trust"] == "reported"
    assert store.search("采集", scope={"installation_id": "installation-a"}, cutoff=CUTOFF)
    assert not store.search("采集", scope={"installation_id": "installation-b"}, cutoff=CUTOFF)
    assert store.snapshot(before["context_snapshot_id"]) == before
    with pytest.raises(ContextConflict):
        store.apply([], expected_version=0)
    second = evolve_context(store, {**feedback, "feedback_id": "f2", "free_text": "独立复核未发现采集偏差。", "contradicts_previous": True})
    assert second["snapshot"]["memories"][0]["state"] == "conflicted"
    # A new instance observes persisted state without a long-running write lock.
    assert ContextStore(tmp_path / "context.json").snapshot()["version"] == 2


def test_skill_updates_autoactivate_or_quarantine_and_rollback():
    store = ContextStore()
    malicious = store.apply([{"operation": "SKILL_REVISE", "skill_id": "s", "fields": {"allowed_tools": ["approve"]}}], expected_version=0)
    assert malicious["state"] == "quarantined" and store.snapshot()["version"] == 0
    update = {"operation": "SKILL_REVISE", "skill_id": "s", "fields": {"evidence_checklist": ["retain counterevidence"]}}
    assert store.apply([update], expected_version=0)["state"] == "quarantined"
    result = store.apply([update], expected_version=0, regression={"passed": True, "split": "dev", "hard_failures": []})
    assert result["state"] == "active"
    rolled = store.check_regression({"permission_violations": 1}, expected_version=1)
    assert rolled["state"] == "rolled_back" and store.snapshot()["version"] == 0
    assert store.audit()[-1]["reason"]
    with pytest.raises(ValueError, match="sealed"):
        store.apply([], expected_version=0, source_scope="sealed")


def test_gepa_separate_roots_editable_whitelist_and_failed_budget():
    search = GEPASearch(rollout_budget=6, candidate_budget=3)
    events = [{"root_scenario_id": "e", "split": "evolution", "feedback": {"free_text": "keep missing data unknown"}}]
    selection = [{"root_scenario_id": "d1", "split": "dev"}, {"root_scenario_id": "d2", "split": "dev"}]
    def propose(data):
        assert "hidden_truth" not in json.dumps(data)
        return [{"candidate_id": "bad", "skill_id": "s", "fields": {"allowed_tools": ["approve"]}},
                {"candidate_id": "good", "skill_id": "s", "fields": {"instructions": "retain missing data"}}]
    result = search.search(skill_id="s", current_fields={"instructions": "baseline"}, feedback_events=events,
                           selection_events=selection, propose=propose,
                           evaluate=lambda c, e: {"score": 0.5 if c["candidate_id"] == "baseline" else 0.8, "hard_failures": []})
    assert result["rollouts"] == 6
    assert result["candidates"][1]["state"] == "rejected"
    assert result["chosen"]["candidate"]["candidate_id"] == "good"
    with pytest.raises(ValueError, match="split"):
        search.search(skill_id="s", current_fields={"instructions": "baseline"}, feedback_events=events,
                      selection_events=[{"root_scenario_id": "sealed", "split": "sealed"}], propose=propose, evaluate=lambda c, e: {})


def test_replay_never_leaks_truth_to_runner_or_evolves_selection():
    case = {"case_id": "root1", "split": "dev", "synthetic": True, "initial_visible": payload(),
            "hidden_truth": {"root_cause": "SECRET", "requires_inspection": True}, "oracle": {"branches": "SECRET"},
            "expected_behavior": {"acceptable_statuses": ["insufficient_evidence"]}, "expected_feedback": {"free_text": "SECRET"}}
    def isolated_runner(visible, **kwargs):
        assert "SECRET" not in json.dumps(visible)
        return run_agent(visible, llm=False, context_store=kwargs["context_store"])
    result = ReplayEvaluator().evaluate("A4", [case], runner=isolated_runner)
    assert result["root_count"] == 1 and result["final_context_snapshot"]["version"] == 0
    assert result["metrics"]["diagnosis_accuracy"] == 1
    with pytest.raises(ValueError, match="milestone"):
        ReplayEvaluator().evaluate("A4", [{**case, "split": "sealed"}], runner=isolated_runner)
    sealed = ReplayEvaluator().evaluate("A1", [{**case, "split": "sealed"}], runner=isolated_runner, milestone=True)
    assert not sealed["selection_eligible"]


def test_replay_session_reveals_only_selected_authorized_measurement_then_reassesses():
    class Environment:
        def begin(self, case_id):
            return SimpleNamespace(visible={"initial_visible": payload(), "split": "dev"}, completed=[])
        def authorize(self, session, test_id, approved_by):
            assert test_id == "T_CHANNEL_CHECK" and approved_by == "synthetic_evaluator"
        def reveal(self, session, test_id, result=None):
            session.visible["initial_visible"]["observations"].append({"evidence_id": "ev-revealed", "timestamp": "2026-09-02T12:00:00Z", "summary": "Independent channel recheck remains inconclusive"})
            session.visible["initial_visible"]["visible_cutoff"] = "2026-09-02T12:00:00Z"
            session.completed.append({"test_id": test_id})
            return {"test_id": test_id, "new_evidence": True, "observations": ["ev-revealed"]}
        def score(self, session, report):
            return {"passed": True, "semantic_expert_validation": "not_performed"}
    result = ReplayEvaluator().replay_session("A0", Environment(), "root1", authorized_test_ids=["T_CHANNEL_CHECK"], round_budget=3)
    assert result["root_count"] == 1 and len(result["rounds"]) == 2
    first, second = [r["report"] for r in result["rounds"]]
    assert "ev-revealed" not in first["citations"] and "ev-revealed" in second["citations"]
    assert result["rounds"][1]["run"]["states"][0]["state"] == "REASSESS"
    assert result["rounds"][1]["termination"] == "no_authorized_next_test"


def test_unverified_employee_claim_does_not_confirm_a_root_cause():
    template = run_agent(payload(), llm=False)["report"]
    template.update(status="confirmed", hypotheses=[{"code": "sensor_bias", "level": "confirmed", "supports": ["ev-now"], "probability": None}])
    class Provider:
        def generate_json(self, messages, schema=None):
            return template
    result = run_agent(payload(), llm=Provider())
    assert not result["run"]["cloud_report_valid"]
    assert result["report"]["status"] == "insufficient_evidence"


def test_cloud_client_redacts_errors_and_rejects_malformed_content():
    client = OpenAICompatibleClient(api_key="test-secret-not-real", retries=0,
                                    transport=httpx.MockTransport(lambda req: httpx.Response(401, text="test-secret-not-real")))
    with pytest.raises(LLMError) as raised:
        client.complete([{"role": "user", "content": "test"}])
    assert "test-secret-not-real" not in str(raised.value)
    client = OpenAICompatibleClient(api_key="test-secret-not-real", retries=0,
                                    transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "{broken"}}]})))
    with pytest.raises(LLMError, match="invalid structured"):
        client.generate_json([{"role": "user", "content": "test"}])


def test_configured_cloud_failure_is_explicit_and_not_success():
    class Failed:
        model = "test-model"
        def generate_json(self, messages, schema=None):
            raise LLMError("unavailable")
    result = run_agent(payload(), llm=Failed())
    assert result["run"]["execution_mode"] == "cloud"
    assert result["run"]["status"] == "completed_with_problem_report"
    assert not result["run"]["cloud_report_valid"]
    assert result["report"]["suggested_tests"] == []


def test_cloud_report_cannot_fabricate_proposal_or_change_round():
    template = run_agent(payload(), llm=False)["report"]
    class Malicious:
        def generate_json(self, messages, schema=None):
            return {**template, "proposal_id": "made-up-proposal"}
    result = run_agent(payload(), llm=Malicious())
    assert not result["run"]["cloud_report_valid"]
    assert result["report"]["proposal_id"] is None


def test_skill_metadata_does_not_read_body_until_loading_and_rejects_paths(tmp_path):
    path = tmp_path / "skills" / "sensor"
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps({"skill_id": "sensor", "allowed_tools": ["read_prediction"], "license_status": "approved_synthetic",
                                                  "supported_chemistries": ["LFP"], "route_keywords": ["channel"],
                                                  "references": ["references/evidence.md"]}))
    library = SkillLibrary(tmp_path)
    assert library.route({"chemistry": "LFP", "symptoms": "channel"})[0]["skill_id"] == "sensor"
    assert not library.route({"chemistry": "NCM", "symptoms": "channel"})
    # Initialization/routing succeeded even though no body exists yet.
    (path / "SKILL.md").write_text("Check counterevidence")
    assert library.load_skill("sensor")["body"] == "Check counterevidence"
    with pytest.raises(ValueError, match="unauthorized"):
        library.load_reference("sensor", "../../../oracle/labels.json")
