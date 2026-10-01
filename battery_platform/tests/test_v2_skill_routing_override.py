"""Frozen Context text edits affect routing, without changing eligibility."""
import json

import pytest

from app.agent import ContextStore, SkillLibrary, run_agent
from app.agent.gepa_service import FrozenSkills


def library(root):
    for sid, keyword, required in [("a-static", "temperature", []), ("z-context", "voltage", ["observations"])]:
        path = root / "skills" / sid
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(json.dumps({"skill_id": sid, "license_status": "approved_synthetic",
            "version": "1", "supported_chemistries": ["LFP"], "required_inputs": required,
            "allowed_tools": ["get_signal_evidence"], "route_keywords": [keyword]}))
    return SkillLibrary(root, max_skills=1)


def test_snapshot_routing_description_changes_index_without_loading_bodies(tmp_path):
    original = library(tmp_path)
    visible = {"asset": {"chemistry": "LFP"}, "observations": [{"summary": "temperature sensor drift"}]}
    changed = original.with_context_overrides({"z-context": {"routing_description": "temperature sensor drift"}})
    assert original.route(visible)[0]["skill_id"] == "a-static"
    assert changed.route(visible)[0]["skill_id"] == "z-context"
    assert original.route(visible)[0]["skill_id"] == "a-static"  # No shared mutable index.
    assert changed.route({**visible, "asset": {"chemistry": "NCM"}}) == []
    assert not any(row["skill_id"] == "z-context" for row in changed.route({"asset": {"chemistry": "LFP"}, "symptoms": "temperature sensor drift"}))
    with pytest.raises(ValueError, match="immutable"):
        original.with_context_overrides({"z-context": {"allowed_tools": ["approve"]}})


def test_cjk_routing_terms_match_current_observation(tmp_path):
    original = library(tmp_path)
    routed = original.with_context_overrides({"z-context": {"routing_description": "通道温度异常复核"}})
    assert routed.route({"asset": {"chemistry": "LFP"}, "observations": [{"summary": "温度异常"}]})[0]["skill_id"] == "z-context"


@pytest.mark.parametrize("frozen", [False, True])
def test_executor_uses_current_snapshot_routing_overlay_only(tmp_path, frozen):
    original = library(tmp_path)
    for sid in ("a-static", "z-context"):
        (tmp_path / "skills" / sid / "SKILL.md").write_text("Retain unknowns and cite observations.")
    store = ContextStore()
    store.apply([{"operation": "SKILL_REVISE", "skill_id": "z-context", "fields": {"routing_description": "temperature sensor drift"}}],
                expected_version=0, regression={"passed": True, "hard_failures": [], "split": "dev"})
    visible = {"asset_id": "a", "installation_id": "i", "visible_cutoff": "2026-09-01T00:00:00Z",
               "asset": {"chemistry": "LFP"}, "observations": [{"evidence_id": "e", "summary": "temperature sensor drift"}]}
    chosen = FrozenSkills(original) if frozen else original
    result = run_agent(visible, llm=False, skill_library=chosen, context_store=store)
    assert result["run"]["selected_skills"][0]["skill_id"] == "z-context"
    static = run_agent(visible, llm=False, skill_library=chosen, context_store=ContextStore())
    assert static["run"]["selected_skills"][0]["skill_id"] == "a-static"
