"""Feedback fact provenance and bounded semantic summaries; no cloud calls."""
from __future__ import annotations

import copy

import pytest

from app.agent import ContextStore, evolve_context, extract_feedback
from app.agent.context import MemoryRetrievalBudget
from app.agent.regression import _validate_snapshot


CUTOFF = "2026-10-02T12:00:00Z"


def feedback(**changes):
    return {"feedback_id": "feedback-1", "root_scenario_id": "root-1", "installation_id": "installation-a",
            "author_id": "engineer-7", "available_at": "2026-10-02T10:00:00Z", "version": 1,
            "free_text": "", **changes}


@pytest.mark.parametrize("text,claims", [
    ("本次内阻为12.4 mΩ，复测电压为3.65 V。", ["本次内阻为12.4 mΩ，复测电压为3.65 V。"]),
    ("温度为-20.5°C。偏移为-.5 V。", ["温度为-20.5°C。", "偏移为-.5 V。"]),
    ("偏移为.5 V。", ["偏移为.5 V。"]),
    ("Leakage is -1.2e-3 A. Voltage is 3.65 V.", ["Leakage is -1.2e-3 A.", "Voltage is 3.65 V."]),
    ("范围为-20.5--18.25 °C，内阻12.4–13.6 mΩ。", ["范围为-20.5--18.25 °C，内阻12.4–13.6 mΩ。"]),
    ("日期2026.10.02，复测2026-10-03 10:30:00。", ["日期2026.10.02，复测2026-10-03 10:30:00。"]),
    ("Reading is 12.4. Recheck is pending.", ["Reading is 12.4.", "Recheck is pending."]),
    ("  12.4 mΩ。\n\t-.5 V。  ", ["12.4 mΩ。", "-.5 V。"]),
])
def test_numeric_tokens_and_exact_source_spans(text, claims):
    result = extract_feedback(feedback(free_text=text))
    assert [f["claim"] for f in result["candidate_facts"]] == claims
    assert result["free_text"] == text
    for fact in result["candidate_facts"]:
        assert text[fact["span"]["start"]:fact["span"]["end"]] == fact["source_text"] == fact["claim"]
        assert fact["extraction_model"] == "span-extractor-v2-numeric"


def test_measurement_and_late_conclusion_precede_registration_prose():
    text = "".join(f"登记步骤{i}已完成。" for i in range(6)) + "最终结论：连接处存在松动。"
    source = feedback(free_text=text, measurements=[{"metric": "resistance", "value": 12.4, "unit": "mOhm"}])
    result = evolve_context(ContextStore(), source)
    memory = result["snapshot"]["memories"][0]
    assert len(memory["fact_references"]) == 8
    assert "resistance=12.4 mOhm" in memory["insight"]
    assert "最终结论：连接处存在松动。" in memory["insight"]
    measurement = next(f for f in memory["fact_references"] if f.get("measurement"))
    assert measurement["source_field"] == "measurements" and measurement["source_index"] == 0
    assert measurement["feedback_id"] == "feedback-1" and measurement["feedback_version"] == 1
    assert memory["fact_summary"]["omitted_fact_count"] == 2
    assert _validate_snapshot(result["snapshot"]) == []


def test_full_overflow_facts_remain_query_retrievable_and_budget_preserves_projection(tmp_path):
    store = ContextStore(tmp_path / "context.json")
    text = "关键接线标签为BLUE-42。" + "".join(f"登记步骤{i}已完成。" for i in range(9))
    source = feedback(free_text=text, measurements=[{"metric": "resistance", "value": 12.4, "unit": "mOhm"}])
    result = evolve_context(store, source)
    memory = result["snapshot"]["memories"][0]
    assert len(memory["fact_references"]) == 11
    assert "BLUE-42" not in memory["insight"]
    retrieved = store.search("接线标签", scope={"installation_id": "installation-a"}, cutoff=CUTOFF)
    assert len(retrieved) == 1
    view = retrieved[0]
    assert any("BLUE-42" in f["claim"] for f in view["fact_references"])
    assert len(view["fact_references"]) <= 6
    assert sum(len(f["claim"]) for f in view["fact_references"]) <= 2400
    assert view["fact_summary"]["total_fact_count"] == 11
    assert view["fact_summary"]["omitted_fact_count"] == 5
    assert view["retrieval_mode"] == "similar_experience"
    budget = MemoryRetrievalBudget()
    initial = store.history(scope={"installation_id": "installation-a"}, cutoff=CUTOFF, root_id="root-1")
    assert not any("BLUE-42" in f["claim"] for f in initial[0]["fact_references"])
    budget.admit(initial)
    accepted = budget.admit(retrieved)
    assert accepted == retrieved
    assert budget.summary()["unique_retrieved"] == 1
    # Persistence carries complete source references, not the bounded view.
    assert len(ContextStore(tmp_path / "context.json").snapshot()["memories"][0]["fact_references"]) == 11


