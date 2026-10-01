"""Structural, physical-boundary and anti-leakage checks for frozen content."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .common import TOOL_WHITELIST, digest, read_jsonl
from .generate import BUCKETS, ERROR_TYPES, RESULT_TYPES, SPLIT_COUNTS, reference_voi
from .schemas import CASE, FEEDBACK, LABEL, OBSERVATION, PARENTAGE, SKILL, KNOWLEDGE, FIXTURE, EXAMPLE, PROBE, PACKAGE_MANIFEST, simple_document

FORBIDDEN_VISIBLE_KEYS = {"hidden_truth", "expected_behavior", "expected_patch", "branches", "feedback_events", "model_error", "oracle", "fleet_labels", "error_training"}


def forbidden_keys(value, prefix="") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = prefix + "." + key
            if key in FORBIDDEN_VISIBLE_KEYS:
                found.append(path)
            found.extend(forbidden_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_keys(child, f"{prefix}[{index}]"))
    return found


def validate_content(root: str | Path, *, check_hashes: bool = True) -> dict:
    root = Path(root)
    errors, warnings, checks = [], [], {}

    def require(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    def schema_check(row: dict, schema: dict, tag: str) -> None:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for issue in validator.iter_errors(row):
            errors.append(f"{tag}: {'.'.join(str(p) for p in issue.absolute_path)} {issue.message}")

    try:
        manifest = json.loads((root / "manifest.json").read_text())
        all_json = list(root.rglob("*.json"))
        for path in all_json:
            json.loads(path.read_text())
        paths = [root / "cases/cold_start.jsonl", *sorted((root / "streams").glob("evolution_round_*.jsonl")), root / "evaluation/dev/cases.jsonl", root / "evaluation/sealed/cases.jsonl"]
        cases = [case for path in paths for case in read_jsonl(path)]
        labels = read_jsonl(root / "oracle/labels.jsonl")
        observation_rows = read_jsonl(root / "oracle/observations.jsonl")
        parents = read_jsonl(root / "manifests/parentage.jsonl")
        splits = json.loads((root / "manifests/splits.json").read_text())
        evidence = read_jsonl(root / "knowledge/evidence.jsonl")
    except (OSError, ValueError) as exc:
        return {"status": "failed", "errors": [f"package cannot be parsed: {type(exc).__name__}"], "warnings": [], "checks": {}}
    case_ids = {case["case_id"] for case in cases}
    schema_check(manifest, PACKAGE_MANIFEST, "manifest.json")
    for path in all_json:
        relative = str(path.relative_to(root))
        data = json.loads(path.read_text())
        if relative.startswith("schemas/"):
            try:
                Draft202012Validator.check_schema(data)
            except Exception:
                errors.append("invalid published JSON schema: " + relative)
        elif relative == "manifests/splits.json":
            schema_check(data, simple_document(["schema_version", "frozen", "counts", "root_assignments", "grouping"]), relative)
        elif relative == "manifests/near_duplicates.json":
            schema_check(data, simple_document(["cross_split_clusters", "clusters", "limitations"]), relative)
        elif relative == "manifests/provenance.json":
            schema_check(data, simple_document(["creator", "origin", "real_measurement_count", "licenses", "cloud", "forbidden_uses"]), relative)
        elif relative == "manifests/test_catalog.json":
            schema_check(data, simple_document(["schema_version", "namespace", "tests"]), relative)
        elif relative == "manifests/cloud_enrichment.json":
            schema_check(data, simple_document(["skills", "buckets", "ledger", "provenance"]), relative)
        elif relative == "reports/validation.json":
            schema_check(data, simple_document(["schema_version", "status", "errors", "warnings", "checks", "hashes_checked"]), relative)
        elif "/checks/" in relative:
            schema_check(data, simple_document(["required", "termination_conditions", "example_ids"]), relative)
    for entry in evidence:
        schema_check(entry, KNOWLEDGE, "knowledge:" + str(entry.get("evidence_id")))
    for fixture_path in (root / "fixtures").glob("*.jsonl"):
        for fixture in read_jsonl(fixture_path):
            schema_check(fixture, FIXTURE, str(fixture_path.relative_to(root)))
    for probe in read_jsonl(root / "evaluation/probes.jsonl"):
        schema_check(probe, PROBE, probe["probe_id"])
    by_id = {case["case_id"]: case for case in cases}
    label_by_id = {label["case_id"]: label for label in labels}
    observations = {row["observation_id"]: row for row in observation_rows}
    evidence_ids = {entry.get("evidence_id") or entry.get("knowledge_id") or entry.get("id") for entry in evidence}
    require(len(cases) == 2400 == len(case_ids), "expected 2400 unique roots")
    require(len(labels) == len(case_ids) and set(label_by_id) == case_ids, "oracle label roots must exactly match visible roots")
    require(len(observations) == len(observation_rows), "observation IDs must be unique")
    require(dict(Counter(c["split_tags"]["split"] for c in cases)) == SPLIT_COUNTS, "split root counts differ from 960/720/360/360")
    require(Counter(l["split_tags"]["main_bucket"] for l in labels) == Counter({bucket: 200 for bucket in BUCKETS}), "twelve buckets must each have 200 roots")
    parent_by_id = {row["case_id"]: row for row in parents}
    require(len(parent_by_id) == len(parents), "parentage IDs must be unique")
    for parent in parents:
        schema_check(parent, PARENTAGE, parent["case_id"])
        require(parent["root_scenario_id"] in case_ids, "parentage root does not exist")
        if parent["parent_id"]:
            require(parent["parent_id"] in parent_by_id, "parent pointer does not exist")
        require(parent["split"] == splits["root_assignments"].get(parent["root_scenario_id"]), "derived sample crosses root split")
        require(set(parent.get("observation_ids", [])) <= observations.keys(), "child observation reference missing")
    clusters, templates, signal_splits = defaultdict(set), defaultdict(set), defaultdict(set)
    installs, cells, all_initial_ids = {}, {}, set()
    behavior_counts, result_counts, update_counts, error_counts, fleet_variants = Counter(), Counter(), Counter(), Counter(), Counter()
    for case in cases:
        cid = case["case_id"]
        schema_check(case, CASE, cid)
        require(not forbidden_keys(case), f"public case has hidden fields: {cid}")
        require(case["parent_id"] is None and case["root_scenario_id"] == cid, "root case identity invalid")
        label = label_by_id.get(cid)
        if label is None:
            continue
        schema_check(label, LABEL, cid)
        tags = label["split_tags"]
        require(tags["split"] == case["split_tags"]["split"] == splits["root_assignments"].get(cid), "root split assignments disagree")
        clusters[tags["near_duplicate_cluster"]].add(tags["split"]); templates[tags["template_family"]].add(tags["split"])
        values = [(o["metric"], o["value"] * 1000 if o["unit"] == "V" else o["value"], "mV" if o["unit"] == "V" else o["unit"]) for o in case["initial_visible"]["observations"]]
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        signal_splits[fingerprint].add(tags["split"])
        asset = case["asset_context"]
        old_cell = installs.setdefault(asset["installation_id"], asset["physical_cell_id"])
        old_install = cells.setdefault(asset["physical_cell_id"], asset["installation_id"])
        require(old_cell == asset["physical_cell_id"] and old_install == asset["installation_id"], "installation/cell identity reused inconsistently")
        require(asset["namespace"] == "demo_synthetic", "synthetic root must stay demo_synthetic")
        require(not label["hidden_truth"]["is_real_confirmation"], "synthetic oracle cannot claim real confirmation")
        require(label["hidden_truth"]["root_cause"] not in json.dumps(case, ensure_ascii=False), f"root cause leaked into visible root {cid}")
        initial = case["initial_visible"]
        for obs in initial["observations"]:
            schema_check(obs, OBSERVATION, obs["observation_id"])
            require(obs["available_after"] == "start" and obs["timestamp"] <= initial["cutoff"], "initial observation is from the future")
            all_initial_ids.add(obs["observation_id"])
        for feedback in initial.get("visible_feedback", []):
            schema_check(feedback, FEEDBACK, feedback["feedback_id"])
            require(feedback["observed_at"] <= initial["cutoff"], "initial feedback is from the future")
            require(set(feedback["evidence_ids"]) <= {obs["observation_id"] for obs in initial["observations"]}, "initial feedback references an unseen measurement")
            for extraction in feedback["extraction_targets"]:
                span = extraction["span"]
                require(feedback["free_text"][span["start"]:span["end"]] == span["text"], "initial feedback span does not preserve raw text")
        require(not asset["observation_complete_cycle"] and not asset["soc_endpoints_equal"], "incomplete cycle must not be marked comparable efficiency")
        catalog = {test["test_id"]: test for test in case["test_catalog"]}
        reached = {"start"}
        branch_remaining = list(label["branches"])
        while branch_remaining:
            advance = [b for b in branch_remaining if b["from"] in reached]
            if not advance:
                break
            for branch in advance:
                reached.add(branch["next_state"]); branch_remaining.remove(branch)
        require(not branch_remaining, "unreachable branch graph")
        for branch in label["branches"]:
            require(branch["test_id"] in catalog, "branch test not in public catalog")
            require(branch["result"] in catalog[branch["test_id"]]["result_enum"], "branch result outside catalog")
            require(set(branch["reveal"]) <= observations.keys(), "branch observation reference missing")
            require(branch["branch_id"] in parent_by_id, "branch missing parentage")
            result_counts[branch["result"]] += 1
            for oid in branch["reveal"]:
                obs = observations.get(oid)
                if obs:
                    require(obs["root_scenario_id"] == cid, "branch leaks another root's observation")
                    require(obs["available_after"] == branch["test_id"], "observation reveal gate differs from selected test")
                    require(obs["timestamp"] > initial["cutoff"], "branch observations must have future availability")
        for feedback in label["feedback_events"]:
            schema_check(feedback, FEEDBACK, feedback["feedback_id"])
            require(set(feedback["evidence_ids"]) <= (set(observations) | all_initial_ids), "feedback evidence not resolvable")
            for extraction in feedback["extraction_targets"]:
                span = extraction["span"]
                require(feedback["free_text"][span["start"]:span["end"]] == span["text"], "feedback extraction must preserve raw text span")
            if feedback.get("is_injection_probe"):
                require(label["expected_patch"]["operation"] == "NO_UPDATE", "permission injection must not yield an accepted patch")
        for key in ("requires_initial_test", "normal_unsupported_or_insufficient", "conflicting_or_unresolved"):
            behavior_counts[key] += int(tags[key])
        update_counts[label["expected_patch"]["operation"]] += 1
        error_counts[label["error_training"]["error_type"]] += 1
        if label.get("fleet_labels"):
            fleet_variants[label["fleet_labels"]["variant"]] += 1
        model = case["observation_model"]
        if model:
            require(abs(sum(model["prior"].values()) - 1) < 1e-9, "prior probabilities do not normalize")
            for test, distributions in model["likelihoods"].items():
                for values in distributions.values():
                    require(all(0 <= v <= 1 for v in values.values()) and abs(sum(values.values()) - 1) < 1e-9, "test likelihood not normalized")
                require(abs(reference_voi(model, test) - label["active_test_oracle"]["reference_voi"][test]) < 1e-9, "VOI mathematical oracle mismatch")
    for obs in observation_rows:
        schema_check(obs, OBSERVATION, obs["observation_id"])
    require(all(len(v) == 1 for v in clusters.values()), "near-duplicate cluster crosses splits")
    require(all(len(v) == 1 for v in templates.values()), "mother template crosses splits")
    require(all(len(v) == 1 for v in signal_splits.values()), "identical normalized signals cross splits")
    for key, threshold in (("requires_initial_test", .30), ("normal_unsupported_or_insufficient", .20), ("conflicting_or_unresolved", .15)):
        require(behavior_counts[key] / max(1, len(cases)) >= threshold, f"coverage below threshold: {key}")
    require(set(RESULT_TYPES) <= result_counts.keys(), "mandatory test outcome coverage missing")
    require(set(ERROR_TYPES) <= error_counts.keys(), "mandatory error correction coverage missing")
    require({"ADD", "REVISE", "DEPRECATE", "CONFLICT", "NO_UPDATE"} <= update_counts.keys(), "required update/no-update coverage missing")
    skill_manifests = sorted((root / "skills").glob("*/manifest.json"))
    require(len(skill_manifests) == 16, "expected sixteen skill packs")
    example_count = 0
    for path in skill_manifests:
        skill = json.loads(path.read_text()); schema_check(skill, SKILL, str(path.relative_to(root)))
        require(set(skill["allowed_tools"]) <= TOOL_WHITELIST, "skill expands executable tools")
        require(set(skill["references"]) <= evidence_ids, "skill reference evidence missing")
        body = (path.parent / "SKILL.md").read_text()
        require(body.startswith("---\n") and body.count("\n---") >= 1, "skill YAML frontmatter missing")
        import yaml
        frontmatter = yaml.safe_load(body.split("---", 2)[1])
        require(set(frontmatter) == {"name", "description"} and frontmatter["name"] == path.parent.name, "skill standard metadata differs from folder")
        examples = sorted((path.parent / "examples").glob("*.json"))
        require(len(examples) >= 3, "each skill needs positive, negative and insufficient examples")
        for example_path in examples:
            sample = json.loads(example_path.read_text()); example_count += 1
            schema_check(sample, EXAMPLE, str(example_path.relative_to(root)))
            require(not forbidden_keys(sample), "public skill example contains hidden fields")
            root_ref = sample.get("root_scenario_id") or sample.get("case_ref", {}).get("root_scenario_id") or sample.get("case_id")
            require(root_ref in by_id and by_id[root_ref]["split_tags"]["split"] == "cold_start", "skill example must reference a cold root")
    from .fixtures import validate_fixtures
    fixture_result = validate_fixtures(root)
    errors.extend(fixture_result.get("errors", []))
    if check_hashes:
        for relative, entry in manifest.get("files", {}).items():
            path = (root / relative).resolve()
            require(path.is_relative_to(root.resolve()) and path.is_file(), "manifest file missing or escapes root")
            if path.is_file() and path.is_relative_to(root.resolve()):
                require(digest(path) == entry["sha256"], f"hash mismatch: {relative}")
        listed = set(manifest.get("files", {}))
        actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p != root / "manifest.json"}
        require(listed == actual, "manifest must hash every package file except itself")
    checks = {
        "S01": {"skill_count": len(skill_manifests), "tool_whitelist": True},
        "S02": {"example_count": example_count, "source": "cold_start_only"},
        "S03": {"roots": len(case_ids), "derived_observations": len(observations), "parentage": len(parents), "cross_split_clusters": sum(len(v) > 1 for v in clusters.values()), "cross_split_templates": sum(len(v) > 1 for v in templates.values())},
        "S04": {"visible_hidden_paths": "physically_separate", "library_allowlist": ["skills", "knowledge", "cases"]},
        "S05": {"branch_result_counts": dict(result_counts), "coverage": dict(behavior_counts)},
        "S06": {"feedback_raw_span_checks": len(labels)}, "S07": {"updates": dict(update_counts), "errors": dict(error_counts)},
        "S08": {"fleet_variants": dict(fleet_variants)},
        "S09": {"fixture_count": fixture_result["dispatch_count"], "coverage": fixture_result["coverage"]["dispatch"], "oracle": "independent exhaustive discrete-grid scheduler"},
        "S10": {"fixture_count": fixture_result["carbon_count"], "coverage": fixture_result["coverage"]["carbon"], "oracle": "deterministic arithmetic, recurrence and support functions"},
        "S11": {"real_measurements": 0, "origins": dict(Counter(c["origin"] for c in cases))},
        "S12": {"sealed_roots": SPLIT_COUNTS["sealed_test"], "public_library_access": "denied_by_allowlist", "expert_blind_review": "not_performed"},
    }
    warnings.extend(["Programmatic acceptance does not establish clinical/engineering validity on real devices.", "Broad physics generation recipe is shared across splits; root/entity/condition/mother-template groups are frozen independently.", "No independent professional blind review has been performed; LLM language outputs are supplemental synthetic content only."])
    return {"schema_version": "content-validation-v1", "status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings, "checks": checks, "hashes_checked": check_hashes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("content_v1"))
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args()
    result = validate_content(args.root)
    if args.write_report:
        from .common import write_json
        write_json(args.write_report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
