from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Login(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserCreate(Strict):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "researcher", "dispatcher", "technician", "viewer"]


class UserUpdate(Strict):
    version: int
    role: Literal["admin", "researcher", "dispatcher", "technician", "viewer"]
    active: bool = True


class PasswordUpdate(Strict):
    new_password: str = Field(min_length=12, max_length=128)
    current_password: str | None = Field(default=None, max_length=128)


class AssetCreate(Strict):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["site", "cabinet", "module", "cell"]
    parent_id: int | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location: str = Field(default="", max_length=300)


class AssetUpdate(Strict):
    version: int
    name: str = Field(min_length=1, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location: str = Field(default="", max_length=300)


class Binding(Strict):
    dataset_id: int
    cell_id: str = Field(min_length=1, max_length=160)


class JobCreate(Strict):
    kind: Literal["inference", "evaluation", "training"]
    dataset_id: int
    model_id: int | None = None
    sample_ids: list[int] = Field(default_factory=list, max_length=256)
    cell_id: str | None = None
    asset_id: int | None = None
    min_samples_leaf: int = Field(default=3, ge=1, le=16)
    n_estimators: int = Field(default=100, ge=30, le=300)


class Transition(Strict):
    version: int
    action: Literal[
        "assign",
        "accept",
        "start",
        "resolve",
        "verify",
        "close",
        "reject",
        "reopen",
        "cancel",
    ]
    assignee_id: int | None = None
    note: str = Field(default="", max_length=2000)


class AlertAction(Strict):
    version: int
    action: Literal["acknowledge", "resolve", "reopen"]
    note: str = Field(default="", max_length=1000)


class PolicyCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    threshold: float = Field(ge=0.1, le=1.5)
    persistence: int = Field(default=2, ge=1, le=20)
    cooldown_seconds: int = Field(default=3600, ge=0, le=604800)
    stale_seconds: int = Field(default=86400, ge=60, le=31536000)


class PersonnelUpdate(Strict):
    user_id: int
    skills: list[str] = Field(default_factory=lambda: ["battery"], max_length=10)
    on_call: bool = True
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    max_workload: int = Field(default=4, ge=1, le=20)


class FeedbackCreate(Strict):
    prediction_id: int
    order_id: int | None = None
    value: float = Field(gt=0, le=2)
    provenance: Literal["simulated", "measured_declared"]
    source: str = Field(min_length=3, max_length=300)
    measured_at: str
    note: str = Field(default="", max_length=2000)


class DemoEvent(Strict):
    asset_id: int
    scenario: Literal["capacity-review", "sensor-temperature", "communication-loss"]


class VersionAction(Strict):
    version: int
    note: str = Field(default="", max_length=500)
