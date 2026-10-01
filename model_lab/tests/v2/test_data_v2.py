from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from model_lab.modeling.v2.data import (
    ParsedDataset, audit_manifest, build_survival_target, efficiency_label,
    freeze_group_split, parse_xjtu_mat, read_measurement_file,
    repair_matr_continuations, verify_matr_continuation, visible_prefix,
    write_json,
)


def test_survival_censoring_and_target_basis():
    censored = build_survival_target([1, 2, 3], [1.1, 1., .9], threshold_Ah=.88, target_definition_id="nominal")
    assert censored["censor_type"] == "right" and censored["value"] is None
    assert censored["lower_event_bound"] == 3 and censored["upper_event_bound"] is None
    event = build_survival_target([1, 2, 3], [1.1, .9, .87], threshold_Ah=.88, target_definition_id="nominal")
    assert event["censor_type"] == "exact" and event["value"] == 3
    interval = build_survival_target([1, 10, 20], [1.1, .9, .87], threshold_Ah=.88, target_definition_id="reference")
    assert interval["censor_type"] == "interval" and interval["lower_event_bound"] == 10
    unknown = build_survival_target([1, 2], [1.1, .87], threshold_Ah=.88, target_definition_id="xjtu", physical_cycles_known=False)
    assert unknown["label_status"] == "unavailable"
    exact_boundary = build_survival_target([1, 2], [1.1, .88], threshold_Ah=.88, target_definition_id="paper", inclusive=False)
    assert exact_boundary["censor_type"] == "right" and exact_boundary["threshold_operator"] == "strictly_less_than"


def test_matr_zero_based_continuations_and_shared_identity():
    records = []
    continuation = [7, 8, 9, 15, 16]
    for index in range(5):
        records.append({"batch_id": "2017-05-12", "batch_index_zero": index, "source_record_id": f"a-{index}", "source_identity": f"barcode-{index}", "physical_cell_id": f"matr:{index}", "cycles": [{"physical_cell_id": f"matr:{index}", "cycle_index": 1, "capacity_Ah": 1.1}, {"physical_cell_id": f"matr:{index}", "cycle_index": 2, "capacity_Ah": 1.09}]})
        records.append({"batch_id": "2017-06-30", "batch_index_zero": continuation[index], "source_record_id": f"b-{index}", "source_identity": f"barcode-{index}", "physical_cell_id": f"wrong:{index}", "cycles": [{"physical_cell_id": f"wrong:{index}", "cycle_index": 1, "capacity_Ah": 1.08}, {"physical_cell_id": f"wrong:{index}", "cycle_index": 2, "capacity_Ah": 1.07}]})
    joined = repair_matr_continuations(records)
    assert len(joined) == 5
    for row in joined:
        assert row["identity_verified"]
        assert row["cycles"].cycle_index.tolist() == [1, 2, 3, 4]
        assert row["cycles"].physical_cell_id.nunique() == 1
    bad = {**records[1], "source_identity": "other-barcode"}
    with pytest.raises(ValueError, match="identity"):
        verify_matr_continuation(records[0], bad)


def test_protected_file_rejected_before_open_and_no_pickle(tmp_path):
    with pytest.raises(PermissionError):
        parse_xjtu_mat(tmp_path / "Batch-4" / "R3_battery-5.mat")
    path = tmp_path / "payload.pkl"
    path.write_bytes(b"not executed")
    with pytest.raises(ValueError, match="pickle"):
        read_measurement_file(path)


def test_xjtu_fixture_preserves_rpt_and_curves(tmp_path):
    path = tmp_path / "Batch-4" / "R3_battery-1.mat"
    path.parent.mkdir()
    def cycle(capacity):
        return {"relative_time_min": np.array([0, 1, 2, 0, 1, 2]), "voltage_V": np.array([3.7, 3.8, 4.1, 4.0, 3.8, 3.7]), "current_A": np.array([1, 1, 1, -1, -1, -1]), "temperature_C": np.full(6, 25), "capacity_Ah": np.full(6, capacity), "description": "test capacity"}
    savemat(path, {"data": [cycle(2.), cycle(1.9)], "summary": {"discharge_capacity_Ah": [2., 1.9], "cycle_life": 999}})
    parsed = parse_xjtu_mat(path)
    assert parsed.targets.value.tolist() == [1., .95]
    assert parsed.segments.time_s.iloc[0] == [0., 60., 120.]
    assert parsed.cycles.physical_cycles_known.eq(False).all()
    assert "cycle_life" not in parsed.cycles.columns
    assert len(parsed.segments) == 4


