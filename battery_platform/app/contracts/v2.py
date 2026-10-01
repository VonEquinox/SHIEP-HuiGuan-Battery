from __future__ import annotations

from typing import Any, Literal
from pydantic import Field, model_validator
from ..schemas import Strict


class AgentRunCreate(Strict):
    asset_id: int = Field(gt=0)
    installation_id: str = Field(min_length=1, max_length=160)
    visible_cutoff: str
    session_id: int | None = Field(default=None, gt=0)
    incident_group_id: int | None = Field(default=None, gt=0)
    round: int = Field(default=1, ge=1, le=20)
    prediction_id: int | None = Field(default=None, gt=0)


class ProposalCreate(Strict):
    report_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=160)
    asset_ids: list[int] = Field(default_factory=list, max_length=100)
    incident_group_id: int | None = Field(default=None, gt=0)
    primary_alert_id: int | None = Field(default=None, gt=0)
    allowed_tests: list[str] = Field(min_length=1, max_length=20)
    required_tests: list[str] = Field(default_factory=list, max_length=20)
    required_qualifications: list[str] = Field(default_factory=lambda: ["battery"], max_length=20)
    duration_minutes: int = Field(default=60, ge=1, le=1440)
    max_rounds: int = Field(default=3, ge=1, le=20)
    due_at: str | None = None
    expires_at: str | None = None
    severity: Literal["routine", "high", "critical"] = "routine"
    predecessors: list[int] = Field(default_factory=list, max_length=100)
    required_tools: dict[str, int] = Field(default_factory=dict, max_length=20)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_sets(self):
        for name in ("asset_ids", "allowed_tests", "required_tests", "required_qualifications", "predecessors"):
            value = getattr(self, name)
            if len(value) != len(set(value)):
                raise ValueError(f"{name} must not contain duplicates")
        if not set(self.required_tests).issubset(self.allowed_tests):
            raise ValueError("required_tests must be authorized")
        if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in self.required_tools.values()):
            raise ValueError("required_tools requires positive integer quantities")
        return self


class ProposalApprove(Strict):
    version: int = Field(ge=1)
    allowed_tests: list[str] | None = Field(default=None, min_length=1, max_length=20)
    required_tests: list[str] | None = Field(default=None, max_length=20)
    required_qualifications: list[str] | None = Field(default=None, min_length=1, max_length=20)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_rounds: int | None = Field(default=None, ge=1, le=20)
    due_at: str | None = None
    note: str = Field(default="", max_length=2000)


class VersionNote(Strict):
    version: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=2000)


class IncidentAnalyze(Strict):
    asset_ids: list[int] = Field(min_length=2, max_length=100)
    visible_cutoff: str
    window_minutes: int = Field(default=60, ge=1, le=10080)


class IncidentSplit(VersionNote):
    member_asset_ids: list[int] = Field(min_length=1, max_length=99)


class Measurement(Strict):
    metric: str = Field(min_length=1, max_length=80)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    method: str = Field(min_length=1, max_length=160)


class ComparisonContext(Strict):
    chemistry: Literal["LFP", "NCM", "NCA", "LCO", "LMO", "LTO", "unknown"]
    protocol_id: str = Field(min_length=1, max_length=160)
    load_condition: str = Field(min_length=1, max_length=160)
    temperature_condition: str = Field(min_length=1, max_length=160)
    source_cohort_id: str = Field(min_length=1, max_length=160)
    reference_status: Literal["not_reference", "declared_normal"] = "not_reference"

    @model_validator(mode="after")
    def nonblank_conditions(self):
        for field in ("protocol_id", "load_condition", "temperature_condition", "source_cohort_id"):
            if not getattr(self, field).strip():
                raise ValueError("comparison conditions must be explicitly declared")
        return self


