"""Strict structured reports and server-side temporal/citation boundaries."""
from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TOOL_WHITELIST = frozenset({"get_asset_context", "get_signal_evidence", "read_prediction",
                          "get_peer_anomalies", "search_knowledge", "load_skill", "search_memory",
                          "rank_tests", "propose_work_order", "append_report"})
FORBIDDEN_CONTEXT_KEYS = frozenset({"hidden_truth", "hidden", "oracle", "branches", "expected_behavior",
                                    "expected_feedback", "future_observations", "final_root_cause",
                                    "sealed", "sealed_labels", "loss_matrix", "likelihoods"})
EDITABLE_SKILL_FIELDS = frozenset({"instructions", "routing_description", "evidence_checklist",
                                  "retrieval_query_template", "inspection_selection_hints"})


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Fact(Strict):
    claim: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)


class Hypothesis(Strict):
    code: str = Field(min_length=1, max_length=150)
    level: Literal["confirmed", "suspected", "insufficient_evidence", "unsupported"]
    supports: list[str] = Field(default_factory=list, max_length=30)
    contradicts: list[str] = Field(default_factory=list, max_length=30)
    probability: float | None = Field(default=None, ge=0, le=1)
    probability_source: str | None = None


class SuggestedTest(Strict):
    test_id: str = Field(min_length=1, max_length=150)
    reason: str = Field(min_length=1, max_length=1000)
    authorization: Literal["authorized", "required"] = "required"


class Priority(Strict):
    model_config = ConfigDict(extra="forbid")
    class_: Literal["routine", "needs_inspection", "urgent_review", "unsupported"] = Field(alias="class")
    reason: str = Field(min_length=1, max_length=1000)


class AgentReport(Strict):
    report_id: str
    asset_id: str | int
    installation_id: str
    visible_cutoff: str
    round: int = Field(ge=1)
    status: Literal["confirmed", "suspected", "insufficient_evidence", "unsupported"]
    facts: list[Fact] = Field(default_factory=list, max_length=100)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=30)
    unknowns: list[str] = Field(default_factory=list, max_length=100)
    applicability: dict[str, Any] = Field(default_factory=dict)
    suggested_tests: list[SuggestedTest] = Field(default_factory=list, max_length=30)
    priority: Priority
    proposal_id: str | None = None
    citations: list[str] = Field(default_factory=list, max_length=100)
    agent_version: str = "single-agent-v2.0"
    context_version: str


def parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    # Legacy API measurements are UTC when no offset is stored.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def public_context(value: Any, *, cutoff: str, installation_id: str) -> Any:
    """Allowlist-like recursive sanitation removes hidden and unreachable material.

    A row with a timestamp after cutoff, or another installation, is discarded.
    Both acquisition time and availability time are checked: backdated uploads
    cannot become visible before the server has actually received them.
    """
    deadline = parse_time(cutoff)

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            if item.get("installation_id") is not None and str(item["installation_id"]) != str(installation_id):
                return None
            source_ordinal_query = (item.get("time_basis") == "source_record_ordinal" and bool(item.get("source_id"))
                                    and isinstance(item.get("visible_cutoff"), (int, float)))
            for key in ("measured_at", "available_at", "received_at", "visible_at", "query_time", "visible_cutoff", "timestamp"):
                if item.get(key) is not None:
                    if (key in {"query_time", "visible_cutoff"} or key == "available_at" and source_ordinal_query) and isinstance(item[key], (int, float)):
                        # Numerical-model source coordinates (cycles/sample time)
                        # are separate from server ISO observation availability.
                        if not any(k in item for k in ("feature_max_time", "feature_schema", "source_id", "physical_cell_id", "allowed_heads")):
                            raise ValueError("numeric model time needs an explicit source-coordinate query")
                        if not math.isfinite(float(item[key])):
                            raise ValueError("nonfinite model time")
                        continue
                    if parse_time(item[key]) > deadline:
                        return None
            if isinstance(item.get("visible_cutoff"), (int, float)):
                for key in ("feature_max_time", "reference_cutoff", "available_at"):
                    if item.get(key) is not None and isinstance(item[key], (int, float)):
                        if not math.isfinite(float(item[key])) or float(item[key]) > item["visible_cutoff"]:
                            return None
                if isinstance(item.get("query_time"), (int, float)) and item["query_time"] < item["visible_cutoff"]:
                    raise ValueError("source cutoff cannot follow the model query coordinate")
            return {k: cleaned for k, val in item.items()
                    if k not in FORBIDDEN_CONTEXT_KEYS and not k.startswith("hidden_") and not k.startswith("sealed_")
                    and (cleaned := clean(val)) is not None}
        if isinstance(item, list):
            return [cleaned for val in item if (cleaned := clean(val)) is not None]
        if isinstance(item, (str, bool, int)) or item is None:
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("nonfinite context value")
            return item
        raise ValueError("context must be JSON-compatible")

    return clean(copy.deepcopy(value))


