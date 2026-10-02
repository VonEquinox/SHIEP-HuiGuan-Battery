"""Applicable lexical retrieval is distinct from explicit event history."""
from collections import Counter

import pytest

from app.agent.context import MemoryRetrievalBudget, memory_relevance
from test_v2_memory_retrieval_budget import CUTOFF, memory, store


SCOPE = {"installation_id": "installation-a", "chemistry": "LFP"}


@pytest.mark.parametrize("query", ["", " ", "现场本次反馈检查结果", "inspection feedback", "火星轨道探测任务", "12.4"])
def test_unrelated_or_empty_queries_do_not_fill_similarity_budget(query):
    context = store([memory("resistance", trigger="inspection feedback", insight="内阻升高待排查。"),
                     memory("voltage-counter", "counterexample", trigger="电压偏差", insight="复测电压未发现偏差。")])
    hits = context.search(query, scope=SCOPE, cutoff=CUTOFF)
    budget = MemoryRetrievalBudget()
    assert hits == [] and budget.admit(hits) == []
    assert budget.summary()["unique_retrieved"] == 0
    assert {item["memory_id"] for item in context.history(scope=SCOPE, cutoff=CUTOFF)} == {"resistance", "voltage-counter"}
    assert all(item["retrieval_mode"] == "event_history" for item in context.history(scope=SCOPE, cutoff=CUTOFF))


def test_unspaced_chinese_and_bilingual_terms_find_only_matching_evidence():
    context = store([memory("resistance", trigger="接触电阻", insight="实测 resistance 明显变化。"),
                     memory("voltage", trigger="电压异常", insight="独立复测电压有差异。")])
    hits = context.search("复测内阻升高是否需要排查", scope=SCOPE, cutoff=CUTOFF)
    assert [item["memory_id"] for item in hits] == ["resistance"]
    hit = hits[0]
    assert hit["retrieval_mode"] == "similar_experience" and hit["relevance_score"] > 0
    assert "concept:resistance" in hit["relevance_matched_terms"]
    assert memory_relevance("resistance", {"insight": "无空格的内阻升高记录"})[0] > 0
    assert memory_relevance("采集偏差", {"insight": "独立检查容量损失"})[0] == 0


def test_latin_terms_use_boundaries_and_numbers_do_not_establish_relevance():
    assert memory_relevance("bias", {"insight": "biased sampling with 12.4 mOhm"})[0] == 0
    assert memory_relevance("12.4", {"insight": "temperature is 12.4 C"})[0] == 0
    assert memory_relevance("voltage", {"insight": "VOLTAGE reading"})[0] == 1


def test_balancing_uses_relevant_counterevidence_only():
    entries = [memory(f"p-{i}", trigger="内阻复测", insight="接触内阻独立测量。") for i in range(5)]
    entries += [memory(f"c-{i}", "counterexample", trigger="内阻异常", insight="独立内阻测量不支持先前判断。") for i in range(5)]
    entries += [memory("unrelated-counter", "counterexample", trigger="容量", insight="容量变化仍待确认。")]
    hits = store(entries).search("内阻升高", scope=SCOPE, cutoff=CUTOFF)
    assert Counter(item["retrieval_kind"] for item in hits) == {"positive": 3, "counterexample": 3}
    assert "unrelated-counter" not in {item["memory_id"] for item in hits}
    no_relevant_counter = store(entries[:5] + entries[-1:]).search("内阻升高", scope=SCOPE, cutoff=CUTOFF)
    assert len(no_relevant_counter) == 3
    assert all(item["retrieval_kind"] == "positive" for item in no_relevant_counter)


def test_complete_late_facts_and_conflict_claims_remain_searchable():
    entries = [memory("late-measurement", trigger="inspection", insight="本次到场登记。",
                      fact_references=[{"reference_id": "measurement-1", "claim": "resistance=12.4 mOhm", "source_text": "resistance=12.4 mOhm"}]),
               memory("late-counter", "counterexample", trigger="inspection", insight="本次到场登记。",
                      conflicts=[{"claim": "内阻复测未发现上升", "supporting_case_ids": ["other-root"]}])]
    hits = store(entries).search("内阻", scope=SCOPE, cutoff=CUTOFF)
    assert {item["memory_id"] for item in hits} == {"late-measurement", "late-counter"}
    assert memory_relevance("电压", {"conflicts": [{"fact_references": [{"claim": "晚到反证", "source_text": "电压并未变化"}]}]})[0] > 0


def test_history_requires_exact_installation_and_narrows_current_root():
    entries = [memory("current", supporting_case_ids=["current-root"]),
               memory("other-root", supporting_case_ids=["other-root"]),
               memory("global", scope={"chemistry": "LFP"}),
               memory("wrong-install", scope={"installation_id": "installation-b"}),
               memory("future", supporting_case_ids=["current-root"], available_at="2026-09-02T00:00:00Z")]
    context = store(entries)
    assert [item["memory_id"] for item in context.history(scope=SCOPE, cutoff=CUTOFF, root_id="current-root")] == ["current"]
    assert {item["memory_id"] for item in context.history(scope=SCOPE, cutoff=CUTOFF)} == {"current", "other-root"}
    assert context.history(scope={"chemistry": "LFP"}, cutoff=CUTOFF) == []
    assert {item["memory_id"] for item in context.history(scope=SCOPE, cutoff=CUTOFF,
                                                        root_ids=["current-root", "other-root"])} == {"current", "other-root"}
    assert context.history(scope=SCOPE, cutoff=CUTOFF, root_ids=[]) == []


def test_budget_preserves_history_or_similarity_provenance():
    context = store([memory("one", trigger="内阻", insight="内阻测量。")])
    hit = context.search("内阻", scope=SCOPE, cutoff=CUTOFF)[0]
    accepted = MemoryRetrievalBudget().admit([hit])[0]
    assert accepted["retrieval_mode"] == "similar_experience"
    assert accepted["relevance_score"] == hit["relevance_score"]
    assert accepted["relevance_matched_terms"] == hit["relevance_matched_terms"]
    history = context.history(scope=SCOPE, cutoff=CUTOFF)[0]
    assert MemoryRetrievalBudget().admit([history])[0]["retrieval_mode"] == "event_history"
