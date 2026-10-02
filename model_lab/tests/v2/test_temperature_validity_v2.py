"""Temperature observation state survives resampling and model preprocessing."""
import json

import numpy as np
import pandas as pd
import pytest

from model_lab.modeling.v2.contracts import CHANNEL_VALIDITY_SCHEMA, SCHEMA, load_dataset, validate_training_manifest
from model_lab.modeling.v2.features import (
    FEATURE_NAMES, SEQUENCE_CHANNELS, build_feature_bundle, fit_preprocessor,
    preprocess, segment_view, statistical_view,
)
from model_lab.modeling.v2.prediction import SafePackage


def curve(temperature=None):
    row = {"time_s": [0., 1., 2., 3., 4.], "voltage_V": [3., 3.2, 3.4, 3.6, 3.8],
           "current_A": [1.] * 5}
    if temperature is not None:
        row["temperature_C"] = temperature
    return row


def statistics(sequence, mask):
    cycles = pd.DataFrame({"capacity_Ah": [2.], "cycle_index": [1.], "diagnostic": [True]})
    return statistical_view(sequence, mask, cycles, 2., 2.)


@pytest.mark.parametrize("temperature,expected_valid", [
    (None, [0, 0, 0, 0, 0]),
    ([20., 22.], [1, 1, 0, 0, 0]),
    ([20., 22., np.nan, 26., 28.], [1, 1, 0, 1, 1]),
    ([np.nan] * 5, [0, 0, 0, 0, 0]),
    ([0.] * 5, [1, 1, 1, 1, 1]),
])
def test_temperature_absence_short_nan_and_real_zero(temperature, expected_valid):
    sequence, mask = segment_view(curve(temperature), points=5, nominal=2.)
    assert sequence.shape == (5, len(SEQUENCE_CHANNELS))
    assert np.isfinite(sequence).all() and np.array_equal(mask, np.ones(5))
    assert sequence[:, 5].tolist() == expected_valid
    assert (sequence[sequence[:, 5] == 0, 2] == 0).all()
    stat = statistics(sequence, mask)
    assert stat[len(FEATURE_NAMES) + 6:len(FEATURE_NAMES) + 8].tolist() == [int(not all(expected_valid))] * 2
    observed = sequence[sequence[:, 5] > 0, 2]
    assert stat[6] == pytest.approx(observed.mean() if len(observed) else 0.)
    assert stat[7] == pytest.approx(observed.std() if len(observed) else 0.)


def test_missing_temperature_and_measured_zero_are_distinct_inputs():
    absent, mask = segment_view(curve(), points=9)
    zero, zero_mask = segment_view(curve([0.] * 5), points=9)
    assert np.array_equal(absent[:, :5], zero[:, :5])
    assert np.array_equal(mask, zero_mask)
    assert not np.array_equal(absent, zero)
    assert not np.array_equal(statistics(absent, mask), statistics(zero, zero_mask))


def test_temperature_gaps_are_not_interpolated_through_missing_samples():
    sequence, _ = segment_view(curve([20., 22., np.nan, 26., 28.]), points=9)
    assert sequence[:, 5].tolist() == [1, 1, 1, 0, 0, 0, 1, 1, 1]
    assert sequence[[3, 4, 5], 2].tolist() == [0., 0., 0.]


def test_normalization_uses_measured_temperature_and_neutralizes_missing_latest_statistics():
    observed, pointmask = segment_view(curve([20., 22., 24., 26., 28.]), points=5)
    absent, _ = segment_view(curve(), points=5)
    # Last statistics are missing although an older segment has temperature.
    sequences = np.asarray([[observed, observed], [observed, absent], [observed * 999, observed * 999]])
    masks = np.ones(sequences.shape[:-1], np.float32)
    features = np.asarray([statistics(observed, pointmask), statistics(absent, pointmask), statistics(observed, pointmask)])
    transform = fit_preprocessor(features, sequences, masks, [0, 1], domain=np.zeros(3), temperature_stat_domains=[0])
    assert transform["sequence_mean"][2] == pytest.approx(24.)
    assert transform["sequence_scale"][2] == pytest.approx(np.std([20., 22., 24., 26., 28.]))
    assert transform["sequence_mean"][5] == 0 and transform["sequence_scale"][5] == 1
    result = preprocess({"features": features[:2], "sequences": sequences[:2], "sequence_mask": masks[:2], "domain": np.zeros(2)}, transform)
    assert (result["sequences"][1, -1, :, 2] == 0).all()
    assert result["sequences"][0, -1, :, 5].tolist() == [1.] * 5
    assert result["sequences"][1, -1, :, 5].tolist() == [0.] * 5
    assert result["features"][1, 6:8].tolist() == [0., 0.]