def validate_report(report: dict[str, Any], *, evidence_ids: set[str], test_ids: set[str],
                    installation_id: str, cutoff: str, probability_authorities: dict[str, float] | None = None,
                    authorized_test_ids: set[str] | None = None,
                    evidence_records: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed = AgentReport.model_validate(report)
    if parsed.installation_id != str(installation_id) or parse_time(parsed.visible_cutoff) != parse_time(cutoff):
        raise ValueError("report identity or cutoff mismatch")
    refs = set(parsed.citations)
    for fact in parsed.facts:
        refs.update(fact.evidence_ids)
        if evidence_records is not None:
            # Quantitative assertions must repeat program/measurement numbers.
            # Text conclusions still require separate semantic/expert review.
            numeric_tokens = re.findall(r"(?<![\w-])[-+]?\d+(?:\.\d+)?(?![\w-])", fact.claim)
            source_numbers: set[float] = set()
            def collect_numbers(value):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    source_numbers.add(float(value))
                elif isinstance(value, dict):
                    for child in value.values():
                        collect_numbers(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_numbers(child)
                elif isinstance(value, str):
                    source_numbers.update(float(v) for v in re.findall(r"(?<![\w-])[-+]?\d+(?:\.\d+)?(?![\w-])", value))
            for eid in fact.evidence_ids:
                collect_numbers((evidence_records or {}).get(eid, {}))
            if any(not any(math.isclose(float(n), source, abs_tol=1e-9) for source in source_numbers) for n in numeric_tokens):
                raise ValueError("quantitative assertion is not present in its cited evidence")
    for h in parsed.hypotheses:
        refs.update(h.supports)
        refs.update(h.contradicts)
        if h.level == "confirmed" and not h.supports:
            raise ValueError("confirmed hypothesis needs supporting evidence")
        if h.level == "confirmed" and evidence_records is not None:
            verified = any((evidence_records.get(eid, {}).get("verification_status") == "independently_verified"
                            or evidence_records.get(eid, {}).get("source_trust") == "independently_verified"
                            or evidence_records.get(eid, {}).get("provenance") == "independently_verified") for eid in h.supports)
            if not verified:
                raise ValueError("reported or unverified evidence cannot confirm a root cause")
        if h.probability is not None:
            authority = (probability_authorities or {}).get(h.probability_source or "")
            if authority is None or not math.isclose(h.probability, authority, abs_tol=1e-9):
                raise ValueError("hypothesis probability must come from a calibrated numerical authority")
    if not refs <= evidence_ids:
        raise ValueError("unknown, future, or unauthorized citation")
    if parsed.status == "confirmed" and not any(h.level == "confirmed" for h in parsed.hypotheses):
        raise ValueError("confirmed report needs a confirmed hypothesis")
    for test in parsed.suggested_tests:
        if test.test_id not in test_ids:
            raise ValueError("unknown test identifier")
        if test.authorization == "authorized" and test.test_id not in (authorized_test_ids or set()):
            raise ValueError("test is outside existing authorization")
    return parsed.model_dump(by_alias=True)
