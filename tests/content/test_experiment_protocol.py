"""Pre-network experiment split and budget regressions, never benchmark data."""
import json
from pathlib import Path

import pytest

from tools.content.experiment import CostBudget, ExperimentCancelled, Pilot, cumulative_cost, input_payload, interrupt_budget, select_ids, selected_rows, verify_content_files
from tools.content.generate import make_root


def test_preregistered_roots_are_distinct_and_cover_twelve_buckets():
    ids = select_ids()
    assert all(len(values) == len(set(values)) == 12 for values in ids.values())
    assert not set(ids["evolution"]) & set(ids["dev"])
    assert not set(ids["dev"]) & set(ids["sealed_test"])
    assert not set(ids["evolution"]) & set(ids["sealed_test"])


def test_resume_deducts_cumulative_cost_not_only_latest_run():
    assert cumulative_cost({"http_attempts": 150, "charged_tokens_including_unknown_failures": 1200000, "combined_http_attempts": 179, "combined_charged_tokens": 1559656}) == (179, 1559656)


def test_frozen_manifest_checks_real_bytes_even_if_manifest_unchanged(tmp_path):
    from tools.content.common import digest
    artifact = tmp_path / "SKILL.md"
    artifact.write_text("original")
    manifest = {"files": {"SKILL.md": {"sha256": digest(artifact)}}}
    verify_content_files(tmp_path, manifest)
    artifact.write_text("changed without updating manifest")
    with pytest.raises(RuntimeError):
        verify_content_files(tmp_path, manifest)


def test_cancel_before_feedback_prevents_any_context_update(tmp_path):
    pilot = Pilot.__new__(Pilot)
    (tmp_path / "CANCEL").touch()
    pilot.budget = CostBudget(tmp_path, max_calls=1, max_tokens=10000, cancel_file=tmp_path / "CANCEL")
    with pytest.raises(ExperimentCancelled):
        pilot.feedback("A3", {"metrics": {"cloud_report_valid": True}}, 0)


def test_oracle_filter_does_not_decode_unselected_label(tmp_path):
    path = tmp_path / "labels.jsonl"
    path.write_text('{"case_id":"wanted","hidden_truth":{"status":"known"}}\n{"case_id":"sealed", invalid JSON must not be decoded}\n')
    assert selected_rows(path, {"wanted"}) == [{"case_id": "wanted", "hidden_truth": {"status": "known"}}]


def test_runtime_payload_rebases_time_and_excludes_truth():
    case, _, _, _ = make_root(0, 8, 0, {})
    snapshot = {"context_snapshot_id": "context-v0", "version": 0, "memories": [], "skills": {}}
    payload = input_payload(case, snapshot, days=2)
    assert payload["visible_cutoff"] == "2026-09-03T10:00:00Z"
    assert payload["observations"][0]["timestamp"] == payload["visible_cutoff"]
    assert "hidden_truth" not in payload
    assert "branches" not in payload
    assert "sealed_test" not in json.dumps(payload)
    assert payload["installation_id"] == case["asset_context"]["installation_id"]


def test_cancel_file_prevents_any_provider_attempt(tmp_path):
    cancellation = tmp_path / "CANCEL"
    cancellation.touch()
    budget = CostBudget(tmp_path, max_calls=1, max_tokens=10000, cancel_file=cancellation)
    with pytest.raises(ExperimentCancelled):
        budget.invoke([{"role": "user", "content": "test"}], tag="never")
    assert budget.summary()["http_attempts"] == 0


def test_ctrl_c_marks_cancel_before_worker_pool_shutdown(tmp_path):
    budget = CostBudget(tmp_path, max_calls=2, max_tokens=10000, cancel_file=tmp_path / "CANCEL")
    with pytest.raises(KeyboardInterrupt):
        interrupt_budget(budget)
    assert budget.cancelled()
    with pytest.raises(ExperimentCancelled):
        budget.invoke([{"role": "user", "content": "queued worker"}], tag="must_not_start")
    assert budget.summary()["http_attempts"] == 0


def test_interrupt_cancels_queued_futures_and_retains_completed_reports(tmp_path, monkeypatch):
    from concurrent.futures import Future, as_completed
    import tools.content.experiment as experiment
    completed, queued, active = Future(), Future(), Future()
    completed.set_result({"root": "complete"})
    active.set_running_or_notify_cancel()
    active.set_result({"root": "active_finished"})
    calls = 0

    def interrupted_as_completed(pending):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield completed
            raise KeyboardInterrupt
        yield from as_completed(pending)

    monkeypatch.setattr(experiment, "as_completed", interrupted_as_completed)
    pilot = Pilot.__new__(Pilot)
    pilot.budget = CostBudget(tmp_path, max_calls=1, max_tokens=10000, cancel_file=tmp_path / "CANCEL")
    records, failures = [], []
    assert pilot.collect_futures({completed: ("A1", "complete"), queued: ("A2", "queued"), active: ("A3", "active_finished")}, records.append, failures)
    assert queued.cancelled() and pilot.budget.cancelled()
    assert {record["root"] for record in records} == {"complete", "active_finished"}
    assert failures == [{"arm": "A2", "root": "queued", "error_type": "CancelledError"}]


def test_failed_http_attempt_consumes_budget_and_retains_unknown_cost(tmp_path, monkeypatch):
    from battery_platform.app.agent.llm import LLMError, OpenAICompatibleClient

    class FailedTransport:
        last_usage = {}
        retries = 0

        def complete(self, messages, response_format=None):
            raise LLMError("controlled transport failure in a unit test")

    monkeypatch.setattr(OpenAICompatibleClient, "from_env", classmethod(lambda cls: FailedTransport()))
    budget = CostBudget(tmp_path, max_calls=1, max_tokens=10000, cancel_file=tmp_path / "CANCEL")
    with pytest.raises(LLMError):
        budget.invoke([{"role": "user", "content": "test"}], tag="failure")
    assert budget.summary()["http_attempts"] == 1
    assert budget.summary()["failed_calls"] == 1
    assert budget.summary()["charged_tokens_including_unknown_failures"] > 4096
    assert budget.rows[0]["cost_basis"] == "unknown_charge_upper_bound"
    with pytest.raises(LLMError):
        budget.invoke([{"role": "user", "content": "test"}], tag="overbudget")
    assert budget.summary()["http_attempts"] == 1
