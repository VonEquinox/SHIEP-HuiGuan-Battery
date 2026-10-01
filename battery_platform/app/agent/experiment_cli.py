"""Reproducible bounded cloud smoke for A0–A4; not a statistical benchmark.

Run from the repository: PYTHONPATH=battery_platform uv run python -m
app.agent.experiment_cli --output battery_platform/reports/v2_agent/cloud_smoke.json
Credentials are supplied only through BATTERY_LLM_* environment variables.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .context import ContextStore
from .evaluation import GEPASearch, ReplayEvaluator
from .executor import run_agent
from .llm import OpenAICompatibleClient
from .skills import SkillLibrary


class JSONReportAdapter:
    """One provider call per report fixes the cost of this small comparison.

    The executor still runs the program test-ranker before building context.
    The separate single-report probe exercises provider-selected function calls.
    """
    def __init__(self, client):
        self.client = client

    def __getattr__(self, name):
        if name == "complete":
            raise AttributeError(name)
        return getattr(self.client, name)

    def generate_json(self, messages, schema=None):
        return self.client.generate_json(messages, schema=schema)


def smoke_cases(split="evolution"):
    cases = []
    for index in range(2):
        cutoff = f"2026-09-{index + 1:02d}T12:00:00Z"
        visible = {"asset_id": f"cloud-smoke-asset-{index}", "installation_id": f"cloud-smoke-installation-{index}",
                   "visible_cutoff": cutoff, "asset": {"chemistry": "LFP", "protocol_id": "DEMO-PROTOCOL-READONLY"},
                   "observations": [{"evidence_id": f"smoke-ev-{index}", "timestamp": cutoff,
                                     "metric": "channel_review", "value": 1, "unit": "categorical",
                                     "summary": "Synthetic channel records disagree with independent readings; cause remains unverified."}],
                   "test_catalog": [{"test_id": "T_CHANNEL_CHECK", "authorized": True,
                                     "required_qualifications": ["instrumentation"],
                                     "distinguishes": ["acquisition_bias", "physical_state_difference"],
                                     "duration_minutes": 15}],
                   "authorization": {"authorized_test_ids": ["T_CHANNEL_CHECK"], "qualifications": ["instrumentation"], "round_budget": 3}}
        root = f"bounded-smoke-{split}-{index}"
        cases.append({"case_id": root, "root_scenario_id": root, "split": split, "synthetic": True,
                      "initial_visible": visible, "hidden_truth": {"unresolved": True, "requires_inspection": True},
                      "expected_behavior": {"acceptable_statuses": ["insufficient_evidence", "suspected"], "acceptable_tests": ["T_CHANNEL_CHECK"]},
                      # Feedback is revealed only after this report is frozen.
                      "feedback": {"feedback_id": f"smoke-feedback-{index}", "author_id": "synthetic-engineer",
                                   "free_text": "复核尚未确认根因；请保留单体差异和采集偏差两种可能，不能把人员描述视为已证实规律。",
                                   "verification_status": "reported", "scope": {"chemistry": "LFP"},
                                   "available_at": cutoff, "provenance": "expert_synthetic"}})
    return cases


def execute(output: Path):
    client = OpenAICompatibleClient.from_env()
    if client is None:
        raise ValueError("BATTERY_LLM_API_KEY required for a live cloud experiment")
    adapter = JSONReportAdapter(client)
    library = SkillLibrary(Path(__file__).resolve().parents[3] / "content_v1")
    evaluator = ReplayEvaluator()
    frozen = {"llm_model": client.model, "agent_version": "single-agent-v2.0", "numerical_model": "none-bound-unverified-synthetic-signals",
              "max_body_skills": 4, "max_tool_calls": 12, "report_provider_call_budget": 1,
              "root_count_per_arm": 2, "sealed_access": False}
    cases = smoke_cases()
    selection = smoke_cases("dev")[:1]
    candidate_search = GEPASearch(rollout_budget=2, candidate_budget=1, batch_size=1)
    gepa_runs = []
    def optimize(batch, store):
        original_snapshot = store.snapshot()
        def evaluate_candidate(candidate, events):
            snapshot = copy.deepcopy(original_snapshot)
            snapshot["skills"].setdefault("data-quality", {}).update(candidate["fields"])
            candidate_store = ContextStore(initial_snapshot=snapshot)
            scores, failures = [], []
            for event in events:
                visible = copy.deepcopy(event["initial_visible"])
                visible["context_snapshot"] = snapshot
                result = run_agent(visible, llm=adapter, skill_library=library, context_store=candidate_store)
                scores.append(int(result["run"]["cloud_report_valid"]))
                if not result["run"]["cloud_report_valid"]:
                    failures.append("invalid_structured_report")
            return {"score": sum(scores) / len(scores), "hard_failures": failures,
                    "semantic_expert_validation": "not_performed", "metric": "strict_structure_boundary_pass"}
        result = candidate_search.search(skill_id="data-quality", current_fields={"instructions": "Retain counterevidence and distinguish reported feedback from confirmed facts."},
                                         feedback_events=batch, selection_events=selection, evaluate=evaluate_candidate, llm=adapter)
        if result["activation_update"]:
            result["activation"] = store.apply([result["activation_update"]], expected_version=store.snapshot()["version"],
                                               source_scope="evolution", regression=result["regression"])["state"]
        gepa_runs.append(result)
        return {k: v for k, v in result.items() if k != "candidates"}
    results = []
    for arm in ("A0", "A1", "A2", "A3", "A4"):
        results.append(evaluator.evaluate(arm, cases, llm=adapter, skill_library=library, frozen_config=frozen,
                                         batch_optimizer=optimize if arm == "A4" else None, batch_size=1))
    artifact = {"label": "Bounded synthetic/replay diagnosis smoke; no statistical generalization claim",
                "live_cloud": True, "sealed_access": False, "frozen_config": frozen,
                "arms": results, "gepa": gepa_runs, "provider_requests": client.request_count,
                "provider_failed_requests": client.failed_request_count, "provider_usage": client.total_usage,
                "limits": {"root_count_per_arm": 2, "maximum_report_rollouts": 14, "maximum_gepa_proposals": 2,
                           "semantic_expert_validation": "not_performed", "real_field_feedback": False}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("battery_platform/reports/v2_agent/cloud_smoke.json"))
    args = parser.parse_args()
    artifact = execute(args.output)
    print(json.dumps({"output": str(args.output), "provider_requests": artifact["provider_requests"],
                      "provider_failed_requests": artifact["provider_failed_requests"], "usage": artifact["provider_usage"],
                      "arms": [{"arm": a["arm"], "root_count": a["root_count"],
                                "cloud_valid_reports": sum(r["run"].get("cloud_report_valid", False) for r in a["records"]),
                                "context_version": a["final_context_snapshot"]["version"]} for a in artifact["arms"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
