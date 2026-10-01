"""CLI prerequisite guards only; no original measurement or training replay."""
import json

import pytest

from model_lab.scripts.v2.prepare_official_subsets import _ch_paths, _new_output, build_parser, prepare


def test_dry_list_does_not_open_inputs_or_create_output(tmp_path):
    out = tmp_path / "data/derived/v2/new"
    args = build_parser().parse_args(["--kind", "dyad", "--archive", str(tmp_path / "absent.tar.gz"), "--out", str(out), "--dry-list"])
    result = prepare(args)
    assert result["status"] == "dry_list_no_measurements_opened"
    assert not out.exists()


def test_existing_or_non_v2_output_rejected_before_input_parse(tmp_path):
    out = tmp_path / "data/derived/v2/locked"
    out.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        _new_output(str(out), "out")
    with pytest.raises(ValueError):
        _new_output(str(tmp_path / "v1"), "out")


def test_missing_original_is_explicit_without_output(tmp_path):
    out = tmp_path / "data/derived/v2/new"
    args = build_parser().parse_args(["--kind", "matr-csv", "--out", str(out), "--source-registry", str(tmp_path / "missing.yaml")])
    with pytest.raises(FileNotFoundError, match="required original/metadata file unavailable"):
        prepare(args)
    assert not out.exists()


def test_ch_selection_path_traversal_is_rejected(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"selected": [{"path": "../outside.csv"}]}))
    with pytest.raises(ValueError, match="unsafe"):
        _ch_paths(tmp_path, inventory)


def test_corrected_matr_requires_three_original_batches_before_output(tmp_path):
    registry = tmp_path / "registry.yaml"
    registry.write_text("sources:\n  - source_id: matr\n    license_status: declared_official_platform_license\n    landing_url: https://data.matr.io\n    raw_receipts: []\n")
    out = tmp_path / "data/derived/v2/new"
    args = build_parser().parse_args(["--kind", "matr-corrected", "--out", str(out), "--source-registry", str(registry)])
    with pytest.raises(ValueError, match="all three"):
        prepare(args)
    assert not out.exists()
