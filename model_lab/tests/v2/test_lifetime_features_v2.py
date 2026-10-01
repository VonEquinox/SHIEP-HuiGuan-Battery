import json

import numpy as np
import pandas as pd
import pytest

from model_lab.modeling.v2.contracts import load_dataset
from model_lab.modeling.v2.data import build_survival_target
from model_lab.modeling.v2.lifetime_features import build_lifetime_feature_bundle, remaining_survival_target


def _write_fixture(path, records=None, *, future_capacity=1.03, physical=True):
    path.mkdir()
    records = records or [("exact", "train", "policy-A"), ("right", "train", "policy-A"), ("interval", "train", "policy-A")]
    identities, cycles, segments, targets = [], [], [], []
    assignments = {}
    for name, split, policy in records:
        cell = f"matr:barcode-{name}"
        assignments[cell] = split
        identities.append({"source_id": "matr", "physical_cell_id": cell, "chemistry": "LFP", "namespace": "experimental",
                           "source_protocol_id": policy, "protocol_id": policy, "nominal_capacity_Ah": 1.1,
                           "identity_basis": "original_corrected_mat_barcode", "identity_verified": True})
        kind = name.split("-")[0]
        if kind == "exact":
            measurements = [(10, 1.1), (49, 1.04), (50, future_capacity), (79, .9), (80, .87)]
        elif kind == "interval":
            measurements = [(10, 1.1), (49, 1.04), (50, future_capacity), (80, .92), (100, .87)]
        else:
            measurements = [(10, 1.1), (49, 1.04), (50, future_capacity), (120, .94)]
        for cycle, capacity in measurements:
            cycles.append({"physical_cell_id": cell, "source_id": "matr", "cycle_index": cycle,
                           "physical_cycles_known": physical, "capacity_Ah": capacity, "protocol_id": policy,
                           "observed_at": cycle, "available_at": cycle, "raw_ref": f"fixture:{name}:cycle:{cycle}",
                           "cycle_life": 987654, "final_capacity_Ah": .123})
        for cycle in (10, 49, 50):
            segments.append({"physical_cell_id": cell, "source_id": "matr", "cycle_index": cycle,
                             "protocol_id": policy, "observed_at": cycle, "available_at": cycle,
                             "voltage_V": [3., 4.], "current_A": [1., 1.], "temperature_C": [25., 25.],
                             "time_s": [0., 10.], "raw_ref": f"fixture:{name}:curve:{cycle}", "death_cycle": 987654})
        target = build_survival_target([c for c, _ in measurements], [q for _, q in measurements], threshold_Ah=.88,
                                       target_definition_id="fixture-matr-nominal-0.88Ah-v2", inclusive=False)
        targets.append({"physical_cell_id": cell, "source_id": "matr", **target})
    pd.DataFrame(identities).to_parquet(path / "identity_map.parquet")
    pd.DataFrame(cycles).to_parquet(path / "cycles.parquet")
    pd.DataFrame(segments).to_parquet(path / "segments.parquet")
    pd.DataFrame(targets).to_parquet(path / "targets.parquet")
    (path / "split_manifest.json").write_text(json.dumps({"assignments": assignments}))


def test_exact_right_interval_remaining_physical_labels_and_frozen_reference(tmp_path):
    source, out = tmp_path / "source", tmp_path / "views"
    _write_fixture(source)
    built = build_lifetime_feature_bundle(source, out, query_prefixes=(50,), history=2, points=16)
    manifest, arrays = load_dataset(out / "features.json")
    assert arrays["survival_kind"].tolist() == [1., 0., 2.]
    assert arrays["survival_lower"].tolist() == [30., 70., 30.]
    assert arrays["survival_upper"].tolist() == [30., 0., 50.]
    assert np.allclose(arrays["y_soh"], 1.03 / 1.1)
    assert built["censor_counts"] == {"right": 1, "exact": 1, "interval": 1}
    assert np.isnan(arrays["y_efficiency"]).all() and (arrays["y_fault"] == -1).all()
    assert all(row["reference_cutoff"] == 10 and row["feature_max_time"] == 49 for row in manifest["rows"])
    assert "operator=strictly_less_than" in manifest["target_definitions"]["rul"]
    assert not any("life" in name or "death" in name or "final" in name for name in manifest["feature_names"])