def test_late_counterevidence_retains_both_source_bundles_and_flags():
    store = ContextStore()
    first = evolve_context(store, feedback(free_text="诊断认为采集异常。"))
    second = evolve_context(store, feedback(feedback_id="feedback-2", version=2,
                            free_text="独立复核未发现采集异常，原判断不支持。", contradicts_previous=True,
                            available_at="2026-10-02T11:00:00Z", performed_actions=["approved repair"],
                            unresolved_items=["内阻异常原因未知"]))
    memory = second["snapshot"]["memories"][0]
    assert memory["state"] == "conflicted"
    assert {f["feedback_id"] for f in memory["fact_references"]} == {"feedback-1", "feedback-2"}
    assert "原判断不支持" in memory["insight"]
    assert "内阻异常原因未知" in memory["insight"]
    assert memory["conflicts"][0]["fact_references"] == memory["fact_references"]
    assert memory["source_label_guards"]["intervention_prevents_false_positive_label"]
    assert any(f.get("contradicts_previous") for f in memory["fact_references"])
    assert first["snapshot"]["memories"][0]["fact_references"][0]["source_text"] == "诊断认为采集异常。"
    assert _validate_snapshot(second["snapshot"]) == []


def test_structured_measurement_and_free_text_conflict_keeps_exact_values():
    source = feedback(free_text="实测电压为3.65 V。", measurements=[{"metric": "voltage", "value": 3.8, "unit": "V"}],
                      unresolved_items=["结构化测量与文字记录冲突，需复测"])
    result = evolve_context(ContextStore(), source)
    memory = result["snapshot"]["memories"][0]
    assert "3.65 V" in memory["insight"] and "voltage=3.8 V" in memory["insight"]
    assert "结构化测量与文字记录冲突" in memory["insight"]
    assert next(f for f in memory["fact_references"] if f.get("measurement"))["trust"] == "measurement_supported"
    assert next(f for f in memory["fact_references"] if f.get("span"))["trust"] == "reported"


def test_measurement_trust_downgrade_is_preserved():
    source = feedback(measurements=[{"metric": "resistance", "value": 12.4, "unit": "mOhm"}])
    corrected = extract_feedback(source)["candidate_facts"]
    corrected[0]["trust"] = "reported"  # API applies this for an uncalibrated instrument.
    result = evolve_context(ContextStore(), {**source, "candidate_facts": corrected})
    assert result["snapshot"]["memories"][0]["fact_references"][0]["trust"] == "reported"
    assert _validate_snapshot(result["snapshot"]) == []


def test_fact_reference_tampering_is_rejected_by_snapshot_regression():
    result = evolve_context(ContextStore(), feedback(free_text="复测电压为3.65 V。"))
    snapshot = copy.deepcopy(result["snapshot"])
    snapshot["memories"][0]["fact_references"][0]["span"]["end"] += 1
    assert "memory_fact_references_invalid" in _validate_snapshot(snapshot)


def test_long_claim_excerpt_is_explicit_and_conflict_view_does_not_reexpand_full_facts():
    store = ContextStore()
    long_claim = "temperature " + "原始记录" * 750 + "。"
    evolve_context(store, feedback(free_text=long_claim))
    result = evolve_context(store, feedback(feedback_id="feedback-2", version=2, free_text="温度反证仍需复核。",
                            contradicts_previous=True, available_at="2026-10-02T11:00:00Z"))
    view = store.history(scope={"installation_id": "installation-a"}, cutoff=CUTOFF, root_id="root-1")[0]
    assert sum(len(f["claim"]) for f in view["fact_references"]) <= 2400
    excerpt = next(f for f in view["fact_references"] if f.get("claim_excerpt"))
    assert excerpt["source_text"] == long_claim[excerpt["span"]["start"]:excerpt["span"]["end"]]
    assert excerpt["full_source_span"]["end"] == len(long_claim)
    assert all("fact_references" not in c for c in view["conflicts"])
    assert view["conflict_summary"]["total_conflict_count"] == 1
    assert len(result["snapshot"]["memories"][0]["fact_references"][0]["claim"]) > 2400


