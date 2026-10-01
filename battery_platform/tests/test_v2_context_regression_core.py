"""Post-publication Context comparison using handmade dev cases and stubs only."""
from __future__ import annotations

import copy
import json

import httpx
import pytest

from app.agent import ContextStore, OpenAICompatibleClient, run_agent
from app.agent.regression import ContextRegressionService


class Library:
    def skill_metadata(self):
        return [{"skill_id": name, "version": "1", "allowed_tools": ["get_signal_evidence"]}
                for name in ("data-quality", "temperature")]

    def load_skill(self, skill_id):
        assert skill_id in {"data-quality", "temperature"}
        return {"manifest": next(m for m in self.skill_metadata() if m["skill_id"] == skill_id),
                "body": "Preserve uncertainty and counterevidence."}

    def route(self, context, max_skills=4):
        return self.skill_metadata()[:max_skills]


def cases():
    return [{"case_id": f"manual-dev-{i}", "root_scenario_id": f"manual-dev-{i}", "split": "dev",
             "synthetic": True, "hidden_truth": {"root_cause": "HANDMADE_EVALUATOR_SECRET"},
             "expected_behavior": {"initial_status": "insufficient_evidence"},
             "initial_visible": {"asset_id": "a", "installation_id": "i", "visible_cutoff": "2026-09-01T12:00:00Z",
                 "asset": {"chemistry": "LFP"}, "symptoms": "inspection", "test_catalog": [],
                 "observations": [{"evidence_id": "reading", "summary": "Independent readings disagree."}]}}
            for i in range(3)]


def memory(**changes):
    return {"memory_id": "m", "version": 1, "scope": {"chemistry": "LFP", "protocol_id": None},
            "trigger": "inspection", "insight": "Preserve uncertain source reports.", "supporting_case_ids": ["operational-source"],
            "counterexamples": [], "source_trust": "reported", "source_scope": "operational", "state": "active",
            "available_at": "2026-09-01T10:00:00Z", "helpful_count": 0, "harmful_count": 0,
            "last_used": None, "expires_at": None, **changes}


def snapshots():
    previous = ContextStore().snapshot()
    previous["skills"] = {"data-quality": {}, "temperature": {"evidence_checklist": ["retain alternatives"]}}
    current = copy.deepcopy(previous)
    current.update(version=1, context_version="context_v1", context_snapshot_id="new-snapshot")
    current["memories"] = [memory()]
    return current, previous


class Client:
    model = "handmade-test-stub"

    def __init__(self, transform=None):
        self.request_count = self.failed_request_count = self.unknown_usage_request_count = 0
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.inputs = []
        self.transform = transform

    def generate_json(self, messages, schema=None):
        self.request_count += 1
        self.total_usage["prompt_tokens"] += 10
        self.total_usage["completion_tokens"] += 5
        self.total_usage["total_tokens"] += 15
        assert "HANDMADE_EVALUATOR_SECRET" not in json.dumps(messages)
        payload = json.loads(messages[-1]["content"])
        self.inputs.append(copy.deepcopy(payload))
        report = payload["report_template"]
        return self.transform(report, payload["context"]) if self.transform else report


def service(tmp_path, **kwargs):
    options = {"llm": Client(), "selection_count": 2, "rollout_budget": 4,
               "skill_library": Library(), "selection_cases": cases()}
    options.update(kwargs)
    return ContextRegressionService(tmp_path, **options)


