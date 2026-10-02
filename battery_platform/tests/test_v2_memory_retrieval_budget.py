"""Handmade evidence categories and bounded retrieval; no provider or labels."""
from collections import Counter
import copy
import json

import pytest

from app.agent import ContextStore, run_agent
from app.agent.context import MemoryRetrievalBudget, memory_retrieval_kind
from test_v2_agent_core import payload


CUTOFF = "2026-09-01T12:00:00Z"


def memory(mid, kind="positive", **changes):
    entry = {"memory_id": mid, "version": 1, "scope": {"installation_id": "installation-a", "chemistry": "LFP"},
             "trigger": "channel", "insight": "Retain a source-supported applicable condition.",
             "supporting_case_ids": ["manual-root-" + mid], "counterexamples": [], "source_trust": "measurement_supported",
             "state": "active", "source_scope": "operational", "available_at": "2026-09-01T10:00:00Z",
             "helpful_count": 0, "harmful_count": 0, "last_used": None, "expires_at": None}
    if kind == "counterexample":
        entry.update(state="conflicted", conflicts=[{"insight": "An opposite source remains unresolved.",
                    "supporting_case_ids": ["manual-opposite-" + mid], "source_trust": "reported"}])
    elif kind == "unclassified":
        entry["source_trust"] = "reported"
    return {**entry, **changes}


def store(entries):
    snapshot = ContextStore().snapshot()
    snapshot["memories"] = entries
    return ContextStore(initial_snapshot=snapshot)


def retrieve(entries, **kwargs):
    return store(entries).search("channel", scope={"installation_id": "installation-a", "chemistry": "LFP"}, cutoff=CUTOFF, **kwargs)


def counts(items):
    return Counter(item["retrieval_kind"] for item in items)


def test_high_score_support_cannot_crowd_out_recorded_counterexamples():
    entries = [memory(f"p-{i}", insight="channel source-supported applicable condition") for i in range(8)]
    entries += [memory(f"c-{i}", "counterexample", trigger="other", insight="An opposite channel observation.") for i in range(8)]
    items = retrieve(entries)
    assert counts(items) == {"positive": 3, "counterexample": 3}
    assert {m["memory_id"] for m in items} == {"p-0", "p-1", "p-2", "c-0", "c-1", "c-2"}
    assert all(m["conflicts"][0]["source_trust"] == "reported" for m in items if m["retrieval_kind"] == "counterexample")


@pytest.mark.parametrize("kind", ["positive", "counterexample"])
def test_missing_other_class_never_borrows_above_three(kind):
    items = retrieve([memory(str(i), kind) for i in range(8)])
    assert len(items) == 3 and counts(items) == {kind: 3}


def test_unclassified_reports_fill_missing_slots_without_becoming_successes():
    entries = [memory("p-a"), memory("p-b"), memory("c-a", "counterexample")]
    entries += [memory(f"u-{i}", "unclassified", insight="channel confirmed successful root cause") for i in range(8)]
    items = retrieve(entries)
    assert len(items) == 6 and counts(items) == {"positive": 2, "counterexample": 1, "unclassified": 3}
    assert all(m["source_trust"] == "reported" for m in items if m["retrieval_kind"] == "unclassified")
    only_reports = retrieve([memory(f"u-{i}", "unclassified") for i in range(8)])
    assert len(only_reports) == 6 and counts(only_reports) == {"unclassified": 6}
    assert retrieve([]) == []


@pytest.mark.parametrize("fields,basis", [
    ({"state": "conflicted"}, "recorded_conflict"),
    ({"source_trust": "contradicted"}, "source_contradicted"),
    ({"counterexamples": [{"claim": "Conditions do not support this interpretation", "source_trust": "reported"}]}, "explicit_counterexamples"),
    ({"conflicts": [{"insight": "Competing source", "source_trust": "reported", "supporting_case_ids": ["manual-counter"]}]}, "explicit_conflicting_sources"),
])
def test_counterevidence_precedes_source_support_without_erasing_both_sides(fields, basis):
    original = memory("mixed", **{"source_trust": "independently_verified", **fields})
    item = retrieve([original])[0]
    assert (item["retrieval_kind"], item["retrieval_basis"]) == ("counterexample", basis)
    assert item["insight"] == original["insight"] and item["supporting_case_ids"] == original["supporting_case_ids"]


@pytest.mark.parametrize("fields", [
    {"source_trust": "reported"}, {"source_trust": None}, {"source_trust": ["independently_verified"]},
    {"supporting_case_ids": []}, {"supporting_case_ids": [""]},
])
def test_missing_or_unestablished_category_does_not_infer_success_from_prose(fields):
    kind, _ = memory_retrieval_kind(memory("unknown", insight="confirmed successful channel", **fields))
    assert kind == "unclassified"


