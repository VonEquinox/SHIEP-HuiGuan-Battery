import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

from model_lab.data.nasa_pcoe import (
    archive_inventory, first_eligible_reference, integrated_discharge,
    nasa_charge_view, pair_operations,
)
from model_lab.data.physical_curve_features import curve_features
from model_lab.data.xjtu_raw import build_cc_window
from model_lab.modeling.frozen_et import predict_soh, validate_inputs
from model_lab.scripts.freeze_et_champion import selected_leaf


def operation(kind, hour, data):
    return {"type": kind, "time": np.array([2020, 1, 2, hour, 0, 0.]), "data": data}


def charge_data(temperature=None):
    n = 101
    return {"Time": np.linspace(0, 3600, n),
            "Voltage_measured": np.linspace(3.6, 4.2, n),
            "Current_measured": np.ones(n),
            "Temperature_measured": (25 + np.linspace(0, 1, n)
                                     if temperature is None else temperature)}


def discharge_data(voltage=None):
    return {"Time": np.array([0., 1800., 3600.]),
            "Voltage_measured": np.array([4., 3., 2.]) if voltage is None else voltage,
            "Current_measured": np.array([-2., -2., -2.]), "Capacity": 1.3}


def test_seconds_to_minutes_and_exact_feature_order():
    data = charge_data()
    x, q, meta = nasa_charge_view(operation("charge", 1, data))
    assert meta["reason"] == "ok"
    assert np.isclose(q, 40/60, atol=.01)
    assert np.isclose(np.exp(x[65]), 40., atol=.5)
    assert np.isclose(x[69], 25+1/6, atol=.02)
    assert np.isclose(x[70], 1.)
    mapped = {"relative_time_min": data["Time"]/60,
              "voltage_V": data["Voltage_measured"],
              "current_A": data["Current_measured"],
              "temperature_C": data["Temperature_measured"]}
    window = build_cc_window(mapped)
    channels = np.stack((window.elapsed_min, window.incremental_charge_Ah,
                         window.current_A, window.temperature_rel_C), axis=1)
    flat = np.r_[channels.reshape(-1), np.isfinite(channels).reshape(-1)][None, :].astype(np.float32)
    np.testing.assert_allclose(x[:69], curve_features(flat)[0], rtol=0, atol=1e-6)


def test_later_charge_samples_and_missing_temperature_cannot_invent_prefix():
    data = charge_data()
    before, _, meta = nasa_charge_view(operation("charge", 1, data))
    changed = {key: np.array(value, copy=True) for key, value in data.items()}
    stop = meta["source_end_index"] + 1
    changed["Current_measured"][stop:] = -100
    changed["Temperature_measured"][stop:] = -100
    after, _, _ = nasa_charge_view(operation("charge", 1, changed))
    np.testing.assert_array_equal(before, after)
    short = charge_data(np.full(20, 25.))
    features, _, info = nasa_charge_view(operation("charge", 1, short))
    assert features is not None and info["temperature_missing_in_prefix"]
    assert np.isnan(features[48:64]).all() and np.isnan(features[69])
    interior = charge_data()
    interior["Temperature_measured"][40] = np.nan
    features, _, info = nasa_charge_view(operation("charge", 1, interior))
    assert info["temperature_missing_in_prefix"] and np.isnan(features[48:64]).all()


def test_first_real_2p7_crossing_uses_seconds_and_boundary_interpolation():
    result = integrated_discharge(operation("discharge", 2, discharge_data()))
    assert result["status"] == "integrated_2p7"
    assert np.isclose(result["integrated_2p7_Ah"], 1.3)
    assert np.isclose(result["terminal_integrated_Ah"], 2.)
    assert np.isclose(result["crossing_time_s"], 2340.)
    terminal = integrated_discharge(operation("discharge", 2,
                            discharge_data(np.array([4., 3.5, 3.]))))
    assert terminal["status"] == "protocol_terminal_capacity_not_standard_2p7"
    assert "integrated_2p7_Ah" not in terminal