def test_full_context_comparison_preserves_both_overlays_and_never_mutates_snapshots(tmp_path):
    current, previous = snapshots()
    original = copy.deepcopy((current, previous))
    client = Client()
    adapter = service(tmp_path, llm=client)
    result = adapter.check(current, previous, source_root_ids=["operational-source"])
    assert result["state"] == "passed" and result["reason"] == "independent_dev_floor_preserved"
    assert result["rollouts"] == 4 and result["provider_requests"] == 4
    assert result["provider_usage"]["total_tokens"] == 60 and result["provider_unknown_usage_requests"] == 0
    assert result["previous_metrics"]["score"] == result["current_metrics"]["score"]
    assert result["selection_sha256"] == result["current_metrics"]["selection_sha256"] == result["previous_metrics"]["selection_sha256"]
    assert set(result["selection_root_ids"]).isdisjoint(result["source_root_ids"])
    for payload in client.inputs:
        skills = {item["manifest"]["skill_id"]: item for item in payload["context"]["skills"]}
        assert skills["temperature"]["context_overrides"] == {"evidence_checklist": ["retain alternatives"]}
        assert skills["data-quality"]["context_overrides"]["instructions"] == "Preserve uncertainty and counterevidence."
    assert client.inputs[0]["context"]["memories"] == []
    assert client.inputs[-1]["context"]["memories"][0]["memory_id"] == "m"
    assert (current, previous) == original
    assert "current_metrics" not in adapter.accounting() and "activation_update" not in adapter.accounting()


def test_current_memory_score_regression_has_real_previous_floor(tmp_path):
    def transform(report, context):
        if context["memories"]:
            report["status"] = "unsupported"
        return report
    current, previous = snapshots()
    result = service(tmp_path, llm=Client(transform)).check(current, previous)
    assert result["state"] == "regression" and result["key_regression"]
    assert result["reason"] == "key_score_below_previous" and result["permission_violations"] == 0
    assert result["current_metrics"]["score"] < result["previous_metrics"]["score"]
    assert result["provider_requests"] == 4


def test_non_target_skill_overlay_is_also_scored(tmp_path):
    def transform(report, context):
        if any(s["context_overrides"].get("routing_description") == "bad overlay" for s in context["skills"]):
            report["status"] = "unsupported"
        return report
    current, previous = snapshots()
    current["skills"]["temperature"]["routing_description"] = "bad overlay"
    result = service(tmp_path, llm=Client(transform)).check(current, previous)
    assert result["state"] == "regression" and result["key_regression"]


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(version=True),
    lambda s: s.update(context_version="wrong"),
    lambda s: s.update(authorization={"approve": True}),
    lambda s: s["skills"]["temperature"].update(allowed_tools=["approve"]),
    lambda s: s["skills"]["temperature"].update(instructions={"permission": "approve"}),
    lambda s: s["memories"][0].update(allowed_tools=["carbon_execute"]),
    lambda s: s["memories"][0].update(source_scope="sealed"),
    lambda s: s["memories"][0].update(source_trust=["independently_verified"]),
    lambda s: s["memories"][0].update(state="automatically_approved"),
    lambda s: s["memories"][0].update(available_at="not a timestamp"),
    lambda s: s["memories"][0].update(scope=["LFP"]),
    lambda s: s["memories"].append(copy.deepcopy(s["memories"][0])),
    lambda s: s["memories"].append(None),
    lambda s: s["memories"][0].update(counterexamples=[{"oracle": "label"}]),
    lambda s: s["memories"][0].update(version=2, revision_provenance={"previous_version": 1,
        "previous_available_at": "2026-09-02T12:00:00Z", "previous_feedback_id": "f"}),
])
def test_malformed_full_current_snapshot_is_hard_regression_before_any_provider(tmp_path, mutate):
    current, previous = snapshots()
    mutate(current)
    original = copy.deepcopy(current)
    client = Client()
    result = service(tmp_path, llm=client).check(current, previous)
    assert result["state"] == "regression" and result["key_regression"] and result["permission_violations"] == 1
    assert result["reason"] == "current_snapshot_failed_hard_validation" and result["validation_errors"]
    assert result["provider_requests"] == result["rollouts"] == client.request_count == 0
    assert result["previous_metrics"] is result["current_metrics"] is None
    assert current == original


def test_hard_current_guard_works_without_cloud_configuration(tmp_path):
    current, previous = snapshots()
    current["skills"]["temperature"]["permissions"] = ["approve"]
    result = service(tmp_path, llm=False).check(current, previous)
    assert result["state"] == "regression" and result["permission_violations"] == 1 and result["provider_requests"] == 0