def test_partial_temperature_statistics_remain_measured_and_native_sources_are_not_temperature():
    partial, mask = segment_view(curve([20., 22., np.nan, 26., 28.]), points=5)
    absent, _ = segment_view(curve(), points=5)
    partial_stats = statistics(partial, mask)
    native = partial_stats.copy()
    native[6:8] = [3.5, 3.2]  # DYAD uses voltage columns here, not temperatures.
    native[21:23] = 0
    sequences = np.asarray([[partial], [absent]])
    masks = np.ones(sequences.shape[:-1])
    features = np.asarray([partial_stats, native])
    domains = np.asarray([0, 1])
    transform = fit_preprocessor(features, sequences, masks, [0, 1], domain=domains, temperature_stat_domains=[0])
    assert transform["feature_mean"][6] == pytest.approx((24. + 3.5) / 2)
    result = preprocess({"features": features, "sequences": sequences, "sequence_mask": masks, "domain": domains}, transform)
    assert result["features"][0, 6] != 0  # valid partial summary was retained.
    assert result["features"][1, 6] != 0  # native source was not neutralized.


def write_fixture(path):
    path.mkdir()
    pd.DataFrame([{"source_id": "fixture", "physical_cell_id": "a", "chemistry": "NCM", "protocol_id": "p", "nominal_capacity_Ah": 2.}]).to_parquet(path / "identity_map.parquet")
    pd.DataFrame([{"physical_cell_id": "a", "cycle_index": k, "capacity_Ah": q, "diagnostic": True} for k, q in [(1, 2.), (3, 1.8)]]).to_parquet(path / "cycles.parquet")
    pd.DataFrame([{**curve(), "physical_cell_id": "a", "cycle_index": 1, "raw_ref": "fixture:1"}]).to_parquet(path / "segments.parquet")
    (path / "split_manifest.json").write_text(json.dumps({"assignments": {"a": "train"}}))


def test_new_feature_version_is_immutable_and_loads_six_channel_contract(tmp_path):
    source, out = tmp_path / "source", tmp_path / "features"
    write_fixture(source)
    manifest = build_feature_bundle(source, out, landmarks_per_cell=1, history=1, points=5)
    assert manifest["schema_version"] == CHANNEL_VALIDITY_SCHEMA
    assert manifest["data_version"] == "v2-prefix-channel-validity-2"
    assert manifest["sequence_channels"] == SEQUENCE_CHANNELS
    _, arrays = load_dataset(out / "features.json")
    assert arrays["sequences"].shape == (1, 1, 5, 6)
    assert arrays["features"][0, 21:23].tolist() == [1., 1.]
    before = (out / "features.npz").read_bytes()
    with pytest.raises(FileExistsError, match="immutable"):
        build_feature_bundle(source, out)
    assert (out / "features.npz").read_bytes() == before


def test_model_rejects_new_schema_before_using_historical_transform_or_model():
    package = SafePackage.__new__(SafePackage)
    package.model_version = "historical-model"
    package.record = {"feature_schema": SCHEMA, "support_domains": [{"source_id": "fixture", "chemistry": "NCM", "protocol_id": "p"}]}
    query = {"feature_schema": CHANNEL_VALIDITY_SCHEMA, "source_id": "fixture", "physical_cell_id": "a", "chemistry": "NCM", "protocol_id": "p", "query_time": 3, "visible_cutoff": 2, "data_namespace": "experimental"}
    profile = package.predict(query, {})
    assert profile["support"]["status"] == "unsupported"
    assert profile["support"]["reasons"] == ["feature_schema_mismatch"]


