from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EngineerResource(Strict):
    id: int = Field(gt=0)
    shifts: list[tuple[int, int]] = Field(max_length=30)
    max_minutes: int = Field(default=480, ge=0, le=10080)
    home_location: str = Field(min_length=1, max_length=120)

    @field_validator("home_location")
    @classmethod
    def valid_location(cls, value):
        if not value.strip() or "|" in value:
            raise ValueError("起始地点必须明确且不含|分隔符")
        return value

    @field_validator("shifts")
    @classmethod
    def valid_shifts(cls, value):
        if any(s < 0 or f <= s or f > 10080 for s, f in value):
            raise ValueError("班次须为0–10080分钟内的非空区间")
        if any(a[1] > b[0] for a, b in zip(sorted(value), sorted(value)[1:])):
            raise ValueError("班次不能重叠")
        return sorted(value)


class ResourcePayload(Strict):
    engineers: list[EngineerResource] = Field(default_factory=list, max_length=30)
    tool_capacities: dict[str, int] = Field(default_factory=dict, max_length=30)
    tool_windows: dict[str, list[tuple[int, int]]] = Field(default_factory=dict, max_length=30)
    travel_minutes: dict[str, int] = Field(default_factory=dict, max_length=900)
    provenance: Literal["simulated", "declared"] = "declared"
    scenario_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def bounded(self):
        if len({e.id for e in self.engineers}) != len(self.engineers):
            raise ValueError("工程师编号重复")
        if any(not k or len(k) > 120 or "|" in k or not isinstance(v, int) or not 0 <= v <= 100 for k, v in self.tool_capacities.items()):
            raise ValueError("工具容量无效")
        if any(k.count("|") != 1 or len(k) > 241 or not isinstance(v, int) or not 0 <= v <= 10080 for k, v in self.travel_minutes.items()):
            raise ValueError("地点转换须为地点|地点和非负分钟")
        if any(k not in self.tool_capacities or len(w) > 30 or any(s < 0 or f <= s or f > 10080 for s, f in w) for k, w in self.tool_windows.items()):
            raise ValueError("工具可用时段必须对应容量且为有效区间")
        if self.provenance == "simulated" and not self.scenario_id:
            raise ValueError("模拟资源必须标注scenario_id")
        return self


class ResourceUpdate(Strict):
    version: int = Field(ge=1)
    payload: ResourcePayload


class PlanCreate(Strict):
    order_ids: list[int] = Field(min_length=1, max_length=40)
    horizon_start: datetime
    horizon_minutes: int = Field(default=480, ge=1, le=10080)
    time_limit_seconds: float = Field(default=10, gt=0, le=30)

    @model_validator(mode="after")
    def valid(self):
        if self.horizon_start.tzinfo is None:
            raise ValueError("horizon_start必须带时区")
        if len(set(self.order_ids)) != len(self.order_ids) or any(i < 1 for i in self.order_ids):
            raise ValueError("工单编号必须为不重复正整数")
        return self


class RequirementUpdate(Strict):
    version: int = Field(ge=0)
    required_qualifications: list[str] = Field(default_factory=list, max_length=30)
    duration_minutes: int = Field(default=60, ge=1, le=10080)
    due_at: datetime | None = None
    release_at: datetime | None = None
    severity: Literal["routine", "high", "critical"] = "routine"
    hard_deadline: bool = False
    predecessors: list[int] = Field(default_factory=list, max_length=40)
    required_tools: dict[str, int] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def valid(self):
        for date in (self.due_at, self.release_at):
            if date is not None and date.tzinfo is None:
                raise ValueError("任务时间必须带时区")
        if any(not s or len(s) > 80 for s in self.required_qualifications):
            raise ValueError("资格标签无效")
        if len(set(self.predecessors)) != len(self.predecessors) or any(i < 1 for i in self.predecessors):
            raise ValueError("前置任务无效")
        if any(not k or len(k) > 120 or not 1 <= v <= 100 for k, v in self.required_tools.items()):
            raise ValueError("工具需求无效")
        return self


class Assignment(Strict):
    order_id: int = Field(gt=0)
    engineer_id: int = Field(gt=0)
    start: int = Field(ge=0, le=10080)
    end: int = Field(ge=1, le=10080)


class PlanEdit(Strict):
    version: int = Field(ge=1)
    assignments: list[Assignment] = Field(max_length=40)


class PlanConfirm(Strict):
    version: int = Field(ge=1)