def test_two_malformed_snapshots_cannot_recommend_restoring_an_invalid_previous_version(tmp_path):
    current, previous = snapshots()
    current["memories"][0]["state"] = "automatically_approved"
    previous["skills"]["temperature"]["allowed_tools"] = ["approve"]
    result = service(tmp_path).check(current, previous)
    assert result["state"] == "no_check" and result["reason"] == "current_and_previous_snapshots_failed_hard_validation"
    assert not result["key_regression"] and result["permission_violations"] == 0
    assert result["provider_requests"] == result["rollouts"] == 0
    assert {error["snapshot"] for error in result["validation_errors"]} == {"current", "previous"}


@pytest.mark.parametrize("variant,reason", [
    ("no_previous", "previous_snapshot_not_available"),
    ("no_client", "cloud_regression_client_not_configured"),
    ("no_dev", "independent_dev_selection_unavailable"),
    ("budget", "insufficient_budget_for_previous_and_current"),
    ("few_dev", "insufficient_independent_dev_roots"),
    ("sealed_dev", "independent_dev_selection_unavailable"),
    ("bad_previous", "previous_snapshot_failed_hard_validation"),
    ("bad_source", "source_root_ids_invalid"),
])
def test_unavailable_comparisons_are_explicit_no_check_without_fake_scores(tmp_path, variant, reason):
    current, previous = snapshots()
    client = Client()
    options, sources = {"llm": client}, []
    if variant == "no_previous":
        previous = None
    elif variant == "no_client":
        options["llm"] = False
    elif variant == "no_dev":
        options["selection_cases"] = []
    elif variant == "budget":
        options["rollout_budget"] = 3
    elif variant == "few_dev":
        options["selection_cases"] = cases()[:1]
    elif variant == "sealed_dev":
        options["selection_cases"] = [{**cases()[0], "split": "sealed"}]
    elif variant == "bad_previous":
        previous["skills"]["temperature"]["allowed_tools"] = ["approve"]
    elif variant == "bad_source":
        sources = "bad-source-type"
    result = service(tmp_path, **options).check(current, previous, source_root_ids=sources)
    assert result["state"] == "no_check" and result["reason"] == reason
    assert result["previous_metrics"] is result["current_metrics"] is None
    assert result["provider_requests"] == result["rollouts"] == client.request_count == 0
    assert not result["key_regression"]


def test_source_dev_root_is_excluded_and_stable_selection_is_order_independent(tmp_path):
    current, previous = snapshots()
    source = cases()[0]["root_scenario_id"]
    a = service(tmp_path).check(current, previous, source_root_ids=[source])
    b = service(tmp_path, selection_cases=list(reversed(cases()))).check(current, previous, source_root_ids=[source])
    assert a["state"] == b["state"] == "passed"
    assert a["selection_sha256"] == b["selection_sha256"] and source not in a["selection_root_ids"]


def test_previous_invalid_cloud_report_cannot_establish_a_floor(tmp_path):
    def transform(report, context):
        if not context["memories"]:
            report["status"] = "invented_status"
        return report
    current, previous = snapshots()
    adapter = service(tmp_path, llm=Client(transform))
    result = adapter.check(current, previous)
    assert result["state"] == "no_check" and result["reason"] == "previous_dev_evaluation_invalid"
    assert result["previous_metrics"]["hard_failures"] and result["current_metrics"] is None
    assert result["rollouts"] == result["provider_requests"] == result["provider_failed_requests"] == 2
    assert adapter.accounting()["provider_usage"]["total_tokens"] == 30


def test_current_invalid_cloud_report_is_regression_with_previous_evidence(tmp_path):
    def transform(report, context):
        if context["memories"]:
            report["status"] = "invented_status"
        return report
    current, previous = snapshots()
    result = service(tmp_path, llm=Client(transform)).check(current, previous)
    assert result["state"] == "regression" and result["reason"] == "current_dev_hard_failure"
    assert not result["previous_metrics"]["hard_failures"] and result["current_metrics"]["hard_failures"]
    assert result["key_regression"] and result["provider_failed_requests"] == 2