def test_repeated_feedback_without_timestamp_does_not_duplicate_fact_references():
    store = ContextStore()
    source = feedback(free_text="本次内阻为12.4 mΩ。")
    source.pop("available_at")
    first = evolve_context(store, source)
    repeated = evolve_context(store, source)
    assert repeated["state"] == "no_update"
    assert repeated["snapshot"] == first["snapshot"]


def test_corrected_short_claim_with_long_source_remains_bounded_and_source_spanned():
    store = ContextStore()
    raw = "voltage " + "原文记录" * 750 + "。"
    source = feedback(free_text=raw, candidate_facts=[{"fact_id": "corrected", "claim": "短结论，保留未知。",
                     "span": {"start": 0, "end": len(raw)}, "source_text": raw, "trust": "reported"}])
    evolve_context(store, source)
    view = store.history(scope={"installation_id": "installation-a"}, cutoff=CUTOFF, root_id="root-1")[0]
    fact = view["fact_references"][0]
    assert fact["claim"] == "短结论，保留未知。"
    assert fact["source_excerpt"] and len(fact["source_text"]) == 2400
    assert raw[fact["span"]["start"]:fact["span"]["end"]] == fact["source_text"]
    assert fact["full_source_span"]["end"] == len(raw)


def test_extracted_structured_facts_can_be_corrected_through_real_api(admin, monkeypatch):
    from app.db import obj, one, tx
    from test_v2_workflow import approved, observation, work_job

    monkeypatch.delenv("BATTERY_LLM_API_KEY", raising=False)
    asset, _, _, _, order, _ = approved(admin)
    source = observation(asset, order, uuid="numeric-feedback-source-0001")
    source.update(free_text="本次内阻为12.4 mΩ，复测电压为3.65 V。", excluded_hypotheses=["sensor_failure"])
    created = admin.post(f"/api/v2/orders/{order['id']}/observations", json=source)
    assert created.status_code == 201, created.text
    identifiers = created.json()
    extraction = work_job(identifiers["extraction_job_id"])
    assert extraction["status"] == "succeeded", extraction["error"]
    with tx() as c:
        record = one(c, "SELECT * FROM inspection_observations WHERE id=:i", {"i": identifiers["observation_id"]})
        facts = obj(record["candidate_facts"])
        assert any(f.get("source_field") == "excluded_hypotheses" for f in facts)
    corrected = admin.post(f"/api/v2/observations/{identifiers['observation_id']}/facts", json={
        "version": record["version"], "candidate_facts": facts, "note": "保留原文小数与结构化来源"})
    assert corrected.status_code == 200, corrected.text
    repaired = work_job(corrected.json()["job_id"])
    assert repaired["status"] == "succeeded", repaired["error"]
    forged = copy.deepcopy(facts)
    next(f for f in forged if f.get("source_field") == "excluded_hypotheses")["source_index"] = 99
    with tx() as c:
        version = one(c, "SELECT version FROM inspection_observations WHERE id=:i", {"i": identifiers["observation_id"]})["version"]
    invalid = admin.post(f"/api/v2/observations/{identifiers['observation_id']}/facts", json={
        "version": version, "candidate_facts": forged, "note": "无效来源不得进入学习"})
    assert invalid.status_code == 422


@pytest.mark.parametrize("text,measurements", [
    ("长记录" * 1000 + "。", []),
    ("".join(f"到达登记{i}。" for i in range(110)), [{"metric": "resistance", "value": 12.4, "unit": "mOhm"}]),
], ids=["long_sentence", "many_sentences_late_measurement"])
def test_compute_api_preserves_large_automatic_extraction_but_bounds_memory(text, measurements):
    from app.api_evolution import feedback_compute
    from app.db import js

    source = feedback(free_text=text, measurements=measurements, calibration_status="unknown")
    result = feedback_compute({"feedback": source, "base": {"content": js(ContextStore().snapshot())},
                               "preserve_corrected_facts": False, "previous_report": {}}, lambda: False)
    assert result["state"] == "active"
    snapshot = ContextStore().apply(result["updates"], expected_version=0)["snapshot"]
    memory = snapshot["memories"][0]
    assert len(memory["fact_references"]) == len(extract_feedback(source)["candidate_facts"])
    assert _validate_snapshot(snapshot) == []
    view = ContextStore(initial_snapshot=snapshot).history(scope={"installation_id": "installation-a"}, cutoff=CUTOFF)[0]
    assert len(view["fact_references"]) <= 6
    assert sum(max(len(f["claim"]), len(f.get("source_text", ""))) for f in view["fact_references"]) <= 2400
    if measurements:
        assert "resistance=12.4 mOhm" in view["insight"]
        assert next(f for f in memory["fact_references"] if f.get("measurement"))["trust"] == "reported"
