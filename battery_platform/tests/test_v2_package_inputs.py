"""Package-specific input selection and future-label exclusion at runtime."""
import json

import numpy as np
import pytest

from app import v2_jobs
from app.services import sha


def test_runtime_query_excludes_future_survival_state_and_timestamps():
    row = {"source_id": "matr", "physical_cell_id": "matr:handwritten", "query_time": 100,
           "visible_cutoff": 99, "time_basis": "verified_physical_cycle", "physical_cycles_known": True,
           "survival_threshold_Ah": .88, "survival_threshold_operator": "strictly_less_than",
           "survival_censor_type": "right", "survival_label_observed_at": 1200,
           "survival_label_available_at": 1200, "target_observed_at": 100, "target_available_at": 100,
           "split": "dev"}
    query = v2_jobs.inference_query(row, {"schema_version": "battery_features_v2", "data_namespace": "experimental"})
    assert set(query).isdisjoint({"survival_censor_type", "survival_label_observed_at", "survival_label_available_at",
                                 "target_observed_at", "target_available_at", "split"})
    assert query["visible_cutoff"] == 99 and query["survival_threshold_Ah"] == .88
    assert row["survival_label_available_at"] == 1200


def package_fixture(tmp_path, monkeypatch, *, split="final", label_array=False):
    from model_lab.modeling.v2 import contracts
    monkeypatch.setattr(v2_jobs, "REPO_ROOT", tmp_path)
    derived = tmp_path / "model_lab/data/derived/v2/study"
    derived.mkdir(parents=True)
    (derived / "features.json").write_text(json.dumps({"data_namespace": "experimental", "rows": [{"split": split}]}))
    folder = tmp_path / "package"
    folder.mkdir()
    (folder / "manifest.json").write_text("{}")
    (folder / "run.json").write_text(json.dumps({"dataset_manifest": "/historical/checkout/model_lab/data/derived/v2/study/features.json",
                                              "feature_schema": "battery_features_v2", "data_namespace": "experimental"}))
    queries = [{"split": "dev", "source_id": "matr", "physical_cell_id": "matr:handwritten-dev",
                "query_time": 100, "visible_cutoff": 99, "feature_schema": "battery_features_v2"}]
    (folder / "reload_domain_queries.json").write_text(json.dumps(queries))
    arrays = {"features": np.zeros((1, 30)), "sequences": np.zeros((1, 2, 4, 6)),
              "sequence_mask": np.ones((1, 2, 4)), "domain": np.zeros(1, dtype=int)}
    if label_array:
        arrays["y_soh"] = np.ones(1)
    np.savez_compressed(folder / "reload_domain_samples.npz", **arrays)
    package = {"package_id": "package", "path": str(folder), "manifest_hash": sha(folder / "manifest.json")}
    def forbidden_numeric_load(*args, **kwargs):
        raise AssertionError("A non-development source corpus must never be numerically opened")
    monkeypatch.setattr(contracts, "load_dataset", forbidden_numeric_load)
    return package, folder


@pytest.mark.parametrize("split", ["final", "sealed", "protected"])
def test_final_corpus_is_excluded_before_numeric_loading(tmp_path, monkeypatch, split):
    package, folder = package_fixture(tmp_path, monkeypatch, split=split)
    file, manifest, arrays = v2_jobs.feature_bundle("package", package=package)
    assert file == folder / "manifest.json"
    assert manifest["binding_input_source"] == "label_free_package_development_examples"
    assert all(row["split"] == "dev" for row in manifest["rows"])
    assert set(arrays) == {"features", "sequences", "sequence_mask", "domain"}


def test_fallback_corpus_cannot_include_supervision_arrays(tmp_path, monkeypatch):
    package, _ = package_fixture(tmp_path, monkeypatch, label_array=True)
    with pytest.raises(ValueError, match="不能包含标签"):
        v2_jobs.feature_bundle("package", package=package)


def test_package_revision_change_rejects_old_binding_input(tmp_path, monkeypatch):
    package, folder = package_fixture(tmp_path, monkeypatch)
    (folder / "manifest.json").write_text('{"updated":true}')
    with pytest.raises(ValueError, match="版本已变化"):
        v2_jobs.feature_bundle("package", package=package)


def test_label_free_package_inputs_must_match_its_feature_version(tmp_path, monkeypatch):
    package, folder = package_fixture(tmp_path, monkeypatch)
    queries = json.loads((folder / "reload_domain_queries.json").read_text())
    queries[0]["feature_schema"] = "battery_features_v2_channel_validity_1"
    (folder / "reload_domain_queries.json").write_text(json.dumps(queries))
    with pytest.raises(ValueError, match="特征版本"):
        v2_jobs.feature_bundle("package", package=package)