def test_new_model_rejects_old_query_or_misdeclared_five_channel_input():
    package = SafePackage.__new__(SafePackage)
    package.model_version = "new-model"
    package.record = {"feature_schema": CHANNEL_VALIDITY_SCHEMA,
                      "support_domains": [{"source_id": "fixture", "chemistry": "NCM", "protocol_id": "p"}],
                      "preprocessor": {"feature_mean": [0.] * 30, "sequence_mean": [0.] * 6}}
    query = {"feature_schema": SCHEMA, "source_id": "fixture", "physical_cell_id": "a", "chemistry": "NCM", "protocol_id": "p", "query_time": 3, "visible_cutoff": 2, "data_namespace": "experimental"}
    assert package.predict(query, {})["support"]["reasons"] == ["feature_schema_mismatch"]
    arrays = {"features": np.zeros((1, 30)), "sequences": np.zeros((1, 1, 5, 5)), "sequence_mask": np.ones((1, 1, 5))}
    assert package.predict({**query, "feature_schema": CHANNEL_VALIDITY_SCHEMA}, arrays)["support"]["reasons"] == ["invalid_sequence"]


@pytest.mark.parametrize("mutation", [
    lambda arrays: arrays.__setitem__("sequences", arrays["sequences"][..., :5]),
    lambda arrays: arrays["sequences"].__setitem__((0, 0, 0, 5), .5),
    lambda arrays: arrays["sequences"].__setitem__((0, 0, 0, 2), 27.),
])
def test_new_schema_cannot_hide_invalid_channel_state(tmp_path, mutation):
    from model_lab.modeling.v2.contracts import sha256_file
    source, out = tmp_path / "source", tmp_path / "features"
    write_fixture(source)
    manifest = build_feature_bundle(source, out, history=1, points=5)
    _, arrays = load_dataset(out / "features.json")
    mutation(arrays)
    np.savez_compressed(out / "features.npz", **arrays)
    manifest["arrays_sha256"] = sha256_file(out / "features.npz")
    (out / "features.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="channel|temperature"):
        load_dataset(out / "features.json")


@pytest.mark.parametrize("mutation", [
    lambda manifest: manifest.pop("temperature_stat_domains"),
    lambda manifest: manifest.update(temperature_stat_domains=[]),
    lambda manifest: manifest.update(temperature_stat_domains=None),
    lambda manifest: manifest.update(temperature_stat_domains="0"),
    lambda manifest: manifest.update(temperature_stat_domains=["0"]),
    lambda manifest: manifest.update(temperature_stat_domains=[True]),
    lambda manifest: manifest.update(temperature_stat_domains=[0.]),
    lambda manifest: manifest.update(temperature_stat_domains=[0, 0]),
    lambda manifest: manifest.update(temperature_stat_domains=[1]),
    lambda manifest: manifest.update(domains={"fixture::NCM::p": 0, "other::NCM::q": 1}),
])
def test_new_schema_requires_complete_temperature_domain_metadata_before_numeric_read(tmp_path, monkeypatch, mutation):
    source, out = tmp_path / "source", tmp_path / "features"
    write_fixture(source)
    manifest = build_feature_bundle(source, out, history=1, points=5)
    mutation(manifest)
    (out / "features.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: pytest.fail("invalid metadata must fail before numeric loading"))
    with pytest.raises(ValueError, match="temperature"):
        load_dataset(out / "features.json")


def test_native_dyad_domain_is_excluded_without_changing_legacy_manifest_compatibility():
    row = {"source_id": "dyad", "physical_cell_id": "vehicle", "split": "train", "query_time": 1, "visible_cutoff": 1}
    manifest = {"schema_version": CHANNEL_VALIDITY_SCHEMA, "data_namespace": "experimental", "rows": [row],
                "domains": {"dyad::unknown::vehicle_charging": 0}, "temperature_stat_domains": []}
    validate_training_manifest(manifest)
    with pytest.raises(ValueError, match="exclude native DYAD"):
        validate_training_manifest({**manifest, "temperature_stat_domains": [0]})
    # Historical schema never required this new metadata and remains loadable.
    validate_training_manifest({"schema_version": SCHEMA, "data_namespace": "experimental", "rows": [row]})


@pytest.mark.parametrize("temperature_domains", [None, [], [True], [0, 0], [1]])
def test_new_model_package_cannot_omit_or_corrupt_temperature_stat_domain_metadata(tmp_path, temperature_domains):
    (tmp_path / "manifest.json").write_text(json.dumps({"format": "battery_model_safe_v2", "files": {}}))
    preprocessor = {} if temperature_domains is None else {"temperature_stat_domains": temperature_domains}
    (tmp_path / "run.json").write_text(json.dumps({"feature_schema": CHANNEL_VALIDITY_SCHEMA,
                                                  "domain_index": {"fixture::NCM::p": 0}, "preprocessor": preprocessor}))
    with pytest.raises(ValueError, match="temperature"):
        SafePackage(tmp_path)
