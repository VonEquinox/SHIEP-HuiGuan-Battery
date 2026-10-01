"""Hand-constructed language/identifier cases; no benchmark fixtures or API."""
from __future__ import annotations

import pytest

from app.agent import validate_report
from app.agent.contracts import _text_numbers

CUTOFF = "2026-09-01T00:00:00Z"


def validate(claim, source):
    report = {"report_id": "r", "asset_id": "a", "installation_id": "i", "visible_cutoff": CUTOFF,
              "round": 1, "status": "insufficient_evidence", "facts": [{"claim": claim, "evidence_ids": ["e"]}],
              "hypotheses": [], "unknowns": [], "applicability": {}, "suggested_tests": [],
              "priority": {"class": "needs_inspection", "reason": "Review evidence"}, "citations": ["e"],
              "context_version": "v0"}
    return validate_report(report, evidence_ids={"e"}, test_ids=set(), installation_id="i", cutoff=CUTOFF,
                           evidence_records={"e": source})


@pytest.mark.parametrize("claim,value", [
    ("温度18.25", 18.25), ("温度18.25℃", 18.25), ("温度 18.25 °C", 18.25),
    ("Temperature 18.25", 18.25), ("Voltage 18.25V", 18.25),
    ("温度-18.25摄氏度", -18.25), ("温度−18.25℃", -18.25),
    ("电流+0.25A", 0.25), ("电压.25V", 0.25), ("电流1.825e-3A", 0.001825),
])
def test_complete_cited_number_passes_in_chinese_english_and_compact_units(claim, value):
    assert _text_numbers(claim) == [value]
    assert validate(claim, {"value": value})["facts"][0]["claim"] == claim


@pytest.mark.parametrize("source", [{"value": 18.25}, {"summary": "温度18.25℃"},
                                    {"measurements": [{"value": 18.25, "unit": "°C"}]}])
def test_source_literal_numbers_use_the_same_whole_token_scanner(source):
    validate("温度18.25℃", source)
    for claim in ("温度19.25℃", "温度25℃"):
        with pytest.raises(ValueError, match="quantitative"):
            validate(claim, source)


@pytest.mark.parametrize("text", ["传感器sensor_18.25待复核", "记录EV-18.25尚未复核", "模型v2.0.1已载入",
                                "安装123-ABC需复核", "记录2026-09-01T12:30:00Z需复核",
                                "记录2026/09/01 12:30:00+08:00需复核", "记录2026年9月1日需复核",
                                "时间12:30:00Z需复核"])
def test_identifiers_versions_and_dates_are_not_physical_number_assertions(text):
    assert _text_numbers(text) == []
    validate(text, {})


@pytest.mark.parametrize("source", [{"sensor_id": 25}, {"id": 25}, {"summary": "sensor_18.25"},
                                    {"measured_at": "2026-09-01T12:25:00Z"}])
def test_identifier_or_time_fragment_cannot_authorize_a_fabricated_physical_value(source):
    with pytest.raises(ValueError, match="quantitative"):
        validate("温度25℃", source)


def test_date_and_identifier_masking_preserves_adjacent_real_measurements():
    source = {"summary": "sensor_25于2026-09-01T12:30:00Z温度18.25℃，电压3.125V"}
    assert _text_numbers(source["summary"]) == [18.25, 3.125]
    validate("温度18.25℃，电压3.125V", source)
    with pytest.raises(ValueError, match="quantitative"):
        validate("温度18.25℃，电压3.25V", source)


@pytest.mark.parametrize("claim", ["Temperature 18.25.", "Temperature 18.25. Next observation pending.",
                                  "质量18.25kg", "质量18.25g", "长度18.25mm", "长度18.25m", "电阻18.25ohm"])
def test_sentence_periods_and_common_compact_units_keep_the_complete_quantity(claim):
    assert _text_numbers(claim) == [18.25]
    validate(claim, {"value": 18.25})
    with pytest.raises(ValueError, match="quantitative"):
        validate(claim.replace("18.25", "19.25"), {"value": 18.25})


@pytest.mark.parametrize("claim,values", [("温度18.25-20.25℃", [18.25, 20.25]),
                                         ("温度-20.25--18.25℃", [-20.25, -18.25]),
                                         ("Temperature 18.25 – 20.25 °C.", [18.25, 20.25])])
def test_numeric_ranges_check_both_endpoints_without_losing_signs(claim, values):
    assert _text_numbers(claim) == values
    validate(claim, {"values": values})
    with pytest.raises(ValueError, match="quantitative"):
        validate(claim, {"value": values[0]})


def test_nonfinite_exponent_cannot_disappear_from_a_physical_assertion():
    with pytest.raises(ValueError, match="nonfinite quantitative"):
        validate("温度1e309℃", {"value": 18.25})


def test_thousands_groups_form_one_complete_source_value():
    assert _text_numbers("容量1,000mAh，能量1,000.25Wh") == [1000, 1000.25]
    validate("容量1,000mAh", {"value": 1000})
    validate("容量1,000mAh", {"summary": "Capacity 1,000mAh"})
    with pytest.raises(ValueError, match="quantitative"):
        validate("容量1,000mAh", {"values": [1, 0]})
