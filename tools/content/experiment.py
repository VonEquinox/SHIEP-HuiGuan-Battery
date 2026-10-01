"""Preregistered real-cloud A0–A4 synthetic replay pilot, with bounded costs.

No simulated LLM is used. A0 alone is an explicitly deterministic rule baseline.
The sealed milestone is evaluated only after final snapshots are frozen, and
is never supplied to any memory update, proposer or selection callback.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import threading
import time

from .common import TOOL_WHITELIST, digest, opaque_id, read_jsonl, write_json
from .generate import BUCKETS
from .replay import EvaluatorReplay

REPOSITORY = Path(__file__).resolve().parents[2]
ARMS = ("A0", "A1", "A2", "A3", "A4")


def sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _time_shift(value: str, days: int) -> str:
    return (datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _rebase(value, days: int):
    if isinstance(value, dict):
        return {key: _time_shift(child, days) if key in {"timestamp", "observed_at", "cutoff", "visible_cutoff"} and isinstance(child, str) and re.match(r"\d{4}-\d\d-\d\dT", child) else _rebase(child, days) for key, child in value.items()}
    if isinstance(value, list):
        return [_rebase(child, days) for child in value]
    return value


def select_ids() -> dict:
    # The parameter choice is frozen before execution, never chosen by model
    # outcomes. One root per bucket, with different mother templates in each split.
    return {split: [opaque_id("r", f"v1:{bucket}:{group}:{bucket % 8}") for bucket in range(12)] for split, group in (("evolution", 8), ("dev", 14), ("sealed_test", 17))}


def selected_rows(path: Path, ids: set[str], *, key: str = "case_id") -> list[dict]:
    rows = []
    pattern = re.compile('"' + re.escape(key) + r'"\s*:\s*"([^"]+)"')
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            identity = pattern.search(line)
            if identity and identity.group(1) in ids:
                rows.append(json.loads(line))
    return rows


def cumulative_cost(cost: dict) -> tuple[int, int]:
    return (int(cost.get("combined_http_attempts", cost["http_attempts"])), int(cost.get("combined_charged_tokens", cost["charged_tokens_including_unknown_failures"])))


def verify_content_files(content: Path, manifest: dict) -> None:
    for relative, entry in manifest["files"].items():
        path = (content / relative).resolve()
        if not path.is_relative_to(content.resolve()) or not path.is_file() or digest(path) != entry["sha256"]:
            raise RuntimeError("frozen content file changed: " + relative)


def input_payload(case: dict, snapshot: dict, *, days: int = 0) -> dict:
    initial = _rebase(deepcopy(case["initial_visible"]), days)
    asset = deepcopy(case["asset_context"])
    observations = initial["observations"]
    units = sorted({observation["unit"] for observation in observations})
    # Derived aliases refer only to existing visible measurements. Required
    # measurements/mappings that are absent remain absent and cannot force-route.
    payload = {**initial, "observations": observations, "asset_id": asset["asset_id"], "installation_id": asset["installation_id"],
               "asset": asset, "asset_context": asset, "chemistry": asset["chemistry"], "protocol_id": asset["protocol_id"],
               "visible_cutoff": initial["cutoff"], "round": 1, "units": units,
               "visible_evidence": observations, "measurement_quality": asset["quality"],
               "symptoms": " ".join(observation["metric"] for observation in observations) + " chemistry data quality 检查 未解决",
               "test_catalog": deepcopy(case["test_catalog"]), "context_snapshot": deepcopy(snapshot), "max_tool_calls": 12,
               "authorization": {"authorized_test_ids": ["T_TIME_ALIGN", "T_CHANNEL_CHECK"], "qualifications": ["instrumentation"], "round_budget": 3, "human_approved": True},
               "resource_constraints": {"remaining_minutes": 60, "synthetic_grants": True}, "namespace": "demo_synthetic"}
    if case.get("fleet_context"):
        payload["group_context"] = deepcopy(case["fleet_context"])
    if initial.get("visible_feedback"):
        payload["feedback"] = initial["visible_feedback"]
    return payload


class ExperimentCancelled(RuntimeError):
    pass


def interrupt_budget(budget) -> None:
    # Mark cancellation BEFORE executor shutdown waits for running futures. Any
    # queued worker then rejects its call before spending another HTTP attempt.
    budget.cancel_file.touch(exist_ok=True)
    raise KeyboardInterrupt


class CostBudget:
    def __init__(self, output: Path, *, max_calls: int, max_tokens: int, cancel_file: Path):
        self.output, self.max_calls, self.max_tokens, self.cancel_file = output, max_calls, max_tokens, cancel_file
        self.lock = threading.Lock()
        self.attempts = 0
        self.reserved_tokens = 0
        self.charged_tokens = 0
        self.failed = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.rows = []

    def cancelled(self) -> bool:
        return self.cancel_file.exists()

    def invoke(self, messages: list[dict], *, tag: str) -> dict:
        from battery_platform.app.agent.llm import OpenAICompatibleClient, LLMError
        if self.cancelled():
            raise ExperimentCancelled("cancel file detected")
        # UTF-8 byte count bounds byte-token vocabulary length; reserve the
        # provider's full 4096 completion cap, then refund to actual reported use.
        reservation = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 4096 + 256
        with self.lock:
            if self.cancelled():
                raise ExperimentCancelled("cancel file detected before HTTP reservation")
            if self.attempts >= self.max_calls or self.charged_tokens + self.reserved_tokens + reservation > self.max_tokens:
                raise LLMError("pre-registered API/token budget exhausted")
            self.attempts += 1; sequence = self.attempts; self.reserved_tokens += reservation
        client = OpenAICompatibleClient.from_env()
        if client is None:
            raise RuntimeError("BATTERY_LLM_API_KEY required for a real cloud pilot")
        client.retries = 0
        started = time.monotonic()
        row = {"sequence": sequence, "tag": tag, "request_sha256": sha(messages), "started_at": datetime.now(timezone.utc).isoformat(), "token_upper_bound_reserved": reservation, "http_attempts": 1, "thinking": getattr(client, "thinking", None)}
        answer, error = None, None
        try:
            response = client.complete(messages, response_format={"type": "json_object"})
            row["usage"] = deepcopy(client.last_usage)
            row["response_model"] = response.get("model")
            row["system_fingerprint"] = response.get("system_fingerprint")
            row["finish_reason"] = response["choices"][0].get("finish_reason")
            content = response["choices"][0]["message"]["content"]
            # Save only the provider's final answer, never reasoning_content.
            response_dir = self.output / "provider_responses"
            response_dir.mkdir(exist_ok=True)
            (response_dir / f"{sequence:04d}.txt").write_text(content or "", encoding="utf-8")
            answer = json.loads(content)
            if not isinstance(answer, dict):
                raise ValueError("provider JSON is not an object")
            row.update(status="json_received", response_sha256=sha(answer))
        except Exception as exc:
            error = exc
            row.update(status="failed", error_type=type(exc).__name__)
            if client.last_usage:
                row["usage"] = deepcopy(client.last_usage)
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
            reported = row.get("usage", {})
            row["charged_tokens"] = int(reported.get("total_tokens", reservation))
            row["cost_basis"] = "provider_reported" if reported else "unknown_charge_upper_bound"
            with self.lock:
                self.reserved_tokens -= reservation
                self.charged_tokens += row["charged_tokens"]
                self.failed += int(error is not None)
                for key in self.usage:
                    self.usage[key] += int(reported.get(key, 0))
                self.rows.append(row)
                with (self.output / "provider_calls.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if error is not None:
            raise LLMError("recorded provider or structured JSON failure") from None
        if self.cancelled():
            raise ExperimentCancelled("cancelled after recorded provider call")
        return answer

    def summary(self) -> dict:
        with self.lock:
            return {"http_attempts": self.attempts, "failed_calls": self.failed, "reported_usage": deepcopy(self.usage), "charged_tokens_including_unknown_failures": self.charged_tokens, "max_http_attempts": self.max_calls, "max_tokens": self.max_tokens, "remaining_calls": self.max_calls - self.attempts}


class BudgetJSONClient:
    # Deliberately offers generate_json only: one HTTP call per report, no
    # provider-driven iterative tool loop can expand the frozen call budget.
    def __init__(self, budget: CostBudget, model: str, tag: str):
        self.budget, self.model, self.tag = budget, model, tag
        self.last_usage = {}

    @property
    def request_count(self):
        return self.budget.attempts

    @property
    def failed_request_count(self):
        return self.budget.failed

    @property
    def total_usage(self):
        return deepcopy(self.budget.usage)

    def generate_json(self, messages, schema=None):
        if any("report_template" in message.get("content", "") for message in messages):
            messages = deepcopy(messages)
            messages[0]["content"] += "\nKeep the report concise: at most three facts, three hypotheses, three unknowns and two suggested tests. Preserve every immutable ID/time/version exactly as supplied in report_template. Give reasons in at most 80 Chinese characters each."
        return self.budget.invoke(messages, tag=self.tag)


def report_metrics(result: dict, case: dict, label: dict, payload: dict, *, cloud_expected: bool) -> dict:
    report = result["report"]
    refs = {oid for fact in report.get("facts", []) for oid in fact.get("evidence_ids", [])} | set(report.get("citations", []))
    observable_ids = {observation["observation_id"] for observation in payload["observations"]}
    observable_ids |= {f"asset-context:{payload['installation_id']}"}
    snapshot = payload["context_snapshot"]
    observable_ids |= {memory["memory_id"] for memory in snapshot["memories"]}
    observable_ids |= {"prediction:" + p["prediction_id"] for p in payload.get("predictions", [])}
    observable_ids |= {str(e) for metadata in result["run"].get("selected_skills", []) for e in []}
    wrong_refs = refs - observable_ids
    # Published knowledge references are legitimate visible Skill citations.
    wrong_refs = {ref for ref in wrong_refs if not ref.startswith("knowledge-skill-")}
    expected = label["expected_behavior"]
    statuses = {"insufficient_evidence", "suspected"}
    if case["asset_context"]["chemistry"] not in {"LFP", "NCM", "unknown"} or expected["initial_status"] == "unsupported":
        statuses = {"unsupported", "insufficient_evidence"}
    selected = report.get("suggested_tests", [])
    first = next((test["test_id"] for test in selected if test["authorization"] == "authorized"), None)
    acceptable = set(expected["acceptable_first_tests"])
    permission_violations = sum(test["authorization"] == "authorized" and test["test_id"] not in payload["authorization"]["authorized_test_ids"] for test in selected)
    ungrounded_confirmations = sum(hypothesis["level"] == "confirmed" for hypothesis in report.get("hypotheses", []))
    status_pass = report["status"] in statuses
    cloud_valid = bool(result["run"].get("cloud_report_valid")) if cloud_expected else None
    facts = report.get("facts", [])
    grounded = sum(bool(fact.get("evidence_ids")) and not (set(fact.get("evidence_ids", [])) & wrong_refs) for fact in facts)
    grounded_ratio = grounded / len(facts) if facts else 0.0
    test_pass = first in acceptable if first else not label["split_tags"]["requires_initial_test"] or report["status"] == "unsupported"
    quality = .4 * status_pass + .3 * grounded_ratio + .2 * test_pass + .1 / (1 + len(selected))
    if cloud_expected and not cloud_valid:
        quality = 0.0
    needs = bool(label["split_tags"]["requires_initial_test"])
    alert = report["priority"]["class"] in {"needs_inspection", "urgent_review"}
    return {"report_quality": quality, "initial_status_pass": status_pass, "wrong_reference_count": len(wrong_refs), "wrong_reference_ids": sorted(wrong_refs), "grounded_assertion_ratio": grounded_ratio, "recommended_check_count": len(selected), "acceptable_first_test": test_pass,
            "permission_violation_count": permission_violations, "unjustified_confirmation_count": ungrounded_confirmations,
            "cloud_report_valid": cloud_valid, "configured_inspection_needed": needs, "missed_inspection": int(needs and not alert), "false_inspection_alarm": int(not needs and alert),
            "inspection_label_provenance": "project-configured scenario behavior; not real defect incidence", "semantic_blind_review": "pending"}


def summarize_records(records: list[dict]) -> dict:
    metrics = [record["metrics"] for record in records]
    count = len(metrics)
    return {"root_count": count, "mean_report_quality": sum(m["report_quality"] for m in metrics) / count if count else None,
            "cloud_valid_reports": sum(m["cloud_report_valid"] is True for m in metrics), "wrong_references": sum(m["wrong_reference_count"] for m in metrics),
            "mean_recommended_checks": sum(m["recommended_check_count"] for m in metrics) / count if count else None,
            "missed_inspections": sum(m["missed_inspection"] for m in metrics), "false_inspection_alarms": sum(m["false_inspection_alarm"] for m in metrics),
            "permission_violations": sum(m["permission_violation_count"] for m in metrics), "unjustified_confirmations": sum(m["unjustified_confirmation_count"] for m in metrics), "semantic_blind_review": "pending"}


class Pilot:
    def __init__(self, output: Path, *, max_calls=200, max_tokens=2_000_000, workers=4, offline_full=True, prior_run: Path | None = None):
        from battery_platform.app.agent.context import ContextStore
        from battery_platform.app.agent.gepa_service import FrozenSkills
        from battery_platform.app.agent.llm import OpenAICompatibleClient
        from battery_platform.app.agent.skills import SkillLibrary
        self.output = output.resolve()
        if self.output.exists() and any(self.output.iterdir()):
            raise ValueError("experiment output must be a new empty directory; never overwrite a prior protocol")
        self.output.mkdir(parents=True, exist_ok=True)
        self.content = REPOSITORY / "content_v1"
        self.client = OpenAICompatibleClient.from_env()
        if self.client is None:
            raise ValueError("a real cloud key is required; no simulated LLM fallback")
        self.ids = select_ids()
        assignments = json.loads((self.content / "manifests/splits.json").read_text())["root_assignments"]
        if any(assignments.get(cid) != split for split, ids in self.ids.items() for cid in ids):
            raise ValueError("preregistered roots no longer match the frozen split")
        self.initial = ContextStore().snapshot()
        self.stores = {arm: ContextStore(initial_snapshot=self.initial) for arm in ARMS}
        self.content_manifest = json.loads((self.content / "manifest.json").read_text())
        verify_content_files(self.content, self.content_manifest)
        self.library = FrozenSkills(SkillLibrary(self.content))
        self.workers, self.offline_full = min(4, max(1, workers)), offline_full
        self.prior = {}
        if prior_run:
            prior_summary = json.loads((prior_run / "summary.json").read_text())
            self.prior = {"path": str(prior_run), "summary_sha256": digest(prior_run / "summary.json"), "cost": prior_summary["cost"], "state": prior_summary["state"]}
            prior_calls, prior_tokens = cumulative_cost(prior_summary["cost"])
            self.prior["cumulative_cost"] = {"http_attempts": prior_calls, "charged_tokens": prior_tokens}
            max_calls -= prior_calls
            max_tokens -= prior_tokens
        if max_calls <= 0 or max_tokens <= 0:
            raise ValueError("prior recorded calls exhaust the combined authorized budget")
        self.budget = CostBudget(self.output, max_calls=max_calls, max_tokens=max_tokens, cancel_file=self.output / "CANCEL")
        evo = selected_rows(self.content / "streams/evolution_round_01.jsonl", set(self.ids["evolution"]))
        dev = selected_rows(self.content / "evaluation/dev/cases.jsonl", set(self.ids["dev"]))
        selected = set(self.ids["evolution"] + self.ids["dev"])
        self.cases = {case["case_id"]: case for case in evo + dev}
        self.labels = {label["case_id"]: label for label in selected_rows(self.content / "oracle/labels.jsonl", selected)}
        if len(self.cases) != 24 or len(self.labels) != 24:
            raise ValueError("pilot needs exactly twelve evolution and twelve independent dev roots")
        # Filter oracle before instantiating the existing replay methods, keeping
        # all sealed inputs out of the live training environment.
        self.environment = EvaluatorReplay.__new__(EvaluatorReplay)
        self.environment.root = self.content
        self.environment._cases = {cid: self.cases[cid] for cid in self.ids["evolution"]}
        self.environment._labels = {cid: self.labels[cid] for cid in self.ids["evolution"]}
        self.environment._observations = {o["observation_id"]: o for o in selected_rows(self.content / "oracle/observations.jsonl", set(self.ids["evolution"]), key="root_scenario_id")}
        self.artifact = {"label": "预登记小规模合成/回放诊断实验（真实云端调用）", "state": "preregistered", "live_cloud": True, "batches": [], "dev_evaluation": {}, "sealed_milestone": {}, "offline_A0": {}, "limitations": ["12 roots per stage cannot establish broad generalization", "no independent professional blind review", "coarse configured synthetic states, not field outcomes", "A2 installation-scoped episodes cannot transfer across unique installations", "no calibrated real fault probabilities"]}
        self.freeze_protocol(max_calls, max_tokens)

    def freeze_protocol(self, max_calls: int, max_tokens: int):
        code_paths = [*[REPOSITORY / "tools/content" / name for name in ("experiment.py", "common.py", "replay.py", "generate.py")], *sorted((REPOSITORY / "battery_platform/app/agent").glob("*.py")), REPOSITORY / "battery_platform/app/diagnosis/active_tests.py"]
        self.code_hashes = {str(path.relative_to(REPOSITORY)): digest(path) for path in code_paths}
        self.protocol = {"protocol_version": "battery-replay-pilot-v1", "registered_at": datetime.now(timezone.utc).isoformat(), "content_manifest_sha256": digest(self.content / "manifest.json"),
                         "code_sha256": self.code_hashes, "model": self.client.model, "provider_base_url": self.client.base_url, "numerical_model": "configured-synthetic-head-v1 (unvalidated)",
                         "context_v0": self.initial, "context_v0_sha256": sha(self.initial), "root_ids": self.ids, "bucket_order": list(BUCKETS), "arms": list(ARMS), "thinking": getattr(self.client, "thinking", None), "prior_run": self.prior,
                         "batch_count": 6, "roots_per_batch": 2, "same_frozen_input_within_batch": True, "report_budget": {"provider_calls": 1, "max_tokens_per_call": 4096, "max_tool_calls": 12, "max_loaded_skills": 4, "http_retries": 0},
                         "gepa": {"candidate_budget_per_batch": 1, "selection_roots_per_batch": 2, "max_candidate_rollouts": 24, "feedback_before_proposal": True},
                         "maximum_http_attempts": max_calls, "maximum_tokens_including_unknown_failures": max_tokens, "tools": sorted(TOOL_WHITELIST),
                         "stages": ["six evolution batches: predict all arms, freeze reports, reveal selected authorized tests, apply memory, stage GEPA", "freeze final context snapshots", "read-only final twelve-dev evaluation for A0/A1/A4 (A2/A3 reserved for sealed milestone to fit cumulative budget)", "one final twelve-sealed milestone, compare shared static v0 and frozen final A2/A3/A4, no later optimizer", "optional complete deterministic A0 offline after milestone"],
                         "sealed_cache": "A1 and initial A2/A3/A4 are identical static inputs/context; v0 is called once and shared. A1 final stays v0 and reuses this identical report; no duplicate report counted as independent sample.",
                         "selection_rule": "one root per each of twelve buckets, frozen generator identity groups8/14/17, member=bucket_index%8; no result-dependent selection",
                         "timeline": "each evolution batch shifted by integer days; original physical root/observation identity and quantities retained; feedback availability precedes later batch cutoff", "scoring": "0.4 initial-status pass +0.3 grounded citations +0.2 acceptable first-test/abstention +0.1/(1+checks); failed cloud report=0; inspection error counts use configured requires_initial_test, not real defect labels",
                         "cancellation": "create output/CANCEL or interrupt process; ledger and frozen batches retained", "semantic_blind_review": "pending"}
        self.protocol["response_constraints"] = {"facts": 3, "hypotheses": 3, "unknowns": 3, "suggested_tests": 2, "reason_max_chinese_characters": 80, "raw_final_answers_saved": True, "reasoning_content_saved": False}
        self.protocol["protocol_sha256"] = sha(self.protocol)
        write_json(self.output / "protocol.json", self.protocol)
        write_json(self.output / "context_v0.json", self.initial)
        write_json(self.output / "results.json", self.artifact)

    def check_frozen(self, *, content_files: bool = False):
        if self.budget.cancelled():
            raise ExperimentCancelled("cancel file detected")
        if digest(self.content / "manifest.json") != self.protocol["content_manifest_sha256"]:
            raise RuntimeError("content changed after preregistration")
        if any(digest(REPOSITORY / relative) != expected for relative, expected in self.code_hashes.items()):
            raise RuntimeError("runtime code changed after preregistration")
        if content_files:
            verify_content_files(self.content, self.content_manifest)

    def predict(self, arm: str, case: dict, label: dict, snapshot: dict, tag: str, days: int = 0) -> dict:
        from battery_platform.app.agent.context import ContextStore
        from battery_platform.app.agent.executor import run_agent
        self.check_frozen()
        payload = input_payload(case, snapshot, days=days)
        adapter = BudgetJSONClient(self.budget, self.client.model, tag)
        started = time.monotonic()
        result = run_agent(payload, llm=adapter if arm != "A0" else False, skill_library=self.library if arm != "A0" else None, context_store=ContextStore(initial_snapshot=snapshot))
        record = {"arm": arm, "root_scenario_id": case["root_scenario_id"], "input_sha256": sha(payload), "context_snapshot_id": snapshot["context_snapshot_id"], "report": result["report"], "report_sha256": sha(result["report"]), "run": result["run"], "tool_trace": result["tool_trace"], "elapsed_seconds": round(time.monotonic() - started, 3), "metrics": report_metrics(result, case, label, payload, cloud_expected=arm != "A0"), "feedback_used_before_report": False}
        exact_calls = [row for row in self.budget.rows if row["tag"] == tag]
        record["provider_cost"] = {"http_attempts": len(exact_calls), "usage": {key: sum(row.get("usage", {}).get(key, 0) for row in exact_calls) for key in self.budget.usage}, "failed_calls": sum(row["status"] == "failed" for row in exact_calls)}
        raw_diagnostics = []
        for call in exact_calls:
            response_path = self.output / "provider_responses" / f"{call['sequence']:04d}.txt"
            item = {"sequence": call["sequence"], "finish_reason": call.get("finish_reason"), "response_file": str(response_path.relative_to(self.output)) if response_path.exists() else None}
            if response_path.exists():
                try:
                    raw = json.loads(response_path.read_text())
                    raw_refs = set(raw.get("citations", [])) | {ref for fact in raw.get("facts", []) for ref in fact.get("evidence_ids", [])}
                    visible_refs = {observation["observation_id"] for observation in payload["observations"]}
                    from battery_platform.app.agent.context import ContextStore
                    from battery_platform.app.agent.executor import _evidence_ids
                    scope = {"installation_id": payload["installation_id"], "chemistry": payload["chemistry"], "protocol_id": payload["protocol_id"]}
                    visible_refs |= _evidence_ids(ContextStore(initial_snapshot=snapshot).search(payload["symptoms"], scope=scope, cutoff=payload["visible_cutoff"]))
                    visible_refs |= {"prediction:" + p["prediction_id"] for p in payload.get("predictions", [])}
                    visible_refs |= _evidence_ids(result["tool_trace"])
                    visible_refs |= {ref for metadata in result["run"]["selected_skills"] for ref in _evidence_ids(self.library.load_skill(metadata["skill_id"]))}
                    item.update(json_parse=True, raw_wrong_reference_count=len(raw_refs - visible_refs), raw_wrong_reference_ids=sorted(raw_refs - visible_refs), immutable_changes=[key for key in ("asset_id", "installation_id", "visible_cutoff", "round", "report_id", "context_version") if raw.get(key) != record["report"].get(key)])
                    from battery_platform.app.agent.contracts import AgentReport
                    try:
                        AgentReport.model_validate(raw)
                        item["strict_schema_pass"] = True
                    except Exception:
                        item["strict_schema_pass"] = False
                except (ValueError, TypeError, KeyError, AttributeError):
                    item.update(json_parse=False, raw_wrong_reference_count=None)
            else:
                item.update(json_parse=None, raw_wrong_reference_count=None)
            raw_diagnostics.append(item)
        record["provider_diagnostics"] = raw_diagnostics
        record["metrics"]["provider_raw_wrong_reference_count"] = sum(item.get("raw_wrong_reference_count") or 0 for item in raw_diagnostics)
        # Concurrent client-global counters are unsuitable per report; bind its
        # already recorded exact call tag before persisting the report artifact.
        record["run"]["llm_usage"] = record["provider_cost"]["usage"]
        record["run"]["llm_request_count"] = record["provider_cost"]["http_attempts"]
        record["run"]["llm_failed_request_count"] = record["provider_cost"]["failed_calls"]
        return record

    def freeze_records(self, relative: str, records: list[dict]):
        write_json(self.output / relative, {"records": records, "sha256": sha(records), "frozen_before_feedback": True})

    def feedback(self, arm: str, record: dict, days: int) -> dict | None:
        from battery_platform.app.agent.context import evolve_context
        self.check_frozen()
        if arm not in {"A2", "A3", "A4"} or not record["metrics"]["cloud_report_valid"]:
            record["update"] = {"state": "no_update", "reason": "arm_has_no_memory_or_cloud_report_failed"}
            return None
        session = self.environment.begin(record["root_scenario_id"])
        chosen = next((test["test_id"] for test in record["report"]["suggested_tests"] if test["authorization"] == "authorized" and test["test_id"] == "T_TIME_ALIGN"), None)
        if not chosen:
            record["update"] = {"state": "no_update", "reason": "no_reachable_authorized_test_selected"}
            return None
        self.environment.authorize(session, chosen, approved_by="synthetic_evaluator")
        record["revealed"] = _rebase(self.environment.reveal(session, chosen), days)
        available = self.environment.visible_feedback(session)
        if not available:
            record["update"] = {"state": "no_update", "reason": "feedback_evidence_not_reached"}
            return None
        feedback = _rebase(deepcopy(available[0]), days)
        feedback.update(root_scenario_id=record["root_scenario_id"], split="evolution", installation_id=session.visible["asset_context"]["installation_id"], provenance="expert_synthetic", available_at=feedback["observed_at"])
        store = self.stores[arm]
        self.check_frozen()
        if arm == "A2":
            item = {"insight": feedback["free_text"], "trigger": "inspection episode", "scope": {"installation_id": feedback["installation_id"]}, "supporting_case_ids": [record["root_scenario_id"]], "source_trust": "reported", "available_at": feedback["available_at"], "origin": "synthetic_replay", "raw_feedback_id": feedback["feedback_id"]}
            updated = store.apply([{"operation": "ADD", "memory_id": "episode-" + record["root_scenario_id"], "item": item}], expected_version=store.snapshot()["version"], source_scope="evolution")
        else:
            asset = session.visible["asset_context"]
            feedback["scope"] = {"chemistry": asset["chemistry"], "protocol_id": asset["protocol_id"]}
            updated = evolve_context(store, feedback, record["report"])
        record["feedback"] = feedback
        record["update"] = {"state": updated["state"], "context_snapshot_id": updated["snapshot"]["context_snapshot_id"], "raw_feedback_id": feedback["feedback_id"]}
        return {"root_scenario_id": record["root_scenario_id"], "split": "evolution", "report": deepcopy(record["report"]), "tool_trace": deepcopy(record["tool_trace"]), "feedback": feedback}

    def run_gepa(self, batch: int, events: list[dict]) -> dict:
        from battery_platform.app.agent.gepa_service import GEPAService
        if len(events) < 2:
            return {"state": "no_update", "reason": "less_than_two_revealed_feedback_roots", "rollouts": 0, "provider_requests": 0}
        cases = []
        for cid in self.ids["dev"][batch * 2:batch * 2 + 2]:
            case = deepcopy(self.cases[cid]); label = deepcopy(self.labels[cid])
            case.update(split="dev", hidden_truth=label["hidden_truth"], expected_behavior=label["expected_behavior"])
            case["initial_visible"] = _rebase(case["initial_visible"], 10)
            cases.append(case)
        service = GEPAService(self.content, max_rollouts=4, direct_root_count=0, batch_size=2, selection_count=2, candidate_budget=1,
                              llm=BudgetJSONClient(self.budget, self.client.model, f"gepa-batch-{batch+1}"), cancelled=self.budget.cancelled, selection_cases=cases, skill_library=self.library)
        self.check_frozen()
        staged = service.optimize(events, self.stores["A4"], skill_id="data-quality")
        if staged.get("activation_update"):
            self.check_frozen()
            activation = self.stores["A4"].apply([staged["activation_update"]], expected_version=self.stores["A4"].snapshot()["version"], source_scope="evolution", regression=staged["regression"])
            staged["activation_state"] = activation["state"]
            staged["activated_snapshot_id"] = activation["snapshot"]["context_snapshot_id"]
        return staged

    def read_only_stage(self, stage: str, cases: dict, labels: dict, contexts: dict, *, days=10) -> dict:
        self.check_frozen(content_files=True)
        records_by_arm = {arm: [] for arm in contexts}
        failures = []
        jobs = [(arm, case_id) for case_id in self.ids["dev" if stage == "dev" else "sealed_test"] for arm in contexts]
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self.predict, arm, cases[cid], labels[cid], contexts[arm], f"{stage}:{arm}:{cid}", days): (arm, cid) for arm, cid in jobs}
            def persist(record):
                records_by_arm[record["arm"]].append(record)
                write_json(self.output / f"partial_records/{stage}/{record['arm']}_{record['root_scenario_id']}.json", record)
            interrupted = self.collect_futures(futures, persist, failures)
        if failures or interrupted:
            self.artifact["partial_stage"] = {"stage": stage, "completed": {arm: summarize_records(records) for arm, records in records_by_arm.items()}, "failures": failures, "records": records_by_arm}
            if interrupted:
                raise KeyboardInterrupt
            raise ExperimentCancelled("cancelled stage") if self.budget.cancelled() else RuntimeError("stage has retained incomplete records")
        self.check_frozen(content_files=True)
        for arm, records in records_by_arm.items():
            records.sort(key=lambda record: self.ids["dev" if stage == "dev" else "sealed_test"].index(record["root_scenario_id"]))
            self.freeze_records(f"{stage}/{arm}.json", records)
        return {arm: {"records": records, "summary": summarize_records(records), "selection_eligible": stage == "dev"} for arm, records in records_by_arm.items()}

    def collect_futures(self, futures: dict, persist, failures: list) -> bool:
        pending = set(futures)
        interrupted = False
        while pending:
            try:
                for future in as_completed(pending):
                    pending.remove(future)
                    arm, cid = futures[future]
                    try:
                        persist(future.result())
                    except Exception as exc:
                        failures.append({"arm": arm, "root": cid, "error_type": type(exc).__name__})
            except KeyboardInterrupt:
                # Catch before ThreadPoolExecutor.__exit__(wait=True). Cancel
                # queued futures immediately, then drain active/completed ones
                # so every actual response retains its ledger and report.
                interrupted = True
                self.budget.cancel_file.touch(exist_ok=True)
                for future in tuple(pending):
                    if future.cancel():
                        arm, cid = futures[future]
                        failures.append({"arm": arm, "root": cid, "error_type": "CancelledError"})
                        pending.remove(future)
        return interrupted

    def execute(self) -> dict:
        try:
            self.artifact["state"] = "evolution_running"
            for batch in range(6):
                self.check_frozen(content_files=True)
                snapshots = {arm: self.stores[arm].snapshot() for arm in ARMS}
                ids = self.ids["evolution"][batch * 2:batch * 2 + 2]
                records = []
                failures = []
                with ThreadPoolExecutor(max_workers=self.workers) as executor:
                    futures = {executor.submit(self.predict, arm, self.cases[cid], self.labels[cid], snapshots[arm], f"evolution-{batch+1}:{arm}:{cid}", batch): (arm, cid) for cid in ids for arm in ARMS}
                    def persist(record):
                        records.append(record)
                        write_json(self.output / f"partial_records/evolution_{batch+1:02d}/{record['arm']}_{record['root_scenario_id']}.json", record)
                    interrupted = self.collect_futures(futures, persist, failures)
                if failures or interrupted:
                    self.artifact["partial_stage"] = {"stage": "evolution", "batch": batch + 1, "records": records, "failures": failures}
                    if interrupted:
                        raise KeyboardInterrupt
                    raise ExperimentCancelled("cancelled batch") if self.budget.cancelled() else RuntimeError("batch has retained incomplete records")
                records.sort(key=lambda record: (ARMS.index(record["arm"]), ids.index(record["root_scenario_id"])))
                # This saved file is immutable prediction evidence. Subsequent
                # feedback and patches are stored in the separate batch result.
                self.freeze_records(f"batches/batch_{batch+1:02d}_predictions.json", records)
                self.check_frozen(content_files=True)
                feedback_events = []
                for record in records:
                    self.check_frozen()
                    feedback = self.feedback(record["arm"], record, batch)
                    if record["arm"] == "A4" and feedback:
                        feedback_events.append(feedback)
                gepa = self.run_gepa(batch, feedback_events)
                self.check_frozen()
                after = {arm: self.stores[arm].snapshot() for arm in ARMS}
                summary = {arm: summarize_records([record for record in records if record["arm"] == arm]) for arm in ARMS}
                result = {"batch": batch + 1, "roots": ids, "summaries": summary, "records": records, "gepa": gepa, "context_versions_before": {arm: snapshot["version"] for arm, snapshot in snapshots.items()}, "context_versions_after": {arm: snapshot["version"] for arm, snapshot in after.items()}, "cost_so_far": self.budget.summary()}
                self.artifact["batches"].append(result)
                write_json(self.output / f"batches/batch_{batch+1:02d}_result.json", result)
                for arm, snapshot in after.items():
                    write_json(self.output / f"contexts/{arm}_batch_{batch+1:02d}.json", snapshot)
                write_json(self.output / "results.json", self.artifact)
                print(json.dumps({"stage": "evolution", "batch": batch + 1, "versions": result["context_versions_after"], "gepa": gepa["state"], "cost": self.budget.summary()}, ensure_ascii=False), flush=True)
            self.check_frozen()
            final = {arm: self.stores[arm].snapshot() for arm in ARMS}
            write_json(self.output / "final_contexts.json", {"contexts": final, "sha256": sha(final), "optimizer_closed_before_sealed": True})
            self.artifact["final_context_versions"] = {arm: snapshot["version"] for arm, snapshot in final.items()}
            self.artifact["state"] = "read_only_dev"
            self.artifact["dev_evaluation"] = self.read_only_stage("dev", self.cases, self.labels, {arm: final[arm] for arm in ("A0", "A1", "A4")})
            write_json(self.output / "results.json", self.artifact)
            print(json.dumps({"stage": "dev", "cost": self.budget.summary()}), flush=True)
            # First access to the sealed cases is strictly after optimizer close.
            self.check_frozen(content_files=True)
            sealed_cases = {case["case_id"]: case for case in selected_rows(self.content / "evaluation/sealed/cases.jsonl", set(self.ids["sealed_test"]))}
            sealed_labels = {label["case_id"]: label for label in selected_rows(self.content / "oracle/labels.jsonl", set(self.ids["sealed_test"]))}
            self.artifact["state"] = "sealed_milestone"
            frozen_initial = {"A0": self.initial, "A1": self.initial}
            initial_sealed = self.read_only_stage("sealed", sealed_cases, sealed_labels, frozen_initial)
            evolved_sealed = self.read_only_stage("sealed_final", sealed_cases, sealed_labels, {arm: final[arm] for arm in ("A2", "A3", "A4")})
            comparisons = {"A0": {"initial": initial_sealed["A0"]["summary"], "final": initial_sealed["A0"]["summary"], "same_context_reused": True}, "A1": {"initial": initial_sealed["A1"]["summary"], "final": initial_sealed["A1"]["summary"], "same_context_reused": True}}
            for arm in ("A2", "A3", "A4"):
                comparisons[arm] = {"initial": initial_sealed["A1"]["summary"], "final": evolved_sealed[arm]["summary"], "static_initial_reports_shared": True, "quality_delta": evolved_sealed[arm]["summary"]["mean_report_quality"] - initial_sealed["A1"]["summary"]["mean_report_quality"]}
            self.artifact["sealed_milestone"] = {"optimizer_closed": True, "selection_eligible": False, "root_count": 12, "initial": initial_sealed, "final": evolved_sealed, "comparisons": comparisons, "blinded_independent_review": "pending"}
            if self.offline_full:
                from battery_platform.app.agent.executor import run_agent
                self.check_frozen(content_files=True)
                summaries, count = Counter(), 0
                source_paths = [self.content / "cases/cold_start.jsonl", *sorted((self.content / "streams").glob("evolution_round_*.jsonl")), self.content / "evaluation/dev/cases.jsonl", self.content / "evaluation/sealed/cases.jsonl"]
                for source_path in source_paths:
                    for case in read_jsonl(source_path):
                        self.check_frozen()
                        result = run_agent(input_payload(case, self.initial, days=10), llm=False, skill_library=None)
                        summaries[result["report"]["status"]] += 1; count += 1
                self.artifact["offline_A0"] = {"root_count": count, "status_counts": dict(summaries), "provider_calls": 0, "interpretation": "complete deterministic execution coverage only; no LLM generalization result"}
                self.check_frozen(content_files=True)
            self.artifact["state"] = "completed"
        except KeyboardInterrupt:
            self.artifact.update(state="cancelled", stopped_reason="keyboard_interrupt")
        except Exception as exc:
            self.artifact.update(state="cancelled" if self.budget.cancelled() else "stopped_with_partial_results", stopped_reason=type(exc).__name__)
        finally:
            self.artifact["protocol_sha256"] = self.protocol["protocol_sha256"]
            self.artifact["cost"] = self.budget.summary()
            if self.prior:
                self.artifact["cost"]["combined_http_attempts"] = self.budget.attempts + self.prior["cumulative_cost"]["http_attempts"]
                self.artifact["cost"]["combined_charged_tokens"] = self.budget.charged_tokens + self.prior["cumulative_cost"]["charged_tokens"]
            self.artifact["finished_at"] = datetime.now(timezone.utc).isoformat()
            self.artifact["last_contexts"] = {arm: self.stores[arm].snapshot() for arm in ARMS}
            write_json(self.output / "results.json", self.artifact)
            write_json(self.output / "summary.json", {"state": self.artifact["state"], "protocol_sha256": self.protocol["protocol_sha256"], "cost": self.artifact["cost"], "batches_completed": len(self.artifact["batches"]), "evolution": {arm: summarize_records([record for batch in self.artifact["batches"] for record in batch["records"] if record["arm"] == arm]) for arm in ARMS}, "dev": {arm: value["summary"] for arm, value in self.artifact["dev_evaluation"].items()}, "sealed": self.artifact["sealed_milestone"].get("comparisons", {}), "offline_A0": self.artifact["offline_A0"], "semantic_blind_review": "pending"})
        return self.artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("battery_platform/reports/v2_agent/preregistered_pilot_v1"))
    parser.add_argument("--max-calls", type=int, default=200)
    parser.add_argument("--max-tokens", type=int, default=2_000_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-full-offline", action="store_true")
    parser.add_argument("--prior-run", type=Path, help="Deduct preserved prior-run cost from the combined authorized budget")
    args = parser.parse_args()
    if not 1 <= args.max_calls <= 200 or not 1 <= args.max_tokens <= 2_000_000:
        parser.error("budget must be within authorized 200 calls / 2M tokens")
    pilot = Pilot(args.out, max_calls=args.max_calls, max_tokens=args.max_tokens, workers=args.workers, offline_full=not args.skip_full_offline, prior_run=args.prior_run)
    old_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda signum, frame: interrupt_budget(pilot.budget))
    try:
        artifact = pilot.execute()
    finally:
        signal.signal(signal.SIGINT, old_sigint)
    print(json.dumps({"state": artifact["state"], "output": str(pilot.output), "cost": artifact["cost"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
