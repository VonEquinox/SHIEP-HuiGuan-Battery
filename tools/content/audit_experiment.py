"""Read-only audit of completed cloud artifacts; never invokes a model/optimizer.

Preserved provider answers are checked against the frozen report contract. The
audit does not rescore the preregistered experiment or change any context.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

from battery_platform.app.agent.context import ContextStore
from battery_platform.app.agent.contracts import validate_report
from battery_platform.app.agent.executor import _evidence_ids, _evidence_records
from battery_platform.app.agent.skills import SkillLibrary

from .common import digest, read_jsonl, write_json
from .experiment import REPOSITORY, input_payload, select_ids, selected_rows, sha, verify_content_files


def numerical_token_diagnostics(raw: dict, evidence_records: dict) -> list[dict]:
    diagnostics = []
    original = r"(?<![\w-])[-+]?\d+(?:\.\d+)?(?![\w-])"
    ascii_boundary = r"(?<![A-Za-z0-9_-])[-+]?\d+(?:\.\d+)?(?![A-Za-z0-9_-])"
    for fact in raw.get("facts", []):
        numbers = set()

        def collect(value):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numbers.add(float(value))
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
            elif isinstance(value, str):
                numbers.update(float(v) for v in re.findall(original, value))

        for eid in fact.get("evidence_ids", []):
            collect(evidence_records.get(eid, {}))
        unsupported = lambda tokens: [token for token in tokens if not any(math.isclose(float(token), number, abs_tol=1e-9) for number in numbers)]
        original_tokens = re.findall(original, fact["claim"])
        original_mismatches = unsupported(original_tokens)
        if original_mismatches:
            adjusted = re.findall(ascii_boundary, fact["claim"])
            diagnostics.append({"claim": fact["claim"], "original_tokens": original_tokens, "original_unmatched_tokens": original_mismatches,
                                "ascii_boundary_tokens": adjusted, "ascii_boundary_unmatched_tokens": unsupported(adjusted),
                                "interpretation": "posthoc tokenizer analysis only; preregistered scores and production validator unchanged"})
    return diagnostics


def audit(output: Path) -> dict:
    output = output.resolve()
    protocol = json.loads((output / "protocol.json").read_text())
    results = json.loads((output / "results.json").read_text())
    if results["state"] != "completed" or not results["sealed_milestone"]["optimizer_closed"]:
        raise ValueError("audit requires completed run with optimizer already closed")
    content = REPOSITORY / "content_v1"
    manifest = json.loads((content / "manifest.json").read_text())
    verify_content_files(content, manifest)
    if digest(content / "manifest.json") != protocol["content_manifest_sha256"]:
        raise ValueError("content manifest differs from preregistration")
    changed = [p for p, expected in protocol["code_sha256"].items() if digest(REPOSITORY / p) != expected]
    if changed:
        raise ValueError("runtime code differs from preregistration: " + ",".join(changed))
    final = json.loads((output / "final_contexts.json").read_text())
    if sha(final["contexts"]) != final["sha256"]:
        raise ValueError("final context hash mismatch")
    library = SkillLibrary(content)
    ids = set(sum(protocol["root_ids"].values(), []))
    cases = {}
    for source in ("streams/evolution_round_01.jsonl", "evaluation/dev/cases.jsonl", "evaluation/sealed/cases.jsonl"):
        cases.update({case["case_id"]: case for case in selected_rows(content / source, ids)})
    contexts = final["contexts"]
    initial = json.loads((output / "context_v0.json").read_text())
    failures, raw_refs, immutable_changes = [], Counter(), Counter()
    exact_input_hashes = 0
    records = []
    for path in sorted((output / "partial_records").rglob("*.json")):
        record = json.loads(path.read_text())
        records.append(record)
        arm, stage = record["arm"], path.parent.name
        if stage.startswith("evolution_"):
            batch = int(stage.rsplit("_", 1)[1])
            days = batch - 1
            snapshot = initial if batch == 1 else json.loads((output / f"contexts/{arm}_batch_{batch-1:02d}.json").read_text())
        else:
            days = 10
            snapshot = contexts[arm] if stage in {"dev", "sealed_final"} else initial
        payload = input_payload(cases[record["root_scenario_id"]], snapshot, days=days)
        if sha(payload) != record["input_sha256"]:
            raise ValueError("frozen prediction input hash differs: " + str(path))
        exact_input_hashes += 1
        memories = ContextStore(initial_snapshot=snapshot).search(payload["symptoms"], scope={"installation_id": payload["installation_id"], "chemistry": payload["chemistry"], "protocol_id": payload["protocol_id"]}, cutoff=payload["visible_cutoff"])
        data = {"observations": payload["observations"], "memories": memories, "trace": record["tool_trace"], "skills": [library.load_skill(s["skill_id"]) for s in record["run"]["selected_skills"]]}
        feasible = {t["test_id"] for trace in record["tool_trace"] if trace["name"] == "rank_tests" for group in ("selected", "pending_authorization") for t in trace.get("result", {}).get(group, [])}
        diagnostic = record["provider_diagnostics"]
        item = {"stage": stage, "arm": arm, "root_scenario_id": record["root_scenario_id"], "actual_http_attempts": record["provider_cost"]["http_attempts"]}
        if diagnostic:
            raw = json.loads((output / diagnostic[0]["response_file"]).read_text())
            refs = set(raw.get("citations", [])) | {ref for fact in raw.get("facts", []) for ref in fact.get("evidence_ids", [])}
            refs |= {ref for h in raw.get("hypotheses", []) for field in ("supports", "contradicts") for ref in h.get(field, [])}
            for ref in refs - _evidence_ids(data):
                raw_refs[ref] += 1
            immutable_changes.update(diagnostic[0].get("immutable_changes", []))
            if record["metrics"]["cloud_report_valid"] is False:
                try:
                    validate_report(raw, evidence_ids=_evidence_ids(data), test_ids=feasible, installation_id=payload["installation_id"], cutoff=payload["visible_cutoff"], authorized_test_ids={"T_TIME_ALIGN", "T_CHANNEL_CHECK"}, evidence_records=_evidence_records(data))
                    item["reason"] = "not_reproduced_by_posthoc_contract_projection"
                except Exception as exc:
                    item["reason"] = str(exc)
                    item["numerical_token_diagnostics"] = numerical_token_diagnostics(raw, _evidence_records(data))
                item["reason_basis"] = "read-only contract validation of preserved actual provider final answer"
                failures.append(item)
        elif arm != "A0":
            item.update(reason="preflight_token_reservation_budget_blocked", reason_basis="inferred from frozen CostBudget code path and zero HTTP attempts; budget reserve exceeded remaining allowance")
            failures.append(item)
    ledger = list(read_jsonl(output / "provider_calls.jsonl"))
    cost = results["cost"]
    if len(ledger) != cost["http_attempts"] or sum(row["charged_tokens"] for row in ledger) != cost["charged_tokens_including_unknown_failures"]:
        raise ValueError("cost ledger differs from final summary")
    report = {"live_provider_calls_added": 0, "optimizer_closed": True, "training_eligible": False,
              "audit_code_sha256": digest(Path(__file__)), "frozen_runtime_and_content_verified": True,
              "content_files_checked": len(manifest["files"]), "runtime_files_checked": len(protocol["code_sha256"]), "exact_frozen_inputs_verified": exact_input_hashes,
              "direct_report_count": len(records), "direct_cloud_valid_reports": sum(r["metrics"]["cloud_report_valid"] is True for r in records),
              "raw_wrong_reference_count_including_hypotheses": sum(raw_refs.values()), "raw_wrong_reference_ids": dict(raw_refs), "raw_immutable_changes": dict(immutable_changes),
              "direct_report_failures": failures, "reason_counts": dict(Counter(f["reason"] for f in failures)),
              "original_numeric_rejections_resolved_by_ascii_token_analysis": sum(bool(f.get("numerical_token_diagnostics")) and all(not d["ascii_boundary_unmatched_tokens"] for d in f["numerical_token_diagnostics"]) for f in failures),
              "ledger_http_attempts": len(ledger), "finish_reasons": dict(Counter(row.get("finish_reason") for row in ledger)),
              "response_models": dict(Counter(row.get("response_model") for row in ledger)), "system_fingerprints": dict(Counter(row.get("system_fingerprint") for row in ledger)),
              "semantic_blind_review": "pending", "preregistered_scores_changed": False}
    write_json(output / "post_execution_audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.out)
    print(json.dumps({"frozen_verified": report["frozen_runtime_and_content_verified"], "exact_inputs": report["exact_frozen_inputs_verified"], "failure_reasons": report["reason_counts"], "raw_wrong_references": report["raw_wrong_reference_count_including_hypotheses"], "provider_calls_added": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