class ObservationCreate(Strict):
    asset_id: int | None = Field(default=None, gt=0)
    installation_id: str = Field(min_length=1, max_length=160)
    round: int = Field(ge=1, le=20)
    order_version: int = Field(ge=1)
    test_id: str = Field(min_length=1, max_length=100)
    measured_at: str
    instrument_id: str = Field(default="not_recorded", min_length=1, max_length=160)
    calibration_status: Literal["calibrated", "unknown", "expired", "not_applicable"] = "unknown"
    measurements: list[Measurement] = Field(default_factory=list, max_length=100)
    comparison_context: ComparisonContext | None = None
    observed_symptoms: list[str] = Field(default_factory=list, max_length=30)
    performed_actions: list[str] = Field(default_factory=list, max_length=30)
    confirmed_hypotheses: list[str] = Field(default_factory=list, max_length=30)
    excluded_hypotheses: list[str] = Field(default_factory=list, max_length=30)
    unresolved_items: list[str] = Field(default_factory=list, max_length=30)
    free_text: str = Field(default="", max_length=12000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=20)
    assertion_targets: list[str] = Field(default_factory=list, max_length=30)
    result: Literal["observed", "inconclusive", "failed", "out_of_range", "refused", "requires_authorization"] = "observed"
    provenance: Literal["synthetic", "experimental_replay", "measured_declared"]
    client_submission_id: str = Field(min_length=8, max_length=128)


class RoundSubmit(Strict):
    order_version: int = Field(ge=1)
    installation_id: str = Field(min_length=1, max_length=160)
    client_submission_id: str = Field(min_length=8, max_length=128)


class FactsCorrection(Strict):
    version: int = Field(ge=1)
    candidate_facts: list[dict[str, Any]] = Field(max_length=100)
    note: str = Field(min_length=3, max_length=2000)


class DiagnosticFeedback(Strict):
    report_id: int = Field(gt=0)
    order_id: int | None = Field(default=None, gt=0)
    free_text: str = Field(min_length=3, max_length=12000)
    assertion_targets: list[str] = Field(default_factory=list, max_length=30)
    confirmed_hypotheses: list[str] = Field(default_factory=list, max_length=30)
    excluded_hypotheses: list[str] = Field(default_factory=list, max_length=30)
    unresolved_items: list[str] = Field(default_factory=list, max_length=30)
    provenance: Literal["synthetic", "experimental_replay", "measured_declared"]
    client_submission_id: str = Field(min_length=8, max_length=128)


class MobileLogin(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class QRVerify(Strict):
    token: str = Field(min_length=20, max_length=3000)


class SourceIngest(Strict):
    mode: Literal["metadata", "registered_local"] = "metadata"
    dataset_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def local_requires_dataset(self):
        if self.mode == "registered_local" and self.dataset_id is None:
            raise ValueError("registered_local requires dataset_id")
        return self


class ModelRunCreate(Strict):
    kind: Literal["training", "evaluation", "inference", "v2_training", "v2_calibration", "v2_evaluation", "v2_export", "v2_inference"]
    dataset_id: int | None = Field(default=None, gt=0)
    model_id: int | None = Field(default=None, gt=0)
    asset_id: int | None = Field(default=None, gt=0)
    cell_id: str | None = None
    sample_ids: list[int] = Field(default_factory=list, max_length=256)
    min_samples_leaf: int = Field(default=3, ge=1, le=16)
    n_estimators: int = Field(default=100, ge=30, le=300)
    run_id: str | None = Field(default=None, max_length=500)
    family: Literal["M1", "M2"] = "M1"
    seed: int = Field(default=0, ge=0, le=2)
    ablation: Literal["joint", "no_domain_adapter", "no_history", "single_task"] = "joint"


class V2Binding(Strict):
    version: int = Field(ge=1)
    installation_id: str = Field(min_length=1, max_length=160)
    package_id: str = Field(min_length=1, max_length=160)
    row_index: int = Field(ge=0)


class EvolutionExperiment(Strict):
    method: Literal["ace", "reflexion", "gepa", "fixed", "no_memory"] = "ace"
    base_version: int = Field(ge=0)
    case_ids: list[str] = Field(min_length=1, max_length=200)
    split: Literal["evolution", "dev", "sealed_test"] = "dev"
    max_rollouts: int = Field(default=20, ge=1, le=200)
    activate: bool = False


class ContextRollback(Strict):
    base_version: int = Field(ge=0)
    snapshot_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=2000)


class ContextRegression(Strict):
    base_version: int = Field(ge=0)
    selection_count: int = Field(default=5, ge=1, le=20)
    max_rollouts: int = Field(default=10, ge=2, le=40)