def test_alive_at_query_and_strict_threshold_boundaries():
    exact = build_survival_target([49, 50], [.9, .87], threshold_Ah=.88, target_definition_id="strict", inclusive=False)
    assert remaining_survival_target(exact, 50)[3] == "event_already_occurred_at_query"
    interval = build_survival_target([40, 80], [.9, .87], threshold_Ah=.88, target_definition_id="strict", inclusive=False)
    assert remaining_survival_target(interval, 50)[3] == "event_interval_straddles_query_alive_status_unknown"
    assert remaining_survival_target(interval, 40)[:3] == (2, 0., 40.)
    right = build_survival_target([10, 40], [1.1, .9], threshold_Ah=.88, target_definition_id="strict", inclusive=False)
    assert remaining_survival_target(right, 50)[3] == "right_censor_before_query_alive_status_unknown"
    strict = build_survival_target([79, 80, 81], [.9, .88, .87], threshold_Ah=.88, target_definition_id="strict", inclusive=False)
    inclusive = build_survival_target([79, 80, 81], [.9, .88, .87], threshold_Ah=.88, target_definition_id="inclusive", inclusive=True)
    assert strict["upper_event_bound"] == 81 and inclusive["upper_event_bound"] == 80
    assert remaining_survival_target({**strict, "threshold_operator": None}, 50)[3] == "missing_or_invalid_threshold_contract"


def test_ordinal_cycles_fail_closed_without_output(tmp_path):
    source, out = tmp_path / "ordinal", tmp_path / "views"
    _write_fixture(source, physical=False)
    with pytest.raises(ValueError, match="no qualified alive-at-query"):
        build_lifetime_feature_bundle(source, out, query_prefixes=(50,), history=2, points=16)
    assert not out.exists()


def test_future_measurements_and_hidden_labels_do_not_change_prefix_features(tmp_path):
    first, other = tmp_path / "first", tmp_path / "other"
    _write_fixture(first, [("exact", "train", "policy-A")])
    _write_fixture(other, [("exact", "train", "policy-A")], future_capacity=.99)
    segments = pd.read_parquet(other / "segments.parquet")
    segments.loc[segments.cycle_index.eq(50), "voltage_V"] = pd.Series([[99., 100.]], index=segments.index[segments.cycle_index.eq(50)])
    segments.to_parquet(other / "segments.parquet", index=False)
    build_lifetime_feature_bundle(first, tmp_path / "a", query_prefixes=(50,), history=2, points=16)
    build_lifetime_feature_bundle(other, tmp_path / "b", query_prefixes=(50,), history=2, points=16)
    _, a = load_dataset(tmp_path / "a" / "features.json")
    _, b = load_dataset(tmp_path / "b" / "features.json")
    assert np.array_equal(a["features"], b["features"])
    assert np.array_equal(a["sequences"], b["sequences"])
    assert a["y_soh"][0] != b["y_soh"][0]


def test_sealed_final_excluded_before_numeric_read_and_exact_policies_preserved(tmp_path, monkeypatch):
    source, out = tmp_path / "source", tmp_path / "views"
    _write_fixture(source, [("exact-A", "train", "policy-A"), ("right-B", "dev", "policy-B"),
                            ("exact-final", "final", "policy-C"), ("right-sealed", "sealed", "policy-D"),
                            ("right-priorfinal", "train", "policy-E")])
    prior_path = tmp_path / "prior_features.json"
    prior_path.write_text(json.dumps({"rows": [{"source_id": "matr", "physical_cell_id": "matr:BARCODE-RIGHT-PRIORFINAL", "split": "final"}],
                                      "arrays_file": "must_not_open_final_arrays.npz"}))
    original = pd.read_parquet
    observed = []

    def read(path, *args, **kwargs):
        if str(path).endswith(("cycles.parquet", "segments.parquet", "targets.parquet")):
            observed.append(kwargs)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", read)
    manifest = build_lifetime_feature_bundle(source, out, query_prefixes=(50,), history=2, points=16, exclude_identity_manifest=prior_path)
    admitted = {"matr:barcode-exact-A", "matr:barcode-right-B"}
    assert len(observed) == 3
    assert all(set(call["filters"][0][2]) == admitted for call in observed)
    assert all("cycle_life" not in call["columns"] and "death_cycle" not in call["columns"] for call in observed)
    assert set(manifest["domains"]) == {"matr::LFP::policy-A", "matr::LFP::policy-B"}
    assert {row["split"] for row in manifest["rows"]} == {"train", "dev"}
    assert manifest["exclusion_counts"]["non_development_split_excluded_before_numeric_read"] == 2
    assert manifest["exclusion_counts"]["previously_consumed_final_identity"] == 1
    assert manifest["prior_final_identity_exclusions"]["prior_final_identity_count"] == 1
    assert manifest["prior_final_identity_exclusions"]["numerical_arrays_opened"] is False
    with pytest.raises(FileExistsError, match="new directory"):
        build_lifetime_feature_bundle(source, out, query_prefixes=(50,), history=2, points=16)