def test_current_permission_violation_is_a_hard_guard_even_if_score_is_equal(tmp_path):
    def runner(payload, **kwargs):
        result = run_agent(payload, **kwargs)
        if payload["context_snapshot"]["version"] == 1:
            result["tool_trace"].append({"name": "approve", "status": "rejected", "error": "tool_not_allowed"})
        return result
    current, previous = snapshots()
    result = service(tmp_path, runner=runner).check(current, previous)
    assert result["state"] == "regression" and result["permission_violations"] == 2
    assert result["current_metrics"]["score"] == result["previous_metrics"]["score"]


def test_cancellation_conserves_actual_provider_cost_and_reserves_full_first_snapshot(tmp_path):
    flag = {"cancelled": False}
    def runner(payload, **kwargs):
        result = run_agent(payload, **kwargs)
        flag["cancelled"] = True
        return result
    current, previous = snapshots()
    original = copy.deepcopy((current, previous))
    adapter = service(tmp_path, runner=runner, cancelled=lambda: flag["cancelled"])
    with pytest.raises(RuntimeError, match="context regression cancelled"):
        adapter.check(current, previous)
    cost = adapter.accounting()
    assert cost["state"] == "cancelled" and cost["rollouts"] == 2 and cost["provider_requests"] == 1
    assert cost["provider_usage"]["total_tokens"] == 15 and cost["budget"]["remaining_rollouts"] == 2
    assert (current, previous) == original
    assert "current_metrics" not in cost and "key_regression" not in cost and "activation_update" not in cost


def test_exhausted_reused_service_budget_never_repeats_provider(tmp_path):
    current, previous = snapshots()
    adapter = service(tmp_path)
    assert adapter.check(current, previous)["state"] == "passed"
    result = adapter.check(current, previous)
    assert result["reason"] == "insufficient_budget_for_previous_and_current" and result["provider_requests"] == 0
    assert adapter.accounting()["rollouts"] == 4 and adapter.accounting()["provider_requests"] == 4


def test_optional_cold_start_fields_future_availability_and_quarantined_memory_remain_legal(tmp_path):
    current, previous = snapshots()
    current["context_snapshot_id"] = "rollback-17"
    current["memories"][0].update(source_scope="cold_start", available_at="2026-09-02T12:00:00Z", state="quarantined")
    result = service(tmp_path).check(current, previous)
    assert result["state"] == "passed"


def test_unknown_skill_id_never_reaches_provider(tmp_path):
    current, previous = snapshots()
    current["skills"]["unlicensed"] = {"instructions": "outside release"}
    result = service(tmp_path).check(current, previous)
    assert result["state"] == "regression" and result["reason"] == "current_snapshot_skill_outside_licensed_release"
    assert result["provider_requests"] == result["rollouts"] == 0


def test_unknown_previous_skill_cannot_be_a_restoration_target(tmp_path):
    current, previous = snapshots()
    current["skills"]["unlicensed"] = {"instructions": "current outside release"}
    previous["skills"]["unlicensed"] = {"instructions": "previous outside release"}
    result = service(tmp_path).check(current, previous)
    assert result["state"] == "no_check" and result["reason"] == "current_and_previous_snapshots_failed_hard_validation"
    assert not result["key_regression"] and result["provider_requests"] == 0


def test_malformed_current_with_unknown_previous_release_is_no_check_without_cloud(tmp_path):
    current, previous = snapshots()
    current["skills"]["temperature"]["allowed_tools"] = ["approve"]
    previous["skills"]["unlicensed"] = {"instructions": "bad restoration target"}
    result = service(tmp_path, llm=False).check(current, previous)
    assert result["state"] == "no_check" and not result["key_regression"] and result["provider_requests"] == 0


