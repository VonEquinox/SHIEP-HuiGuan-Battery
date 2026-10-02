"""Versioned scorer metrics and the public UI catalog share one wire contract."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

METRICS_VERSION = "experiment-metrics.v1"
PROTOCOL_VERSION = "root-replay.v1"


class MetricDenominators(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    diagnosis_roots: int | None = Field(default=None, ge=0)
    facts: int | None = Field(default=None, ge=0)
    independently_labeled_roots: int | None = Field(default=None, ge=0)
    inspection_positive_roots: int | None = Field(default=None, ge=0)
    inspection_negative_roots: int | None = Field(default=None, ge=0)


class ExperimentMetrics(BaseModel):
    """Scalars are never inferred by renaming a count into a rate.

    Nullable denominators permit an honest projection of old archived results.
    New evaluator output always supplies its exact scorer-only denominators.
    """
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["experiment-metrics.v1"] = METRICS_VERSION
    diagnosis_accuracy: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    grounded_assertion_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    mean_test_count: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    unsafe_test_count: int | None = Field(default=None, ge=0)
    independently_labeled_root_count: int | None = Field(default=None, ge=0)
    misses: int | None = Field(default=None, ge=0)
    false_alarms: int | None = Field(default=None, ge=0)
    miss_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    false_positive_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    denominators: MetricDenominators = Field(default_factory=MetricDenominators)

    @model_validator(mode="after")
    def rate_requires_matching_denominator(self):
        for rate, count, denominator in (
            (self.miss_rate, self.misses, self.denominators.inspection_positive_roots),
            (self.false_positive_rate, self.false_alarms, self.denominators.inspection_negative_roots),
        ):
            if rate is not None and (count is None or denominator in (None, 0) or not math.isclose(rate, count / denominator)):
                raise ValueError("rate requires its labeled denominator and matching event count")
        return self


_DEFINITIONS = [
    {"key": "grounded_assertion_ratio", "label": "有依据的事实比例", "kind": "ratio", "unit": "比例 (0–1)", "denominator": "facts", "denominator_label": "报告事实数"},
    {"key": "diagnosis_accuracy", "label": "诊断准确率", "kind": "ratio", "unit": "比例 (0–1)", "denominator": "diagnosis_roots", "denominator_label": "已评估根事件数"},
    {"key": "false_alarms", "label": "误报数", "kind": "count", "unit": "根事件", "denominator": "inspection_negative_roots", "denominator_label": "独立标注无需检查根事件数"},
    {"key": "misses", "label": "漏报数", "kind": "count", "unit": "根事件", "denominator": "inspection_positive_roots", "denominator_label": "独立标注需检查根事件数"},
    {"key": "false_positive_rate", "label": "误报率", "kind": "ratio", "unit": "比例 (0–1)", "denominator": "inspection_negative_roots", "denominator_label": "独立标注无需检查根事件数"},
    {"key": "miss_rate", "label": "漏报率", "kind": "ratio", "unit": "比例 (0–1)", "denominator": "inspection_positive_roots", "denominator_label": "独立标注需检查根事件数"},
    {"key": "mean_test_count", "label": "平均建议检查数", "kind": "mean_count", "unit": "项 / 根事件", "denominator": "diagnosis_roots", "denominator_label": "已评估根事件数"},
    {"key": "unsafe_test_count", "label": "不安全检查建议数", "kind": "count", "unit": "项", "denominator": "diagnosis_roots", "denominator_label": "已评估根事件数"},
    {"key": "score", "label": "综合分数", "kind": "unsupported", "unit": "未支持", "denominator": None, "denominator_label": None,
     "unsupported_reason": "普通根事件 ReplayEvaluator 未定义综合分数；GEPA 选择分数属于独立选择协议，不能串接为本曲线。"},
]


def metrics_contract() -> dict[str, Any]:
    return {"schema_version": METRICS_VERSION, "definitions": _DEFINITIONS,
            "schema": ExperimentMetrics.model_json_schema()}


def aggregate_experiment_metrics(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [(record, case) for record, case in zip(records, cases) if record["metrics"]["missed"] is not None]
    facts = sum(record["metrics"]["fact_count"] for record in records)
    positive = sum(bool(case.get("hidden_truth", case.get("oracle", {}).get("hidden_truth", {})).get("requires_inspection")) for _, case in labeled)
    negative = len(labeled) - positive
    misses = sum(record["metrics"]["missed"] for record, _ in labeled) if labeled else None
    false_alarms = sum(record["metrics"]["false_alarm"] for record, _ in labeled) if labeled else None
    return ExperimentMetrics(
        diagnosis_accuracy=sum(record["metrics"]["diagnosis_correct"] for record in records) / len(records) if records else None,
        grounded_assertion_ratio=sum(record["metrics"]["grounded_fact_count"] for record in records) / facts if facts else None,
        mean_test_count=sum(record["metrics"]["test_count"] for record in records) / len(records) if records else None,
        unsafe_test_count=sum(record["metrics"]["unsafe_test_count"] for record in records),
        independently_labeled_root_count=len(labeled), misses=misses, false_alarms=false_alarms,
        miss_rate=misses / positive if positive else None,
        false_positive_rate=false_alarms / negative if negative else None,
        denominators=MetricDenominators(diagnosis_roots=len(records), facts=facts,
            independently_labeled_roots=len(labeled), inspection_positive_roots=positive,
            inspection_negative_roots=negative),
    ).model_dump()


def public_metrics(stored: dict[str, Any]) -> dict[str, Any]:
    """Project only valid measured keys; operational/search telemetry is separate."""
    fields = ExperimentMetrics.model_fields
    selected = {key: value for key, value in stored.items() if key in fields}
    try:
        values = ExperimentMetrics.model_validate(selected).model_dump()
        invalid_reason = None
    except ValueError:
        values = ExperimentMetrics().model_dump()
        invalid_reason = "已归档指标不符合 ExperimentMetrics 契约，未作为数值绘图。"
    legacy = stored.get("schema_version") != METRICS_VERSION
    unsupported = {}
    for definition in _DEFINITIONS:
        key = definition["key"]
        if definition["kind"] == "unsupported":
            unsupported[key] = definition["unsupported_reason"]
        elif values.get(key) is None:
            unsupported[key] = invalid_reason or (
                "缺少独立正/负标签分母，未计算该比率。" if key in ("miss_rate", "false_positive_rate")
                else "本实验没有测量该指标或没有合格分母。")
    return {"schema_version": METRICS_VERSION, "measurement_version": "legacy-replay-metrics" if legacy else METRICS_VERSION,
            "values": values, "unsupported": unsupported, "legacy_denominators": legacy}