def test_domain_visibility_expiry_and_inactive_filters_apply_before_quotas():
    entries = [memory("wrong-install", scope={"installation_id": "installation-b"}),
               memory("wrong-chemistry", scope={"chemistry": "NCM"}),
               memory("future-counter", "counterexample", available_at="2026-09-02T00:00:00Z"),
               memory("expired-counter", "counterexample", expires_at="2026-08-01T00:00:00Z"),
               memory("inactive-counter", "counterexample", state="quarantined"),
               memory("visible-positive"), memory("visible-counter", "counterexample")]
    assert {m["memory_id"] for m in retrieve(entries)} == {"visible-positive", "visible-counter"}


@pytest.mark.parametrize("limit", [0, 1, 2, 3, 5, 6, 99])
def test_smaller_total_is_fair_and_preserves_counterevidence_first(limit):
    items = retrieve([memory(f"p-{i}") for i in range(4)] + [memory(f"c-{i}", "counterexample") for i in range(4)], limit=limit)
    assert len(items) == min(limit, 6)
    assert counts(items)["positive"] <= 3 and counts(items)["counterexample"] <= 3
    if limit:
        assert counts(items)["counterexample"] >= counts(items)["positive"]


@pytest.mark.parametrize("limit", [-1, True, "3", 1.5])
def test_invalid_limits_do_not_turn_into_negative_slice_or_boolean_budget(limit):
    with pytest.raises(ValueError, match="limit"):
        retrieve([memory("one")], limit=limit)


def test_reward_counters_and_client_category_do_not_change_classification_or_rank():
    entries = [memory(f"p-{i}") for i in range(4)] + [memory(f"c-{i}", "counterexample") for i in range(4)]
    initial = retrieve(entries)
    changed = copy.deepcopy(entries)
    for i, item in enumerate(changed):
        item.update(helpful_count=1000 * i, harmful_count=1000 * (8 - i), retrieval_kind="unclassified")
    assert [m["memory_id"] for m in retrieve(changed)] == [m["memory_id"] for m in initial]
    before = store(entries)
    original = before.snapshot()
    result = before.search("channel", scope={"installation_id": "installation-a", "chemistry": "LFP"}, cutoff=CUTOFF)
    result[0]["insight"] = "Changed returned copy"
    assert before.snapshot() == original and not any("retrieval_kind" in m for m in original["memories"])


def test_round_budget_deduplicates_reuses_frozen_view_and_does_not_reset_per_query():
    budget = MemoryRetrievalBudget()
    first = budget.admit([memory(f"p-{i}") for i in range(3)])
    # Missing counterexamples may be filled by neutral reports, never a fourth positive.
    assert budget.admit([memory("p-new")]) == []
    budget.admit([memory("counter", "counterexample"), memory("reported", "unclassified"), memory("reported-two", "unclassified")])
    returned = budget.admit([memory("p-0", insight="must not revise frozen retrieval"), memory("p-0"), memory("new-counter", "counterexample")])
    assert len(returned) == 1 and returned[0]["insight"] == first[0]["insight"]
    summary = budget.summary()
    assert summary["unique_retrieved"] == 6 and summary["remaining_total"] == 0
    assert summary["counts"] == {"positive": 3, "counterexample": 1, "unclassified": 2}
    assert summary["excluded_by_budget"] == 2


def test_executor_initial_context_and_repeated_memory_tools_share_six_entries():
    entries = [memory(f"p-{i}") for i in range(4)] + [memory(f"c-{i}", "counterexample") for i in range(4)]
    class Client:
        model = "handmade-test-only-client"
        def __init__(self):
            self.calls = 0
        def complete(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                data = json.loads(messages[-1]["content"])
                self.report = data["report_template"]
                self.initial = data["context"]
                return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "one", "type": "function", "function": {"name": "search_memory", "arguments": '{"query":"one"}'}},
                    {"id": "two", "type": "function", "function": {"name": "search_memory", "arguments": '{"query":"two"}'}}]}}]}
            return {"choices": [{"message": {"role": "assistant", "content": json.dumps(self.report)}}]}
    client = Client()
    def tool(arguments):
        if arguments["query"] == "one":
            return [memory(f"new-p-{i}") for i in range(4)]
        return [memory(f"new-c-{i}", "counterexample") for i in range(4)] + [memory("c-0", "counterexample")]
    current = payload()
    current["symptoms"] = "channel"
    result = run_agent(current, context_store=store(entries), llm=client, tools={"search_memory": tool})
    assert result["run"]["cloud_report_valid"] and client.calls == 2
    assert counts(client.initial["memories"]) == {"positive": 3, "counterexample": 3}
    trace = [t for t in result["tool_trace"] if t["name"] == "search_memory"]
    assert trace[0]["result"] == [] and [m["memory_id"] for m in trace[1]["result"]] == ["c-0"]
    assert result["run"]["memory_retrieval_budget"]["unique_retrieved"] == 6
    assert result["run"]["memory_retrieval_budget"]["excluded_by_budget"] == 8
    assert set(result["run"]["retrieved_memory_ids"]) == {m["memory_id"] for m in client.initial["memories"]}
