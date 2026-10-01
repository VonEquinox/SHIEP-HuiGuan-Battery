"""Compare two complete Context snapshots on one independent dev selection.

This service never publishes, activates, or rolls back a snapshot. The caller
performs a final cancellation/CAS check before acting on the returned evidence.
Only the existing dev scorer can read evaluator labels; runtime input remains
its public projection and sealed files are never opened by this service.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Callable

from .contracts import EDITABLE_SKILL_FIELDS, FORBIDDEN_CONTEXT_KEYS, TOOL_WHITELIST, parse_time
from .evaluation import validate_skill_candidate
from .executor import run_agent
from .gepa_service import DevSelectionScorer, FrozenSkills
from .llm import LLMError, OpenAICompatibleClient
from .skills import SkillLibrary


_SNAPSHOT_KEYS = {"context_snapshot_id", "context_version", "version", "memories", "skills",
                  "created_at", "changes", "parent_snapshot_id"}
_MEMORY_KEYS = {"memory_id", "version", "scope", "trigger", "insight", "supporting_case_ids",
                "counterexamples", "source_trust", "helpful_count", "harmful_count", "last_used",
                "expires_at", "state", "source_scope", "raw_feedback_id", "available_at", "origin",
                "revision_provenance", "deprecation_reason", "conflicts", "allowed_tools"}
_TRUST = {"reported", "measurement_supported", "independently_verified", "contradicted"}
_SCOPE = {"operational", "cold_start", "evolution"}
_STATE = {"active", "conflicted", "deprecated", "quarantined"}
_PERMISSION_KEYS = {"tools", "tool_schema", "tool_schemas", "permissions", "approval_permissions",
                    "authorization", "role", "roles", "safety_constraints", "carbon_method", "split"}
_USAGE_KEYS = {"prompt_tokens", "completion_tokens", "total_tokens"}


def _text(value: Any, *, empty: bool = False) -> bool:
    return isinstance(value, str) and (empty or bool(value.strip()))


def _integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _time(value: Any) -> bool:
    if not _text(value):
        return False
    try:
        parse_time(value)
        return True
    except (ValueError, TypeError, OverflowError):
        return False


def _strings(value: Any, *, empty: bool = True) -> bool:
    return isinstance(value, list) and (empty or bool(value)) and all(_text(item) for item in value)


def _validate_snapshot(snapshot: Any) -> list[str]:
    """Validate before hydration; return fixed diagnostic codes, never prose."""
    if not isinstance(snapshot, dict):
        return ["snapshot_not_object"]
    errors: list[str] = []
    try:
        json.dumps(snapshot, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return ["snapshot_not_finite_json"]

    def inspect(value: Any):
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    errors.append("snapshot_key_not_text")
                    continue
                if key in FORBIDDEN_CONTEXT_KEYS or key.startswith(("hidden_", "sealed_")):
                    errors.append("snapshot_contains_evaluator_material")
                if key in _PERMISSION_KEYS:
                    errors.append("snapshot_contains_immutable_permission_or_protocol_field")
                if key == "allowed_tools" and (not _strings(item) or not set(item) <= TOOL_WHITELIST):
                    errors.append("snapshot_widens_tool_permissions")
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    inspect(snapshot)
    if set(snapshot) - _SNAPSHOT_KEYS:
        errors.append("snapshot_contains_noneditable_fields")
    version = snapshot.get("version")
    if not _integer(version):
        errors.append("snapshot_version_invalid")
    if not _text(snapshot.get("context_snapshot_id")):
        errors.append("snapshot_identity_invalid")
    if snapshot.get("context_version") != f"context_v{version}":
        errors.append("snapshot_context_version_mismatch")
    if "created_at" in snapshot and not _time(snapshot["created_at"]):
        errors.append("snapshot_created_at_invalid")
    if snapshot.get("parent_snapshot_id") is not None and not _text(snapshot["parent_snapshot_id"]):
        errors.append("snapshot_parent_invalid")
    if "changes" in snapshot and (not isinstance(snapshot["changes"], list)
                                   or any(not isinstance(change, dict) for change in snapshot["changes"])):
        errors.append("snapshot_changes_invalid")
    skills = snapshot.get("skills")
    if not isinstance(skills, dict):
        errors.append("snapshot_skills_invalid")
    else:
        for skill_id, fields in skills.items():
            if not _text(skill_id) or not isinstance(fields, dict):
                errors.append("snapshot_skill_overlay_invalid")
                continue
            if not set(fields) <= EDITABLE_SKILL_FIELDS:
                errors.append("snapshot_skill_overlay_changes_immutable_fields")
            elif fields:
                try:
                    validate_skill_candidate({"skill_id": skill_id, "fields": fields}, skill_id)
                except (ValueError, TypeError):
                    errors.append("snapshot_skill_overlay_value_invalid")
    memories = snapshot.get("memories")
    if not isinstance(memories, list):
        errors.append("snapshot_memories_invalid")
        return sorted(set(errors))
    identities = set()
    for memory in memories:
        if not isinstance(memory, dict):
            errors.append("memory_not_object")
            continue
        if set(memory) - _MEMORY_KEYS:
            errors.append("memory_contains_noneditable_fields")
        mid = memory.get("memory_id")
        if not _text(mid) or mid in identities:
            errors.append("memory_identity_invalid_or_duplicate")
        else:
            identities.add(mid)
        if not _integer(memory.get("version"), 1):
            errors.append("memory_version_invalid")
        scope = memory.get("scope")
        if not isinstance(scope, dict) or any(not _text(k) or (v is not None and not isinstance(v, (str, int)))
                                             or isinstance(v, bool) for k, v in (scope.items() if isinstance(scope, dict) else [])):
            errors.append("memory_scope_invalid")
        if not _text(memory.get("trigger"), empty=True) or not _text(memory.get("insight")):
            errors.append("memory_content_invalid")
        if not _strings(memory.get("supporting_case_ids"), empty=False):
            errors.append("memory_support_invalid")
        if not isinstance(memory.get("source_trust"), str) or memory["source_trust"] not in _TRUST:
            errors.append("memory_trust_invalid")
        if not isinstance(memory.get("source_scope"), str) or memory["source_scope"] not in _SCOPE:
            errors.append("memory_source_scope_invalid")
        if not isinstance(memory.get("state"), str) or memory["state"] not in _STATE:
            errors.append("memory_state_invalid")
        if not _time(memory.get("available_at")):
            errors.append("memory_available_at_invalid")
        for field in ("last_used", "expires_at"):
            if memory.get(field) is not None and not _time(memory[field]):
                errors.append("memory_optional_time_invalid")
        for field in ("helpful_count", "harmful_count"):
            if field in memory and not _integer(memory[field]):
                errors.append("memory_usage_count_invalid")
        for field in ("raw_feedback_id", "origin", "deprecation_reason"):
            if memory.get(field) is not None and not _text(memory[field]):
                errors.append("memory_provenance_invalid")
        if "counterexamples" in memory and not isinstance(memory["counterexamples"], list):
            errors.append("memory_counterexamples_invalid")
        if "conflicts" in memory:
            conflicts = memory["conflicts"]
            if not isinstance(conflicts, list) or any(not isinstance(c, dict) or not _text(c.get("insight"), empty=True)
                    or not isinstance(c.get("source_trust"), str) or c["source_trust"] not in _TRUST
                    or not _strings(c.get("supporting_case_ids")) for c in conflicts):
                errors.append("memory_conflicts_invalid")
        if "revision_provenance" in memory:
            previous = memory["revision_provenance"]
            if (not isinstance(previous, dict) or set(previous) - {"previous_version", "previous_available_at", "previous_feedback_id"}
                    or not _integer(previous.get("previous_version"), 1)
                    or not _integer(memory.get("version"), previous.get("previous_version", 0) + 1)
                    or not _time(previous.get("previous_available_at"))
                    or (previous.get("previous_feedback_id") is not None and not _text(previous["previous_feedback_id"]))):
                errors.append("memory_revision_provenance_invalid")
            elif _time(memory.get("available_at")) and parse_time(previous["previous_available_at"]) > parse_time(memory["available_at"]):
                errors.append("memory_revision_availability_moved_backwards")
    return sorted(set(errors))


class _ReportClient:
    """Expose only a structured completion, keeping evaluator HTTP work bounded."""
    def __init__(self, client):
        # A dedicated accounting copy avoids changing a shared client's retry
        # setting. httpx transport/configuration are read-only during a request.
        if isinstance(client, OpenAICompatibleClient):
            client = copy.copy(client)
            client.total_usage = copy.deepcopy(client.total_usage)
            client.last_usage = copy.deepcopy(client.last_usage)
            client.last_response_metadata = copy.deepcopy(client.last_response_metadata)
            client.retries = 0
        self.client = client
        self.logical_requests = 0
        self.logical_failures = 0
        self.inferred_unknown_usage_requests = 0
        self._last_failed = False
        self._failure_before = 0

    @property
    def model(self):
        return getattr(self.client, "model", None)

    @property
    def request_count(self):
        return getattr(self.client, "request_count", self.logical_requests)

    @property
    def failed_request_count(self):
        return getattr(self.client, "failed_request_count", 0) + self.logical_failures

    @property
    def unknown_usage_request_count(self):
        return getattr(self.client, "unknown_usage_request_count", self.inferred_unknown_usage_requests)

    @property
    def total_usage(self):
        return getattr(self.client, "total_usage", {})

    def mark_response_failed(self):
        if self._last_failed:
            return
        self._last_failed = True
        if hasattr(self.client, "mark_response_failed"):
            self.client.mark_response_failed()
        elif getattr(self.client, "failed_request_count", 0) == self._failure_before:
            self.logical_failures += 1

    def generate_json(self, messages, schema=None):
        self.logical_requests += 1
        self._last_failed = False
        self._failure_before = getattr(self.client, "failed_request_count", 0)
        try:
            if hasattr(self.client, "generate_json"):
                return self.client.generate_json(messages, schema=schema)
            response = self.client.complete(messages, response_format={"type": "json_object"})
            value = json.loads(response["choices"][0]["message"]["content"])
            if not isinstance(value, dict):
                raise ValueError("report must be an object")
            return value
        except (LLMError, ValueError, TypeError, KeyError):
            self.mark_response_failed()
            raise LLMError("context regression structured completion failed") from None
        finally:
            if not hasattr(self.client, "unknown_usage_request_count"):
                usage = getattr(self.client, "total_usage", None)
                if not isinstance(usage, dict) or any(not _integer(usage.get(key)) for key in _USAGE_KEYS):
                    self.inferred_unknown_usage_requests += 1


class ContextRegressionService:
    def __init__(self, content_root: str | Path, *, llm: Any = None, selection_count: int = 5,
                 rollout_budget: int = 10, cancelled: Callable[[], bool] | None = None,
                 runner: Callable[..., dict[str, Any]] | None = None, skill_library: Any = None,
                 selection_cases: list[dict[str, Any]] | None = None):
        if not _integer(selection_count, 1) or not _integer(rollout_budget):
            raise ValueError("invalid Context regression selection/budget configuration")
        self.content_root = Path(content_root)
        raw_client = llm if llm is not None else OpenAICompatibleClient.from_env()
        self.llm = _ReportClient(raw_client) if raw_client else None
        self.selection_count, self.rollout_budget = selection_count, rollout_budget
        self.cancelled, self.runner = cancelled or (lambda: False), runner or run_agent
        self.library, self.selection_cases = skill_library, selection_cases
        self.rollouts = 0
        self.runs: list[dict[str, Any]] = []

    def _cancel(self):
        if self.cancelled():
            raise RuntimeError("context regression cancelled")

    def _counters(self):
        client = self.llm
        return {"provider_requests": getattr(client, "request_count", 0),
                "provider_failed_requests": getattr(client, "failed_request_count", 0),
                "provider_unknown_usage_requests": getattr(client, "unknown_usage_request_count", 0),
                "provider_usage": {key: value for key, value in getattr(client, "total_usage", {}).items()
                                   if key in _USAGE_KEYS and _integer(value)}}

    def _validate_release(self, current, previous, current_errors, previous_errors):
        # A restoration target must also name only licensed Skills, including
        # when a malformed current snapshot is caught without a cloud client.
        if previous is None or previous_errors:
            return None
        current_skills = current.get("skills", {}) if isinstance(current, dict) else {}
        if not previous["skills"] and not (isinstance(current_skills, dict) and current_skills):
            return None
        try:
            if self.library is None:
                self.library = SkillLibrary(self.content_root)
            metadata = self.library.skill_metadata()
            known = {entry["skill_id"] for entry in metadata}
            if not known or any(not _strings(entry.get("allowed_tools", []))
                                or not set(entry.get("allowed_tools", [])) <= TOOL_WHITELIST for entry in metadata):
                return "frozen_skill_library_invalid"
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
            return "frozen_skill_library_unavailable"
        if not set(previous["skills"]) <= known:
            previous_errors.append("snapshot_skill_outside_licensed_release")
        if not current_errors and not set(current["skills"]) <= known:
            current_errors.append("snapshot_skill_outside_licensed_release")
        return None

    def accounting(self) -> dict[str, Any]:
        """Only costs/budget and root identities, including interrupted checks."""
        return {"state": self.runs[-1]["state"] if self.runs else "not_started", "rollouts": self.rollouts,
                "budget": {"max_rollouts": self.rollout_budget, "regression_rollouts_used": self.rollouts,
                           "remaining_rollouts": max(0, self.rollout_budget - self.rollouts)},
                **{key: sum(run.get(key, 0) for run in self.runs) for key in
                   ("provider_requests", "provider_failed_requests", "provider_unknown_usage_requests")},
                "provider_usage": {key: sum(run.get("provider_usage", {}).get(key, 0) for run in self.runs)
                                   for key in _USAGE_KEYS if any(key in run.get("provider_usage", {}) for run in self.runs)},
                "selection_root_ids": sorted({root for run in self.runs for root in run["selection_root_ids"]}),
                "source_root_ids": sorted({root for run in self.runs for root in run["source_root_ids"]})}

    def check(self, current_snapshot: dict[str, Any], previous_snapshot: dict[str, Any] | None,
              *, source_root_ids: list[str] | None = None) -> dict[str, Any]:
        result = {"state": "no_check", "reason": "check_not_completed", "permission_violations": 0,
                  "key_regression": False, "current_metrics": None, "previous_metrics": None,
                  "selection_root_ids": [], "selection_sha256": None, "source_root_ids": [],
                  "rollouts": 0, "provider_requests": 0, "provider_failed_requests": 0,
                  "provider_unknown_usage_requests": 0, "provider_usage": {},
                  "validation_errors": [], "generalization_verified": False}
        before = self._counters()
        completed = False
        try:
            self._cancel()
            current_errors = _validate_snapshot(current_snapshot)
            previous_errors = _validate_snapshot(previous_snapshot) if previous_snapshot is not None else []
            release_error = self._validate_release(current_snapshot, previous_snapshot, current_errors, previous_errors)
            result["validation_errors"] = [{"snapshot": "current", "reason": code} for code in current_errors]
            result["validation_errors"] += [{"snapshot": "previous", "reason": code} for code in previous_errors]
            if release_error:
                result["reason"] = release_error
            elif current_errors and previous_errors:
                result["reason"] = "current_and_previous_snapshots_failed_hard_validation"
            elif current_errors:
                result.update(state="regression" if previous_snapshot is not None else "no_check",
                              reason="current_snapshot_skill_outside_licensed_release" if current_errors == ["snapshot_skill_outside_licensed_release"]
                                  else "current_snapshot_failed_hard_validation", key_regression=previous_snapshot is not None,
                              permission_violations=1)
            elif previous_snapshot is None:
                result["reason"] = "previous_snapshot_not_available"
            elif previous_errors:
                result["reason"] = ("previous_snapshot_skill_outside_licensed_release"
                                    if previous_errors == ["snapshot_skill_outside_licensed_release"]
                                    else "previous_snapshot_failed_hard_validation")
            elif not _strings([] if source_root_ids is None else source_root_ids):
                result["reason"] = "source_root_ids_invalid"
            elif self.llm is None:
                result["reason"] = "cloud_regression_client_not_configured"
            else:
                result["source_root_ids"] = sorted(set(source_root_ids or []))
                self._compare(result, current_snapshot, previous_snapshot)
            self._cancel()
            completed = True
            return result
        finally:
            after = self._counters()
            for key in ("provider_requests", "provider_failed_requests", "provider_unknown_usage_requests"):
                result[key] = max(0, after[key] - before[key])
            result["provider_usage"] = {key: max(0, value - before["provider_usage"].get(key, 0))
                                        for key, value in after["provider_usage"].items()}
            result["budget"] = {"max_rollouts": self.rollout_budget, "regression_rollouts_used": self.rollouts,
                                "remaining_rollouts": max(0, self.rollout_budget - self.rollouts)}
            if not completed:
                result.update(state="cancelled" if self.cancelled() else "failed", reason="check_interrupted",
                              permission_violations=0, key_regression=False)
            self.runs.append(copy.deepcopy(result))

    def _compare(self, result, current, previous):
        try:
            library = FrozenSkills(self.library or SkillLibrary(self.content_root))
            metadata = library.skill_metadata()
            known = {entry["skill_id"] for entry in metadata}
            if not known or any(not _strings(entry.get("allowed_tools", []))
                                or not set(entry.get("allowed_tools", [])) <= TOOL_WHITELIST for entry in metadata):
                result["reason"] = "frozen_skill_library_invalid"
                return
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
            result["reason"] = "frozen_skill_library_unavailable"
            return
        result["frozen_skill_sha256"] = library.sha256
        if not set(previous["skills"]) <= known:
            result["reason"] = "previous_snapshot_skill_outside_licensed_release"
            return
        if not set(current["skills"]) <= known:
            result.update(state="regression", reason="current_snapshot_skill_outside_licensed_release",
                          permission_violations=1, key_regression=True)
            return
        try:
            scorer = DevSelectionScorer(self.content_root, proposal_root_ids=set(result["source_root_ids"]),
                                        count=self.selection_count, cases=self.selection_cases)
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
            result["reason"] = "independent_dev_selection_unavailable"
            return
        result.update(selection_root_ids=list(scorer.root_ids), selection_sha256=scorer.sha256)
        if len(scorer.cases) != self.selection_count:
            result["reason"] = "insufficient_independent_dev_roots"
            return
        if self.rollout_budget - self.rollouts < 2 * len(scorer.cases):
            result["reason"] = "insufficient_budget_for_previous_and_current"
            return
        skill_id = "data-quality" if "data-quality" in known else sorted(known)[0]

        def evaluate(snapshot):
            self._cancel()
            fields = copy.deepcopy(snapshot["skills"].get(skill_id, {}))
            fields.setdefault("instructions", library.load_skill(skill_id)["body"])
            # Reserve the full fixed selection before starting this snapshot;
            # cancelled/failed roots are conservatively charged as attempts.
            result["rollouts"] += len(scorer.cases)
            self.rollouts += len(scorer.cases)
            metrics = scorer.evaluate({"skill_id": skill_id, "fields": fields}, snapshot=snapshot,
                library=library, llm=self.llm, runner=self.runner, cancelled=self.cancelled)
            self._cancel()
            score = metrics.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError("nonfinite regression score")
            return metrics

        try:
            result["previous_metrics"] = evaluate(previous)
            if result["previous_metrics"].get("hard_failures"):
                result["reason"] = "previous_dev_evaluation_invalid"
                return
            result["current_metrics"] = evaluate(current)
        except RuntimeError:
            if self.cancelled():
                raise RuntimeError("context regression cancelled") from None
            result["reason"] = "dev_evaluation_failed"
            return
        except (LLMError, ValueError, TypeError, KeyError):
            result["reason"] = "dev_evaluation_failed"
            return
        failures = result["current_metrics"].get("hard_failures", [])
        permission_count = sum(f.get("reason") in {"tool_or_execution_permission_violation",
                                                   "safety_infeasible_test_recommended"} for f in failures)
        lower = result["current_metrics"]["score"] < result["previous_metrics"]["score"]
        if failures or lower:
            result.update(state="regression", reason="current_dev_hard_failure" if failures else "key_score_below_previous",
                          permission_violations=permission_count, key_regression=True)
        else:
            result.update(state="passed", reason="independent_dev_floor_preserved")