def test_pairing_never_reuses_or_sees_future_charge_and_reference_is_first_eligible():
    charge = charge_data()
    discharge = discharge_data()
    ops = [operation("discharge", 0, discharge),
           operation("charge", 1, charge),
           operation("impedance", 2, {}),
           operation("discharge", 3, discharge),
           operation("discharge", 4, discharge),
           operation("charge", 5, charge),
           operation("discharge", 6, discharge)]
    rows, pairs = pair_operations(ops)
    assert rows[0]["status"] == rows[4]["status"] == "unpaired_discharge"
    assert [(p["charge"]["index"], p["discharge_index"]) for p in pairs] == [(2, 4), (6, 7)]
    assert first_eligible_reference(pairs) is pairs[0]
    pairs[0]["label"]["status"] = "protocol_terminal_capacity_not_standard_2p7"
    assert first_eligible_reference(pairs) is pairs[1]
    reversed_rows, reversed_pairs = pair_operations([
        operation("charge", 5, charge), operation("discharge", 4, discharge)])
    assert reversed_rows[1]["status"] == "nonmonotonic_operation_start"
    assert not reversed_pairs


def make_archive(path: Path, conflicting=False, traversal=False):
    with zipfile.ZipFile(path, "w") as outer:
        for index in range(6):
            inner_bytes = io.BytesIO()
            with zipfile.ZipFile(inner_bytes, "w") as nested:
                name = "B0001.mat" if index in (0, 5) else f"B{index+1:04d}.mat"
                if traversal and index == 5:
                    name = "../B0001.mat"
                content = b"first" if index in (0, 5) and not (conflicting and index == 5) else bytes([index])
                nested.writestr(name, content)
                nested.writestr("README.txt", b"source")
            outer.writestr(f"nested-{index}.zip", inner_bytes.getvalue())


def test_duplicate_lineage_requires_same_bytes_and_safe_members(tmp_path):
    good = tmp_path / "good.zip"; make_archive(good)
    inventory = archive_inventory(good)
    assert inventory["mat_members"] == 6 and inventory["distinct_cells"] == 5
    assert len(inventory["duplicate_cells"]["B0001"]) == 2
    bad = tmp_path / "bad.zip"; make_archive(bad, conflicting=True)
    with pytest.raises(ValueError, match="conflicting physical cell bytes"):
        archive_inventory(bad)
    unsafe = tmp_path / "unsafe.zip"; make_archive(unsafe, traversal=True)
    with pytest.raises(ValueError, match="unsafe"):
        archive_inventory(unsafe)


def test_frozen_leaf_mode_tie_and_inference_accepts_no_labels():
    summary = {"selections": [{"method": "extra_trees_matched", "config_values": {"min_samples_leaf": x}}
                              for x in (1, 3, 7)]}
    assert selected_leaf(summary)[0] == 7
    x = np.zeros((2, 71), dtype=float)
    x[:, 66] = x[:, 70] = 1.
    r = x.copy(); q = np.zeros(2)
    validate_inputs(x, r, q)
    with pytest.raises(TypeError):
        predict_soh(x, r, q, {}, labels=np.ones(2))
    x[0, 0] = np.nan
    with pytest.raises(ValueError, match="nonfinite required"):
        validate_inputs(x, r, q)


def test_frozen_tree_inference_uses_training_float32_feature_dtype():
    class DtypeCheckingTree:
        def predict(self, z):
            assert z.dtype == np.float32
            assert z.shape == (2, 214)
            return np.zeros(len(z))
    x = np.zeros((2, 71), dtype=np.float32)
    x[:, 66] = x[:, 70] = 1.
    artifact = {"median": np.zeros(71), "mean": np.zeros(71),
                "scale": np.ones(71), "target_mu": 0., "target_scale": .1,
                "models": [DtypeCheckingTree()] * 3}
    np.testing.assert_array_equal(predict_soh(x, x, np.zeros(2), artifact), [1., 1.])
