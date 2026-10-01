"""Meaningful corpus, authorization and leakage regressions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools.content.common import read_jsonl
from tools.content.generate import build, make_root, reference_voi
from tools.content.replay import EvaluatorReplay, PublicContentStore, export_public
from tools.content.skill_catalog import generate_skills
from tools.content.validate import forbidden_keys, validate_content

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def content_root(tmp_path_factory):
    # The checked-in, frozen pack is independently validated, rather than tests
    # silently regenerating and overwriting a changed expected manifest.
    root = REPOSITORY / "content_v1"
    if not root.exists():
        root = tmp_path_factory.mktemp("content")
        build(root)
    return root


def test_full_frozen_pack_schema_hashes_and_root_split(content_root):
    result = validate_content(content_root)
    assert result["status"] == "passed", result["errors"][:10]
    assert result["hashes_checked"] is True
    assert result["checks"]["S03"]["roots"] == 2400
    assert result["checks"]["S03"]["cross_split_clusters"] == 0
    assert result["checks"]["S03"]["cross_split_templates"] == 0


def test_public_export_cannot_publish_oracle_streams_or_carbon(content_root, tmp_path):
    result = export_public(content_root, tmp_path)
    assert result == {"skills": 16, "cold_roots": 960, "evaluator_files": 0}
    assert not (tmp_path / "oracle").exists()
    assert not (tmp_path / "evaluation").exists()
    assert not (tmp_path / "fixtures").exists()
    assert not (tmp_path / "streams").exists()
    public = PublicContentStore(tmp_path)
    assert len(public.skill_metadata()) == 16
    assert all(not forbidden_keys(case) for case in public.cold_cases())
    with pytest.raises(PermissionError):
        public.load_reference("sensor-anomaly", "references/../../../oracle/labels.jsonl")
    with pytest.raises(PermissionError):
        public.load_skill("../../oracle")
    with pytest.raises(ValueError):
        export_public(content_root, tmp_path)


def test_unapproved_skill_and_tool_permission_expansion_not_loaded(content_root, tmp_path):
    export_public(content_root, tmp_path)
    manifest = tmp_path / "skills/sensor-anomaly/manifest.json"
    data = json.loads(manifest.read_text()); data["license_status"] = "pending_review"
    manifest.write_text(json.dumps(data))
    store = PublicContentStore(tmp_path)
    with pytest.raises(PermissionError):
        store.load_skill("sensor-anomaly")
    data["license_status"] = "approved_synthetic"; data["allowed_tools"].append("carbon_optimize")
    manifest.write_text(json.dumps(data))
    with pytest.raises(PermissionError):
        store.load_skill("sensor-anomaly")


def test_evaluator_is_opt_in_and_tests_require_authorization(content_root):
    with pytest.raises(PermissionError):
        EvaluatorReplay(content_root)
    replay = EvaluatorReplay(content_root, oracle_access=True)
    case_id = read_jsonl(content_root / "cases/cold_start.jsonl")[0]["case_id"]
    session = replay.begin(case_id)
    initial_ids = set(session.reached_ids)
    with pytest.raises(PermissionError):
        replay.reveal(session, "T_TIME_ALIGN")
    with pytest.raises(PermissionError):
        replay.reveal(session, "T_CHANNEL_CHECK", authorized=True)
    with pytest.raises(PermissionError):
        replay.reveal(session, "T_RESTRICTED_CHECK", authorized=True, result="additional_authorization")
    with pytest.raises(PermissionError):
        replay.authorize(session, "T_TIME_ALIGN", approved_by="technician")
    replay.authorize(session, "T_TIME_ALIGN", approved_by="synthetic_evaluator")
    first = replay.reveal(session, "T_TIME_ALIGN")
    assert len(session.reached_ids - initial_ids) == 1
    assert first["new_evidence"] is True
    assert not forbidden_keys(session.visible)
    duplicate = replay.reveal(session, "T_TIME_ALIGN")
    assert duplicate["duplicate"] is True and duplicate["new_evidence"] is False
    assert len(session.reached_ids - initial_ids) == 1
    replay.authorize(session, "T_CHANNEL_CHECK", approved_by="synthetic_evaluator")
    second = replay.reveal(session, "T_CHANNEL_CHECK")
    assert second["intervention"] is False
    assert len(session.reached_ids - initial_ids) == 2


def test_feedback_is_gated_by_actual_revealed_observation(content_root):
    replay = EvaluatorReplay(content_root, oracle_access=True)
    root = read_jsonl(content_root / "cases/cold_start.jsonl")[0]["case_id"]
    session = replay.begin(root)
    assert replay.visible_feedback(session) == []
    replay.reveal(session, "T_TIME_ALIGN", authorized=True, result="supports_A")
    feedback = replay.visible_feedback(session)
    assert len(feedback) == 1
    span = feedback[0]["extraction_targets"][0]["span"]
    assert feedback[0]["free_text"][span["start"]:span["end"]] == span["text"]
    assert set(feedback[0]["evidence_ids"]) <= session.reached_ids


def test_same_initial_signals_do_not_imply_same_root_cause():
    left, label_left, _, _ = make_root(1, 0, 0, {})
    right, label_right, _, _ = make_root(1, 0, 1, {})
    assert [(o["metric"], o["value"], o["unit"]) for o in left["initial_visible"]["observations"]] == [(o["metric"], o["value"], o["unit"]) for o in right["initial_visible"]["observations"]]
    assert label_left["hidden_truth"]["root_cause"] != label_right["hidden_truth"]["root_cause"]
    assert not forbidden_keys(left) and not forbidden_keys(right)


def test_generated_examples_reject_sealed_and_future_observations(tmp_path):
    case, _, _, _ = make_root(0, 17, 0, {})
    with pytest.raises(ValueError):
        generate_skills(tmp_path, [case])
    case["split_tags"]["split"] = "cold_start"
    case["initial_visible"]["observations"][0]["available_after"] = "T_TIME_ALIGN"
    with pytest.raises(ValueError):
        generate_skills(tmp_path, [case])


def test_voi_informative_test_beats_dominated_repeat():
    case, label, _, _ = make_root(0, 0, 0, {})
    model = case["observation_model"]
    assert reference_voi(model, "T_TIME_ALIGN") == pytest.approx(0.9)
    assert reference_voi(model, "T_REPEAT_SOURCE") == pytest.approx(-1.0)
    assert label["active_test_oracle"]["reference_voi"]["T_TIME_ALIGN"] > 0


def test_report_scoring_rejects_unreached_reference_and_unauthorized_actions(content_root):
    replay = EvaluatorReplay(content_root, oracle_access=True)
    session = replay.begin(read_jsonl(content_root / "cases/cold_start.jsonl")[0]["case_id"])
    result = replay.score(session, {"evidence_refs": ["future-measurement"], "automatic_dispatch": True, "called_tools": ["carbon_optimize"]})
    assert result["passed"] is False
    assert not result["checks"]["evidence_visible"]
    assert not result["checks"]["no_automatic_dispatch"]
    assert not result["checks"]["no_carbon_tool"]