def test_real_client_copy_has_independent_costs_and_no_retry_or_tool_calls(tmp_path):
    calls = []
    def transport(request):
        body = json.loads(request.content)
        calls.append(body)
        assert "tools" not in body
        return httpx.Response(503, json={"usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}})
    client = OpenAICompatibleClient(api_key="mock-key", proxy=None, retries=3, transport=httpx.MockTransport(transport))
    original_retries = client.retries
    current, previous = snapshots()
    result = service(tmp_path, llm=client).check(current, previous)
    assert result["state"] == "no_check" and result["reason"] == "previous_dev_evaluation_invalid"
    assert len(calls) == 2 and result["provider_requests"] == result["provider_failed_requests"] == 2
    assert result["provider_usage"]["total_tokens"] == 6 and result["provider_unknown_usage_requests"] == 0
    assert client.request_count == client.failed_request_count == 0 and client.retries == original_retries
    assert client.total_usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_client_without_usage_telemetry_marks_provider_usage_unknown(tmp_path):
    class NoTelemetry:
        def generate_json(self, messages, schema=None):
            return json.loads(messages[-1]["content"])["report_template"]
    current, previous = snapshots()
    result = service(tmp_path, llm=NoTelemetry()).check(current, previous)
    assert result["state"] == "passed" and result["provider_requests"] == 4
    assert result["provider_unknown_usage_requests"] == 4 and result["provider_usage"] == {}


def test_partial_usage_and_provider_failures_are_retained_without_double_count(tmp_path):
    class Failed:
        def __init__(self):
            self.request_count = self.failed_request_count = 0
            self.total_usage = {"total_tokens": 0}
        def generate_json(self, messages, schema=None):
            self.request_count += 1
            self.failed_request_count += 1
            self.total_usage["total_tokens"] += 3
            raise ValueError("test malformed response")
    current, previous = snapshots()
    adapter = service(tmp_path, llm=Failed())
    result = adapter.check(current, previous)
    assert result["state"] == "no_check" and result["reason"] == "previous_dev_evaluation_invalid"
    assert result["provider_requests"] == result["provider_failed_requests"] == result["provider_unknown_usage_requests"] == 2
    assert result["provider_usage"] == {"total_tokens": 6}
    assert adapter.accounting()["provider_failed_requests"] == 2


def test_complete_only_client_receives_no_tools_and_malformed_response_fails_once(tmp_path):
    class CompleteOnly:
        def complete(self, messages, *, response_format):
            assert response_format == {"type": "json_object"}
            return {"choices": [{"message": {"content": "[]"}}]}
    current, previous = snapshots()
    result = service(tmp_path, llm=CompleteOnly()).check(current, previous)
    assert result["state"] == "no_check" and result["provider_requests"] == 2
    assert result["provider_failed_requests"] == result["provider_unknown_usage_requests"] == 2
    assert result["provider_usage"] == {}


def test_cancel_before_check_records_zero_billable_or_reserved_work(tmp_path):
    current, previous = snapshots()
    adapter = service(tmp_path, cancelled=lambda: True)
    with pytest.raises(RuntimeError, match="context regression cancelled"):
        adapter.check(current, previous)
    assert adapter.accounting()["state"] == "cancelled"
    assert adapter.accounting()["rollouts"] == adapter.accounting()["provider_requests"] == 0


def test_interrupted_scorer_preserves_cost_without_exposing_exception_prose(tmp_path):
    def runner(payload, **kwargs):
        run_agent(payload, **kwargs)
        raise RuntimeError("PRIVATE_DIAGNOSTIC_SHOULD_NOT_LEAK")
    current, previous = snapshots()
    adapter = service(tmp_path, runner=runner)
    result = adapter.check(current, previous)
    assert result["state"] == "no_check" and result["reason"] == "dev_evaluation_failed"
    assert result["rollouts"] == 2 and result["provider_requests"] == 1
    assert result["provider_usage"]["total_tokens"] == 15 and not result["key_regression"]
    assert "PRIVATE_DIAGNOSTIC_SHOULD_NOT_LEAK" not in json.dumps(result)