def test_group_split_and_prefix_leakage_audit(tmp_path):
    identities = pd.DataFrame({"physical_cell_id": [f"a-{i}" for i in range(21)]})
    split = freeze_group_split(identities, ratios=(11/21, 3/21, 4/21, 3/21))
    assert split["counts"] == {"train": 11, "dev": 3, "calibration": 4, "final": 3}
    repeated = freeze_group_split(pd.concat([identities, identities]), ratios=(11/21, 3/21, 4/21, 3/21))
    assert split == repeated
    rows = pd.DataFrame({"physical_cell_id": ["a-1", "a-1", "a-2"], "available_at": [1., 100., 1.], "cycle_life": [1000, 1000, 1000]})
    visible = visible_prefix(rows, 1, physical_cell_id="a-1")
    assert len(visible) == 1 and "cycle_life" not in visible
    dataset = ParsedDataset(identity_map=identities)
    output = tmp_path / "data" / "derived" / "v2" / "case"
    manifest = dataset.write(output, split)
    assert audit_manifest(output / "manifest.json")["passed"]
    manifest["queries"] = [{"query_id": "q1", "physical_cell_id": "a-1", "visible_cutoff": 10, "feature_dependencies": [{"available_at": 100}]}]
    write_json(output / "manifest.json", manifest)
    assert not audit_manifest(output / "manifest.json")["passed"]


def test_efficiency_requires_closed_metering_boundary():
    label = efficiency_label([0, 1, 2], [3., 3., 3.], [1., 0., -1.], complete=False, start_soc=.5, end_soc=.5, metering_boundary="cell")
    assert label["label_status"] == "unavailable" and label["value"] is None
    label = efficiency_label([0, 1, 2], [3., 3., 3.], [1., 0., -.9], complete=True, start_soc=.5, end_soc=.5, metering_boundary="cell")
    assert label["value"] == pytest.approx(.9)


def test_hdf5_external_link_rejected(tmp_path):
    import h5py
    path = tmp_path / "linked.h5"
    with h5py.File(path, "w") as handle:
        handle["foreign"] = h5py.ExternalLink("foreign.h5", "payload")
    with pytest.raises(ValueError, match="linked"):
        read_measurement_file(path)


def test_matr_parser_keeps_both_continuation_curves_and_raw_refs(tmp_path):
    from model_lab.modeling.v2.data import parse_matr_mat
    def cell(barcode, q):
        return {"barcode": barcode, "policy": "two_step", "summary": {"cycle": [1, 2], "QDischarge": q}, "cycles": [{"t": [0., 1.], "V": [3., 3.5], "I": [1., 1.], "T": [25., 25.]}, {"t": [0., 1.], "V": [3., 3.5], "I": [1., 1.], "T": [25., 25.]}]}
    first = [cell(f"barcode-{i}", [1.1, 1.09]) for i in range(5)]
    second = [cell(f"independent-{i}", [1.08, 1.07]) for i in range(17)]
    for i, index in enumerate([7, 8, 9, 15, 16]):
        second[index] = cell(f"barcode-{i}", [1.08, 1.07])
    first_path = tmp_path / "2017-05-12_corrected.mat"
    second_path = tmp_path / "2017-06-30_corrected.mat"
    savemat(first_path, {"batch": first})
    savemat(second_path, {"batch": second})
    parsed = parse_matr_mat([first_path, second_path])
    curves = parsed.segments[parsed.segments.physical_cell_id == "matr:barcode-0"]
    assert curves.cycle_index.tolist() == [1, 2, 3, 4]
    assert curves.iloc[0].raw_ref.startswith(str(first_path))
    assert curves.iloc[2].raw_ref.startswith(str(second_path))
    assert curves.iloc[0].time_s == [0., 60.]
