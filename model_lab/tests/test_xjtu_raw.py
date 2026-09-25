import numpy as np

from model_lab.data.xjtu_raw import build_cc_window, description_family, split_time_segments


def _cycle(post_cutoff_scale: float = 1.0):
    voltage = np.linspace(3.7, 4.1, 12)
    time = np.linspace(0.0, 11.0, 12)
    current = np.full(12, 2.0)
    temperature = np.linspace(25.0, 26.0, 12)
    return {"relative_time_min": np.r_[time, [12.0, 13.0]], "voltage_V": np.r_[voltage, [3.2, 3.0]], "current_A": np.r_[current, np.array([-2.0, -2.0]) * post_cutoff_scale], "temperature_C": np.r_[temperature, [26.0, 26.0]]}


def test_diagnostic_family_and_time_reset_detection():
    assert description_family("0.5C charge and 0.2C discharge [test capacity]") == "diagnostic"
    assert description_family("2C charge and 1C discharge") == "routine"
    segments, resets = split_time_segments(np.array([0.0, 1.0, 2.0, 0.0, 1.0]))
    assert resets == 1
    assert [(s.start, s.stop) for s in segments] == [(0, 3), (3, 5)]


def test_post_cutoff_signal_does_not_change_input_window():
    first = build_cc_window(_cycle(1.0))
    changed = _cycle(1.0)
    changed["voltage_V"][-2:] = [4.25, 4.3]
    changed["current_A"][-2:] = [-999.0, -999.0]
    second = build_cc_window(changed)
    assert first.valid and second.valid
    assert np.allclose(first.elapsed_min, second.elapsed_min)
    assert np.allclose(first.current_A, second.current_A)
    assert not hasattr(first, "capacity_Ah")


def test_no_interpolation_across_time_reset_or_voltage_reversal():
    cycle = _cycle()
    cycle["relative_time_min"] = np.array([0.0, 1.0, 2.0, 0.0, 1.0, 2.0])
    cycle["voltage_V"] = np.array([3.7, 3.8, 3.9, 3.9, 4.0, 4.1])
    cycle["current_A"] = np.full(6, 2.0)
    cycle["temperature_C"] = np.full(6, 25.0)
    result = build_cc_window(cycle, points=8)
    assert not result.valid
    reversed_cycle = _cycle()
    reversed_cycle["voltage_V"][5] = 3.75
    result = build_cc_window(reversed_cycle)
    assert not result.valid


def test_window_uses_partial_charge_but_never_full_capacity_label():
    result = build_cc_window(_cycle())
    assert result.valid
    assert result.elapsed_min[0] == 0.0
    assert result.charge_Ah > 0
    assert result.finite_mask.shape == (64, 4)
    for name in ("capacity_Ah", "discharge_capacity_Ah", "cycle_life"):
        assert name not in result.__dict__
