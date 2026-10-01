"""Synthetic sentinels prove loaders never open/decode ungranted splits.

No checked-in sealed case, sealed label or archived experiment is read here.
"""
import json
from pathlib import Path

import pytest

from tools.content.replay import EvaluatorReplay


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def case(cid, split):
    return {"case_id": cid, "split_tags": {"split": split}, "initial_visible": {"cutoff": "2026-09-01T00:00:00Z", "observations": [{"observation_id": "initial-" + cid}]}, "test_catalog": [{"test_id": "T_TIME_ALIGN", "needs_new_authorization": False}]}


def label(cid):
    return {"case_id": cid, "branches": [{"from": "start", "test_id": "T_TIME_ALIGN", "result": "supports_A", "reveal": ["branch-" + cid], "next_state": "review"}], "hidden_truth": {"root_cause": "A", "candidate_causes": ["A", "B"]}, "feedback_events": []}


@pytest.fixture
def miniature(tmp_path):
    write(tmp_path / "cases/cold_start.jsonl", [case("cold", "cold_start")])
    write(tmp_path / "streams/evolution_round_01.jsonl", [case("evo-one", "evolution"), case("evo-two", "evolution")])
    write(tmp_path / "evaluation/dev/cases.jsonl", [case("dev-one", "dev")])
    # Out-of-scope sentinels are deliberately invalid JSON: decoding them fails.
    (tmp_path / "evaluation/sealed").mkdir(parents=True)
    (tmp_path / "evaluation/sealed/cases.jsonl").write_text('SEALED INPUT MUST NEVER OPEN\n')
    write(tmp_path / "oracle/labels.jsonl", [label(cid) for cid in ("cold", "evo-one", "evo-two", "dev-one")])
    with (tmp_path / "oracle/labels.jsonl").open("a") as handle:
        handle.write('{"case_id":"sealed-sentinel", invalid out-of-scope label}\n')
    write(tmp_path / "oracle/observations.jsonl", [{"observation_id": "branch-" + cid, "root_scenario_id": cid, "timestamp": "2026-09-01T01:00:00Z", "value": 1.0} for cid in ("cold", "evo-one", "evo-two", "dev-one")])
    with (tmp_path / "oracle/observations.jsonl").open("a") as handle:
        handle.write('{"observation_id":"sealed-branch", invalid out-of-scope observation}\n')
    return tmp_path


def install_spies(monkeypatch):
    opened, decoded = [], []
    original_open, original_loads = Path.open, json.loads

    def open_spy(path, *args, **kwargs):
        if "r" in str(args[0] if args else kwargs.get("mode", "r")):
            opened.append(str(path))
            assert "evaluation/sealed" not in str(path), "sealed input was opened"
        return original_open(path, *args, **kwargs)

    def decode_spy(raw, *args, **kwargs):
        assert "sealed-sentinel" not in raw and "sealed-branch" not in raw, "out-of-scope oracle row reached JSON decoder"
        parsed = original_loads(raw, *args, **kwargs)
        if isinstance(parsed, dict):
            decoded.append(parsed.get("case_id", parsed.get("observation_id")))
        return parsed

    monkeypatch.setattr(Path, "open", open_spy)
    monkeypatch.setattr(json, "loads", decode_spy)
    return opened, decoded


def test_evolution_does_not_open_other_split_files_or_decode_unrequested_roots(miniature, monkeypatch):
    opened, decoded = install_spies(monkeypatch)
    replay = EvaluatorReplay(miniature, oracle_access=True, allowed_splits={"evolution"}, case_ids={"evo-one"})
    assert set(replay._cases) == set(replay._labels) == {"evo-one"}
    assert set(replay._observations) == {"branch-evo-one"}
    assert not any("cold_start" in path or "evaluation/dev" in path for path in opened)
    assert set(decoded) == {"evo-one", "branch-evo-one"}
    session = replay.begin("evo-one")
    replay.authorize(session, "T_TIME_ALIGN", approved_by="synthetic_evaluator")
    assert replay.reveal(session, "T_TIME_ALIGN")["observations"][0]["observation_id"] == "branch-evo-one"


def test_default_oracle_access_grants_only_cold_start(miniature, monkeypatch):
    opened, decoded = install_spies(monkeypatch)
    replay = EvaluatorReplay(miniature, oracle_access=True)
    assert replay.allowed_splits == {"cold_start"}
    assert set(replay._cases) == {"cold"}
    assert not any("streams" in path or "evaluation/" in path for path in opened)
    assert set(decoded) == {"cold", "branch-cold"}


def test_dev_must_be_explicit_and_still_does_not_read_sealed(miniature, monkeypatch):
    opened, decoded = install_spies(monkeypatch)
    replay = EvaluatorReplay(miniature, oracle_access=True, allowed_splits={"evolution", "dev"}, case_ids={"evo-two", "dev-one"})
    assert set(replay._cases) == {"evo-two", "dev-one"}
    assert not any("cold_start" in path for path in opened)
    assert set(decoded) == {"evo-two", "dev-one", "branch-evo-two", "branch-dev-one"}


def test_cross_split_requested_root_rejected_before_any_oracle_read(miniature, monkeypatch):
    opened, decoded = install_spies(monkeypatch)
    with pytest.raises(PermissionError):
        EvaluatorReplay(miniature, oracle_access=True, allowed_splits={"evolution"}, case_ids={"dev-one"})
    assert not decoded
    assert not any("oracle" in path for path in opened)


def test_empty_requested_root_set_reads_nothing(miniature, monkeypatch):
    opened, decoded = install_spies(monkeypatch)
    replay = EvaluatorReplay(miniature, oracle_access=True, allowed_splits={"evolution"}, case_ids=set())
    assert replay._cases == replay._labels == replay._observations == {}
    assert opened == decoded == []


@pytest.mark.parametrize("scope", [{"all"}, set(), "evolution"])
def test_invalid_scope_rejected_before_files_open(miniature, monkeypatch, scope):
    opened, decoded = install_spies(monkeypatch)
    with pytest.raises(ValueError):
        EvaluatorReplay(miniature, oracle_access=True, allowed_splits=scope)
    assert opened == decoded == []
