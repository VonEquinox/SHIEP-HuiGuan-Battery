import numpy as np
from model_lab.data.xjtu_raw import build_cc_window


def signals():
    t = np.linspace(0, 60, 602)
    return {"relative_time_min": t, "voltage_V": np.linspace(3.51, 4.21, len(t)), "current_A": np.ones(len(t)), "temperature_C": 25 + .1*t}


def test_bracket_boundaries_without_exact_voltage_samples():
    c = signals()
    assert not np.any(c["voltage_V"] == 3.7)
    out = build_cc_window(c)
    assert out.valid
    assert abs(out.duration_min - 60*.4/.7) < 1e-6
    assert abs(out.charge_Ah - out.duration_min/60) < 1e-6


def test_post_cutoff_data_cannot_change_features():
    c = signals()
    before = build_cc_window(c)
    assert before.valid
    stop = before.source_end_index + 1
    for key in c:
        c[key][stop:] = -999.0
    after = build_cc_window(c)
    assert after.valid
    for key in ("elapsed_min", "current_A", "temperature_rel_C", "incremental_charge_Ah"):
        np.testing.assert_array_equal(getattr(before, key), getattr(after, key))


def test_small_voltage_reversal_keeps_chronological_prefix():
    c = signals()
    c["voltage_V"][300] = c["voltage_V"][299] - .0002
    out = build_cc_window(c)
    assert out.valid
    assert np.all(np.diff(out.elapsed_min) >= 0)


def test_missing_temperature_is_masked_not_fake_measurement():
    c = signals(); c["temperature_C"][:] = np.nan
    out = build_cc_window(c)
    assert out.valid
    assert not out.finite_mask[:,2].any()
    assert np.isnan(out.temperature_rel_C).all()
