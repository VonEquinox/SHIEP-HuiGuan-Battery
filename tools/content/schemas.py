"""Published JSON Schema contracts (Draft 2020-12)."""
from pathlib import Path
from .common import SCHEMA_VERSION, write_json

OBSERVATION = {
    "type": "object", "required": ["observation_id", "metric", "value", "unit", "timestamp", "method_id", "instrument_id", "source", "provenance", "uncertainty", "quality_flags", "available_after"],
    "properties": {"observation_id": {"type": "string"}, "metric": {"type": "string"}, "value": {"type": ["number", "null"]}, "unit": {"type": "string", "minLength": 1}, "timestamp": {"type": "string", "format": "date-time"}, "uncertainty": {"type": "object"}, "quality_flags": {"type": "array", "items": {"type": "string"}}, "available_after": {"type": "string"}},
    "allOf": [{"if": {"properties": {"value": {"type": "null"}}}, "then": {"required": ["missing_reason"]}}],
}
TEST = {
    "type": "object", "required": ["test_id", "purpose", "applicable_hypotheses", "prerequisite_inputs", "required_skill", "allowed_procedure_ids", "duration_minutes", "cost_units", "result_enum", "unit", "failure_possible", "destructive", "needs_new_authorization"],
    "properties": {"test_id": {"type": "string"}, "duration_minutes": {"type": "number", "minimum": 0}, "cost_units": {"type": "number", "minimum": 0}, "result_enum": {"type": "array", "minItems": 1}, "destructive": {"type": "boolean"}, "needs_new_authorization": {"type": "boolean"}},
}
CASE = {
    "type": "object", "required": ["schema_version", "case_id", "root_scenario_id", "parent_id", "origin", "source_refs", "asset_context", "initial_visible", "test_catalog", "observation_model", "split_tags"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION}, "case_id": {"type": "string"}, "root_scenario_id": {"type": "string"}, "parent_id": {"type": ["string", "null"]},
        "origin": {"enum": ["real_experimental", "real_operational", "literature", "physics_simulated", "expert_synthetic", "public_generated"]}, "source_refs": {"type": "array"},
        "asset_context": {"type": "object", "required": ["installation_id", "physical_cell_id", "chemistry", "protocol_id", "namespace", "provenance"]},
        "initial_visible": {"type": "object", "required": ["cutoff", "observations", "known_missing"], "properties": {"cutoff": {"type": "string", "format": "date-time"}, "observations": {"type": "array", "items": OBSERVATION}, "known_missing": {"type": "array"}, "predictions": {"type": "array", "items": {"type": "object", "required": ["prediction_id", "model_version", "target_definition", "head", "support", "distribution", "calibration_status", "visible_cutoff"]}}}},
        "test_catalog": {"type": "array", "items": TEST}, "observation_model": {"type": ["object", "null"]}, "split_tags": {"type": "object", "required": ["split", "difficulty", "domain"]},
    },
    "not": {"anyOf": [{"required": [field]} for field in ["hidden_truth", "branches", "feedback_events", "expected_behavior", "oracle", "labels"]]},
}
FEEDBACK = {
    "type": "object", "required": ["feedback_id", "case_id", "report_version", "author_role", "observed_at", "structured", "free_text", "evidence_ids", "assertion_targets", "verification_status", "origin", "extraction_targets"],
    "properties": {"free_text": {"type": "string", "minLength": 1}, "evidence_ids": {"type": "array", "items": {"type": "string"}}, "structured": {"type": "object", "required": ["completed_tests", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items"]}, "extraction_targets": {"type": "array", "items": {"type": "object", "required": ["field", "span", "evidence_ids"], "properties": {"span": {"type": "object", "required": ["start", "end", "text"]}}}}},
}
LABEL = {
    "type": "object", "required": ["case_id", "root_scenario_id", "schema_version", "hidden_truth", "branches", "feedback_events", "expected_behavior", "expected_patch", "split_tags"],
    "properties": {"hidden_truth": {"type": "object", "required": ["status", "root_cause", "candidate_causes", "is_real_confirmation"]},
                   "branches": {"type": "array", "items": {"type": "object", "required": ["branch_id", "from", "test_id", "result", "reveal", "next_state", "observation_only"]}},
                   "feedback_events": {"type": "array", "items": FEEDBACK}, "expected_patch": {"type": "object", "required": ["operation", "must_preserve"], "properties": {"operation": {"enum": ["ADD", "REVISE", "DEPRECATE", "CONFLICT", "NO_UPDATE"]}}},
                   "expected_behavior": {"type": "object", "required": ["required", "acceptable", "prohibited", "unknown_allowed", "weights", "weight_basis"]}},
}
SKILL = {
    "type": "object", "required": ["skill_id", "version", "origin", "schema_version", "supported_chemistries", "required_inputs", "allowed_tools", "forbidden_claims", "references", "editable_sections", "tests", "license_status"],
    "properties": {"skill_id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"}, "allowed_tools": {"type": "array", "items": {"type": "string"}}, "references": {"type": "array"}, "license_status": {"enum": ["approved_synthetic", "approved", "pending_review", "restricted", "blocked"]}},
}
PARENTAGE = {"type": "object", "required": ["case_id", "root_scenario_id", "parent_id", "split", "kind"], "properties": {"parent_id": {"type": ["string", "null"]}, "kind": {"enum": ["root", "observation_branch"]}}}
KNOWLEDGE = {"type": "object", "required": ["evidence_id", "origin", "license_status", "title", "text"], "properties": {"evidence_id": {"type": "string"}, "text": {"type": "string"}, "license_status": {"type": "string"}}}
FIXTURE = {"type": "object", "required": ["fixture_id", "schema_version", "kind", "synthetic", "data_scope", "generated_by", "inputs", "oracle"], "properties": {"synthetic": {"const": True}, "data_scope": {"const": "demo_synthetic"}, "kind": {"type": "string", "minLength": 1}, "inputs": {"type": "object"}, "oracle": {"type": "object"}}}
EXAMPLE = {"type": "object", "required": ["example_id", "example_type", "source_case_id", "root_scenario_id"], "properties": {"example_type": {"enum": ["positive", "hard_negative", "insufficient_evidence"]}}}
PROBE = {"type": "object", "required": ["probe_id", "prompt", "required", "prohibited", "scope"], "properties": {"prompt": {"type": "string"}}}
PACKAGE_MANIFEST = {"type": "object", "required": ["content_version", "schema_version", "creator", "generation_method", "root_scenario_count", "child_sample_count", "split_counts", "public_paths", "evaluator_only_paths", "files"], "properties": {"root_scenario_count": {"const": 2400}, "files": {"type": "object", "additionalProperties": {"type": "object", "required": ["sha256", "bytes"], "properties": {"sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "bytes": {"type": "integer", "minimum": 0}}}}}}


def simple_document(required: list[str]) -> dict:
    return {"type": "object", "required": required}


def write_schemas(out: Path) -> None:
    for name, schema in (("case", CASE), ("observation", OBSERVATION), ("feedback", FEEDBACK), ("oracle-label", LABEL), ("skill-manifest", SKILL), ("parentage", PARENTAGE), ("knowledge", KNOWLEDGE), ("fixture", FIXTURE), ("skill-example", EXAMPLE), ("probe", PROBE), ("package-manifest", PACKAGE_MANIFEST)):
        write_json(out / f"{name}.schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"urn:huiguan:{name}:v1", **schema})
