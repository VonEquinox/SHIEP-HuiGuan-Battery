from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
Nonnegative = Annotated[Number, Field(ge=0)]
Unit = Literal["kWh", "kg", "t_km", "battery_unit", "rated_kWh", "test_unit"]
Gas = Literal["kgCO2", "kgCO2e"]
Provenance = Literal["real", "synthetic", "unverified"]
Text = Annotated[str, Field(min_length=1, max_length=500)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Factor(Strict):
    code: Text
    version: Text
    value: Nonnegative
    activity_unit: Unit
    gas_scope: Gas
    boundary: Text
    source_url: Text
    source_title: Text
    jurisdiction: Text
    valid_from: date
    valid_to: date
    deviation: Nonnegative = 0
    uncertainty_key: str = Field(default="", max_length=200)
    provenance: Provenance = "unverified"
    synthetic_scenario_id: str | None = Field(default=None, max_length=200)
    review_status: Literal["unverified", "verified"] = "unverified"

    @model_validator(mode="after")
    def check(self):
        from urllib.parse import urlparse
        url = urlparse(self.source_url)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise ValueError("factor requires an explicit HTTP(S) source URL")
        if self.valid_to < self.valid_from:
            raise ValueError("factor validity interval is reversed")
        if self.deviation > self.value:
            raise ValueError("symmetric factor range must not permit negative emissions")
        if self.deviation and not self.uncertainty_key:
            raise ValueError("factor deviation requires a shared uncertainty key")
        if self.provenance == "synthetic" and not self.synthetic_scenario_id:
            raise ValueError("synthetic factor requires a scenario ID")
        return self


class FunctionalUnit(Strict):
    output_kwh_per_period: list[Nonnegative] = Field(min_length=1, max_length=120)
    period_years: Annotated[Number, Field(gt=0, le=10)] = 1
    start_date: date
    region: Text
    usage_scenario: Text
    service_requirements: Text
    start_state: Text
    terminal_handling: Text
    boundary: list[Text] = Field(min_length=1, max_length=30)
    gas_scope: Gas
    baseline_basis: Text
    accounting_method: Text = "explicit_activity_inventory_v1"
    boundary_kind: Literal["prospective_decision", "product_lifecycle", "activity_only"] = "prospective_decision"
    manufacturing_history_treatment: Text = "shared historical manufacture treated as sunk in prospective comparison"


class Activity(Strict):
    process: Text
    period: int = Field(ge=1, le=120)
    quantity: Nonnegative
    unit: Unit
    factor_id: int = Field(gt=0)
    basis: Literal["projected", "settled"]
    provenance: Provenance
    source_reference: Text
    source_version: Text
    prediction_id: int | None = Field(default=None, gt=0)
    credit: bool = False
    allocation_method: str | None = Field(default=None, max_length=500)
    material_flow_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def credit_evidence(self):
        if self.credit and (not self.allocation_method or not self.material_flow_id):
            raise ValueError("recovery credit requires allocation method and material-flow identity")
        return self


class State(Strict):
    name: Text
    age_years: Nonnegative
    cohort: Literal["existing", "new"]
    available: bool
    efficiency: Annotated[Number, Field(gt=0, le=1)]
    health: Annotated[Number, Field(ge=0, le=1)]


class ReplacementEdge(Strict):
    period: int = Field(ge=1, le=120)
    source: int = Field(ge=0)
    destination: int = Field(ge=0)


class StateModel(Strict):
    states: list[State] = Field(min_length=1, max_length=32)
    initial_distribution: list[Nonnegative] = Field(min_length=1, max_length=32)
    transitions: list[list[list[Nonnegative]]] = Field(min_length=1, max_length=120)
    replacement_edges: list[ReplacementEdge] = Field(default_factory=list, max_length=4000)
    new_initial_distribution: list[Nonnegative] | None = None
    initial_replacement_count: Nonnegative = 0
    energy_factor_id: int = Field(gt=0)
    replacement_factor_id: int | None = Field(default=None, gt=0)
    rated_capacity_kwh: Annotated[Number, Field(gt=0)] | None = None
    auxiliary_kwh_per_period: list[Nonnegative] = Field(default_factory=list, max_length=120)
    auxiliary_in_efficiency: bool = False
    standby_efficiency: Annotated[Number, Field(gt=0, le=1)] | None = None
    parameter_origin: Literal["measured", "user_scenario", "validated_model", "validated_intervention"]
    parameter_evidence: Text
    model_applicable: bool | None = None
    parameter_prediction_output_ids: list[int] = Field(default_factory=list, max_length=30)


class Constraints(Strict):
    safety: bool | None = None
    technical: bool | None = None
    service: bool | None = None
    personnel: bool | None = None
    scenario: bool | None = None


class CostPeriod(Strict):
    period: int = Field(ge=1, le=120)
    energy: Nonnegative = 0
    inspection: Nonnegative = 0
    labor: Nonnegative = 0
    replacement: Nonnegative = 0
    downtime: Nonnegative = 0
    other: Nonnegative = 0
    downtime_basis: str | None = None
    uncertainty_coefficients: dict[str, Number] = Field(default_factory=dict, max_length=30)
    embedded_benefit_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def basis_required(self):
        if self.downtime and not self.downtime_basis:
            raise ValueError("downtime valuation requires a basis")
        return self


class CashFlow(Strict):
    initial_cost: Nonnegative = 0
    discount_rate: Annotated[Number, Field(gt=-1, le=1)] = 0
    flows: list[CostPeriod] = Field(default_factory=list, max_length=120)
    residual_value: Nonnegative = 0
    residual_basis: str | None = None
    energy_price_per_kwh: Nonnegative | None = None
    energy_price_deviation: Nonnegative = 0
    energy_price_uncertainty_key: str = ""
    price_year: int = Field(ge=1900, le=2200)
    currency: Literal["RMB"] = "RMB"
    quote_reference: Text

    @model_validator(mode="after")
    def evidence(self):
        if self.residual_value and not self.residual_basis:
            raise ValueError("residual value requires a source and terminal valuation basis")
        if self.energy_price_deviation and (
            self.energy_price_per_kwh is None
            or self.energy_price_deviation > self.energy_price_per_kwh
            or not self.energy_price_uncertainty_key
        ):
            raise ValueError("energy-price range requires a nonnegative price and uncertainty key")
        return self


class PolicyRule(Strict):
    rule_id: Text
    version: Text
    official_url: Text
    jurisdiction: Text
    eligible_entity: Text
    technology_conditions: list[Text] = Field(default_factory=list, max_length=30)
    valid_from: date
    valid_to: date
    formula: Literal["documented_fixed_amount"] = "documented_fixed_amount"
    cap: Nonnegative
    required_documents: list[Text] = Field(min_length=1, max_length=30)
    review_status: Literal["unverified", "verified", "withdrawn"] = "unverified"
    effective: bool = False
    provenance: Provenance = "unverified"

    @model_validator(mode="after")
    def source(self):
        from urllib.parse import urlparse
        p = urlparse(self.official_url)
        if p.scheme != "https" or not p.netloc or self.valid_from > self.valid_to:
            raise ValueError("policy requires an HTTPS official URL and valid date interval")
        return self


class PolicyBenefit(Strict):
    id: Text
    rule_version_id: int = Field(gt=0)
    period: int = Field(ge=1, le=120)
    amount: Nonnegative
    entity: Text
    documents: dict[str, Text] = Field(default_factory=dict, max_length=30)
    conditions: dict[str, bool | None] = Field(default_factory=dict, max_length=30)
    trade_or_grant_reference: str | None = None
    receipt_reference: str | None = None


class Candidate(Strict):
    id: Text
    label: Text
    intervention: Literal["continue", "inspect", "repair", "replace_module", "replace_pack", "second_life", "recycle"]
    constraints: Constraints
    functional_unit_matches: bool | None
    confirmed_by: Text
    confirmation_reference: Text
    activities: list[Activity] = Field(default_factory=list, max_length=1000)
    state_model: StateModel | None = None
    costs: CashFlow
    policy_benefits: list[PolicyBenefit] = Field(default_factory=list, max_length=30)


class Scenario(Strict):
    name: Text
    version: int = Field(default=1, ge=1)
    functional_unit: FunctionalUnit
    baseline_id: Text
    candidates: list[Candidate] = Field(min_length=2, max_length=32)
    basis: Literal["projected", "settled"]
    claim_type: Literal["activity_emission", "product_footprint", "comparative_avoided"] = "comparative_avoided"
    provenance: Provenance
    synthetic_scenario_id: str | None = None
    gamma: Nonnegative = 0
    gamma_scan: list[Nonnegative] = Field(default_factory=list, max_length=32)
    epsilon_values: list[Number] = Field(default_factory=list, max_length=128)
    shadow_price_rmb_per_t: Nonnegative = 0
    parent_scenario_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def identity(self):
        names = [c.id for c in self.candidates]
        if len(names) != len(set(names)) or self.baseline_id not in names:
            raise ValueError("candidate IDs must be unique and contain the baseline")
        if self.provenance == "synthetic" and not self.synthetic_scenario_id:
            raise ValueError("synthetic scenario requires explicit scenario ID")
        if len(self.functional_unit.boundary) != len(set(self.functional_unit.boundary)):
            raise ValueError("accounting boundaries must be unique")
        expected = {"activity_emission": "activity_only", "product_footprint": "product_lifecycle", "comparative_avoided": "prospective_decision"}
        if self.functional_unit.boundary_kind != expected[self.claim_type]:
            raise ValueError("claim type must use its explicit activity/product/prospective boundary")
        if self.claim_type == "product_footprint" and "sunk" in self.functional_unit.manufacturing_history_treatment.lower():
            raise ValueError("product footprint must explicitly account for historical manufacture under its chosen methodology")
        return self


class SolveRequest(Strict):
    expected_version: int = Field(ge=1)
    gamma: Nonnegative | None = None


class LedgerRequest(Strict):
    result_id: int = Field(gt=0)
    candidate_id: Text
    claim_type: Literal["activity_emission", "product_footprint", "comparative_avoided"]
    basis: Literal["projected", "settled"]
    review_status: Literal["pending", "reviewed", "rejected"] = "pending"
    evidence_reference: Text
    accounting_period: Text


class ReversalRequest(Strict):
    reason: Text
