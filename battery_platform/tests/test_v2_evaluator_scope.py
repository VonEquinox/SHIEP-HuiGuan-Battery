"""API replay loading is proven with handmade sentinels, not released labels."""
import json
from pathlib import Path

import pytest

from app import api_evolution
from app.agent import ContextStore, ReplayEvaluator


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def miniature(tmp_path, monkeypatch):
    root = tmp_path / "content_v1"
    case = {"case_id": "manual-evolution", "asset_context": {"asset_id": "asset", "installation_id": "installation"},
            "initial_visible": {"cutoff": "2026-09-01T00:00:00Z", "observations": []}}
    write(root / "streams/cases.jsonl", json.dumps(case) + '\n{"case_id":"unrequested-root", invalid public sentinel}\n')
    write(root / "manifests/splits.json", json.dumps({"root_assignments": {"manual-evolution": "evolution", "sealed-sentinel": "sealed"}}))
    write(root / "manifests/test_catalog.json", json.dumps({"tests": []}))
    label = {"case_id": "manual-evolution", "hidden_truth": {"requires_inspection": True}, "expected_behavior": {"initial_status": "insufficient_evidence"}}
    write(root / "oracle/labels.jsonl", json.dumps(label) + '\n{"case_id":"sealed-sentinel", invalid hidden sentinel}\n')
    write(root / "evaluation/sealed/cases.jsonl", "SEALED FILE MUST NEVER OPEN\n")
    monkeypatch.setattr(api_evolution, "REPO_ROOT", tmp_path)
    return root


def test_api_case_loader_does_not_decode_unrequested_or_sealed_rows(miniature, monkeypatch):
    original_open, original_loads = Path.open, json.loads
    def opened(path, *args, **kwargs):
        assert "evaluation/sealed" not in str(path)
        return original_open(path, *args, **kwargs)
    def decoded(raw, *args, **kwargs):
        assert "invalid hidden sentinel" not in raw and "invalid public sentinel" not in raw
        return original_loads(raw, *args, **kwargs)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(json, "loads", decoded)
    cases = api_evolution._evaluation_cases(["manual-evolution"], "evolution")
    assert len(cases) == 1 and cases[0]["case_id"] == "manual-evolution"


def test_wrong_split_rejected_before_oracle_open(miniature, monkeypatch):
    write(miniature / "manifests/splits.json", json.dumps({"root_assignments": {"manual-evolution": "sealed"}}))
    original = Path.open
    def opened(path, *args, **kwargs):
        assert "oracle" not in str(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", opened)
    with pytest.raises(ValueError, match="split"):
        api_evolution._evaluation_cases(["manual-evolution"], "evolution")


def test_evolution_compute_grants_only_requested_root_split(monkeypatch):
    import tools.content.replay as replay
    import app.agent as agent
    captured = {}
    def environment(root, **kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr(replay, "EvaluatorReplay", environment)
    monkeypatch.setattr(api_evolution, "_evaluation_cases", lambda ids, split: [{"case_id": ids[0]}])
    monkeypatch.setattr(agent, "SkillLibrary", lambda root: object())
    monkeypatch.setattr(ReplayEvaluator, "evaluate", lambda self, *args, **kwargs: {"records": [], "test_only": True})
    result = api_evolution.evolution_compute({"payload": {"case_ids": ["manual-evolution"], "split": "evolution", "method": "ace", "max_rollouts": 1, "base_version": 0},
                                            "base": {"content": json.dumps(ContextStore().snapshot())}}, lambda: False)
    assert result["test_only"]
    assert captured == {"oracle_access": True, "allowed_splits": {"evolution"}, "case_ids": {"manual-evolution"}}
