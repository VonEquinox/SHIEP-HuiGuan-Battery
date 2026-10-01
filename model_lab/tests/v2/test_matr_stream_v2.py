import struct

import h5py
import numpy as np
import pytest

from model_lab.modeling.v2.matr_stream import (
    AUTHOR_APPEND_COUNTS, BATCH_IDS, CONTINUATIONS, author_paper_selection,
    inventory_identity_frame, inventory_matr_hdf5, parse_matr_hdf5,
)


def make_batch(path, cells, *, orientation="column", mcos=False):
    """Tiny original-shaped 7.3 data; deliberately no cycle_life reads."""
    with h5py.File(path, "w") as handle:
        refs = handle.create_group("#refs#")
        batch = handle.create_group("batch")
        shape = (len(cells), 1) if orientation == "column" else (1, len(cells))
        fields = {key: batch.create_dataset(key, shape, dtype=h5py.ref_dtype) for key in ("barcode", "channel_id", "policy_readable", "summary", "cycles", "cycle_life")}
        def char(name, value):
            node = refs.create_dataset(name, data=np.array([ord(c) for c in value], dtype="u2").reshape(-1, 1))
            node.attrs["MATLAB_class"] = b"char"
            return node
        for index, cell in enumerate(cells):
            coordinate = np.unravel_index(index, shape)
            fields["barcode"][coordinate] = char(f"b{index}", cell["barcode"]).ref
            fields["channel_id"][coordinate] = char(f"ch{index}", str(cell.get("channel", index + 20))).ref
            fields["policy_readable"][coordinate] = char(f"p{index}", "4C(80%)-4C").ref
            # A soft link in an unused future-label field proves no recursion.
            fields["cycle_life"][coordinate] = refs.create_dataset(f"future{index}", shape=(10_000_000,), dtype="f8").ref
            summary = refs.create_group(f"s{index}")
            numbers = cell.get("numbers", [10, 11, 12, 13])
            capacity = cell.get("capacity", [1.1, 1., .88, .87])
            summary.create_dataset("cycle", data=np.array(numbers).reshape(1, -1))
            summary.create_dataset("QDischarge", data=np.array(capacity).reshape(1, -1))
            summary.create_dataset("QCharge", data=np.full((1, len(numbers)), 1.2))
            fields["summary"][coordinate] = summary.ref
            cycles = refs.create_group(f"c{index}")
            for key, values in {"t": [0, .5, 1.], "V": [3., 3.5, 4.], "I": [-1., -1., -1.], "T": [25., 25., 25.], "Qd": [0., .5, 1.], "Qc": [0., 0., 0.]}.items():
                dataset = cycles.create_dataset(key, (len(numbers), 1), dtype=h5py.ref_dtype)
                for cycle in range(len(numbers)):
                    node = refs.create_dataset(f"raw{index}_{cycle}_{key}", data=values)
                    dataset[cycle, 0] = node.ref
            fields["cycles"][coordinate] = cycles.ref
        if mcos:
            texts = [cell["barcode"] for cell in cells] + [str(cell.get("channel", index + 20)) for index, cell in enumerate(cells)]
            count = len(texts)
            offsets = [56, 88, 96 + 16*count, 120 + 40*count, 128 + 40*count, 128 + 40*count]
            blob = struct.pack("<10I", 2, 2, *offsets, 0, 0)
            blob += b"any\0string\0".ljust(16, b"\0")
            blob += struct.pack("<8I", 0, 0, 0, 0, 0, 2, 0, 0)
            blob += b"\0"*8
            blob += b"".join(struct.pack("<4I", 1, 1, 1, index) for index in range(count))
            blob += b"\0"*24
            blob += b"".join(struct.pack("<6I", 1, 0, 0, index + 1, 0, index + 1) for index in range(count))
            blob += b"\0"*8
            subsystem = handle.create_group("#subsystem#")
            table = subsystem.create_dataset("MCOS", (1, count + 2), dtype=h5py.ref_dtype)
            table[0, 0] = refs.create_dataset("mcos_blob", data=np.frombuffer(blob, dtype="u1")).ref
            table[0, 1] = refs.create_dataset("mcos_empty", data=[0, 0]).ref
            for index, text in enumerate(texts):
                payload = text.encode("utf-16-le")
                payload += b"\0"*((-len(payload)) % 8)
                values = np.r_[np.array([1, 2, 1, 1, len(text)], dtype="u8"), np.frombuffer(payload, dtype="<u8")]
                table[0, index + 2] = refs.create_dataset(f"mcos_string_{index}", data=values).ref
                pointer = refs.create_dataset(f"pointer_{index}", data=np.array([0xDD000000, 2, 1, 1, index + 1, 1], dtype="u4").reshape(1, -1))
                pointer.attrs["MATLAB_class"] = b"string"
                fields["barcode" if index < len(cells) else "channel_id"][np.unravel_index(index % len(cells), shape)] = pointer.ref
    return path


@pytest.mark.parametrize("orientation", ["column", "row"])
def test_original_string_identity_and_bounded_native_signals(tmp_path, orientation):
    path = make_batch(tmp_path / "2018-04-12_corrected.mat", [{"barcode": "EL150800460514", "channel": 46}], orientation=orientation, mcos=True)
    inventory = inventory_matr_hdf5([path], repair_continuations=False)
    identity = inventory["records"][0]
    assert identity["source_cell_id"] == "EL150800460514" and identity["original_channel"] == "46"
    assert identity["batch_index_one"] == 1 and identity["barcode_verified"]
    parsed = parse_matr_hdf5([path], inventory, author_paper_selection_enabled=False)
    assert parsed.identity_map.source_protocol_id.iloc[0] == "4C(80%)-4C"
    assert parsed.segments.time_s.iloc[0] == [0., 30., 60.]
    assert parsed.segments.discharge_capacity_Ah.iloc[0] == [0., .5, 1.]
    assert parsed.cycles.charge_capacity_Ah.tolist() == [1.2]*4
    survival = parsed.targets[parsed.targets.target_name == "rul"].iloc[0]
    assert survival["value"] == 13 and survival["threshold_operator"] == "strictly_less_than"
    assert parsed.targets[parsed.targets.target_name == "soh"].value.iloc[0] == 1.
    assert "cycle_life" not in parsed.cycles


def test_missing_identity_and_unexpected_duplicate_rejected(tmp_path):
    path = make_batch(tmp_path / "2018-04-12_corrected.mat", [{"barcode": ""}])
    with pytest.raises(ValueError, match="barcode missing"):
        inventory_matr_hdf5([path], repair_continuations=False)
    path = make_batch(path, [{"barcode": "same"}, {"barcode": "SAME"}])
    with pytest.raises(ValueError, match="duplicate"):
        inventory_matr_hdf5([path], repair_continuations=False)


def test_selected_identity_never_reads_foreign_measurements(tmp_path):
    path = make_batch(tmp_path / "2018-04-12_corrected.mat", [{"barcode": "allowed"}, {"barcode": "sealed"}])
    inventory = inventory_matr_hdf5([path], repair_continuations=False)
    with h5py.File(path, "r+") as handle:
        foreign = handle[handle["batch/summary"][1, 0]]
        del foreign["QDischarge"]
        foreign["QDischarge"] = h5py.ExternalLink("foreign.h5", "measurement")
    parsed = parse_matr_hdf5([path], inventory, selected_physical_ids=["matr:allowed"], author_paper_selection_enabled=False)
    assert len(parsed.identity_map) == 2
    assert parsed.cycles.physical_cell_id.unique().tolist() == ["matr:allowed"]
    with pytest.raises(ValueError, match="linked"):
        parse_matr_hdf5([path], inventory, author_paper_selection_enabled=False)


def test_segment_budget_and_cycle_landmark_selection(tmp_path):
    path = make_batch(tmp_path / "2018-04-12_corrected.mat", [{"barcode": "a", "numbers": list(range(1, 101)), "capacity": [1.1]*100}])
    inventory = inventory_matr_hdf5([path], repair_continuations=False)
    parsed = parse_matr_hdf5([path], inventory, author_paper_selection_enabled=False)
    assert len(parsed.segments) == 32 and {10, 100} <= set(parsed.segments.cycle_index)
    assert 100 in parsed.segments.available_at.tolist()
    with pytest.raises(ValueError, match="total resource budget"):
        parse_matr_hdf5([path], inventory, max_total_points=2, author_paper_selection_enabled=False)


def test_all_continuation_refs_and_repaired_availability(tmp_path):
    first = [{"barcode": f"joined-{index}", "numbers": [1, 2], "capacity": [1.1, 1.09]} for index in range(5)]
    second = [{"barcode": f"independent-{index}", "numbers": [1, 2], "capacity": [1.08, 1.07]} for index in range(17)]
    for first_index, second_index in CONTINUATIONS:
        second[second_index]["barcode"] = first[first_index]["barcode"]
    paths = [make_batch(tmp_path / f"{BATCH_IDS[0]}_corrected.mat", first), make_batch(tmp_path / f"{BATCH_IDS[1]}_corrected.mat", second)]
    inventory = inventory_matr_hdf5(paths)
    assert len(inventory_identity_frame(inventory)) == 17
    assert [row["expected_second_raw_cycle_count"] for row in inventory["continuations"]] == list(AUTHOR_APPEND_COUNTS)
    parsed = parse_matr_hdf5(paths, inventory, author_paper_selection_enabled=False, enforce_author_append_counts=False)
    cycles = parsed.cycles[parsed.cycles.physical_cell_id == "matr:joined-0"]
    assert cycles.cycle_index.tolist() == [1, 2, 3, 4]
    assert cycles.observed_at.tolist() == cycles.available_at.tolist() == [1, 2, 3, 4]
    assert cycles.source_cycle_index.tolist() == [1, 2, 1, 2]
    curves = parsed.segments[parsed.segments.physical_cell_id == "matr:joined-0"]
    assert curves.cycle_index.tolist() == [1, 2, 3, 4]
    assert curves.iloc[0].raw_ref.startswith(str(paths[0])) and curves.iloc[2].raw_ref.startswith(str(paths[1]))
    with pytest.raises(ValueError, match="append count"):
        parse_matr_hdf5(paths, inventory, author_paper_selection_enabled=False)


def test_author_selection_uses_filtered_positions(tmp_path):
    records = []
    for batch, count in zip(BATCH_IDS, (46, 43, 46)):
        for index in range(count):
            records.append({"batch_id": batch, "batch_index_zero": index, "source_record_id": f"{batch}:record-{index + 1}", "physical_cell_id": f"{batch}:{index}", "terminal_capacity_Ah": .87})
    # Remove original zero position 0 before selecting the third noisy row.
    records[-46]["terminal_capacity_Ah"] = .9
    selection = author_paper_selection(records)
    noisy = [row for row in selection["exclusions"] if row["reason"] == "author_noise_position_after_terminal_filter"]
    assert noisy[0]["source_record_id"] == f"{BATCH_IDS[2]}:record-4"
    assert selection["counts"] == {"batch1": 41, "batch2": 43, "batch3": 41, "total": 125}
    assert all(row["source_record_id"] != f"{BATCH_IDS[2]}:record-38" for row in selection["selection_order"])


def test_reference_cycle_and_interval_right_censoring(tmp_path):
    path = make_batch(tmp_path / "2018-04-12_corrected.mat", [{"barcode": "gap", "numbers": [1, 10, 20], "capacity": [1.9, 1.1, .87]}, {"barcode": "right", "numbers": [1, 10, 20], "capacity": [1.9, 1.1, .88]}])
    inventory = inventory_matr_hdf5([path], repair_continuations=False)
    parsed = parse_matr_hdf5([path], inventory, author_paper_selection_enabled=False)
    survival = parsed.targets[parsed.targets.target_name == "rul"].set_index("physical_cell_id")
    assert survival.loc["matr:gap", "censor_type"] == "interval"
    assert survival.loc["matr:gap", "lower_event_bound"] == 10
    assert survival.loc["matr:right", "censor_type"] == "right"
    assert parsed.identity_map.reference_capacity_Ah.tolist() == [1.1, 1.1]
    assert parsed.identity_map.reference_cutoff.tolist() == [10, 10]


def test_identity_inventory_does_not_follow_future_label_link(tmp_path):
    path = make_batch(tmp_path / "2018-04-12_corrected.mat", [{"barcode": "a"}])
    with h5py.File(path, "r+") as handle:
        del handle["batch/cycle_life"]
        handle["batch/cycle_life"] = h5py.SoftLink("/future_targets")
    inventory = inventory_matr_hdf5([path], repair_continuations=False)
    assert inventory["identity_created_before_numeric_targets"]
    assert len(parse_matr_hdf5([path], inventory, author_paper_selection_enabled=False).cycles) == 4


def test_complete_scope_retains_bad_identity_and_separates_paper_convention(tmp_path):
    paths = []
    batch_cells = []
    for batch, count in zip(BATCH_IDS, (46, 48, 46)):
        batch_cells.append([{"barcode": f"{batch}-{index}", "numbers": [1, 2], "capacity": [1.1, .87]} for index in range(count)])
    # Controlled smooth continuation boundaries for this tiny fixture.
    for first, second in CONTINUATIONS:
        batch_cells[0][first]["capacity"] = [1.1, 1.09]
        batch_cells[1][second].update(barcode=batch_cells[0][first]["barcode"], capacity=[1.08, 1.07])
    # The paper example maps this observed but unfinished cell to n+1;
    # survival keeps the physically honest right censor at n.
    batch_cells[0][5]["capacity"] = [1.1, .88]
    for index in (0, 1):
        batch_cells[2][index]["capacity"] = [1.1, .9]
    for batch, cells in zip(BATCH_IDS, batch_cells):
        paths.append(make_batch(tmp_path / f"{batch}_corrected.mat", cells))
    inventory = inventory_matr_hdf5(paths)
    parsed = parse_matr_hdf5(paths, inventory, enforce_author_append_counts=False)
    assert len(parsed.identity_map) == 135
    assert parsed.cycles.physical_cell_id.nunique() == 134
    assert parsed.identity_map.paper_reproduction.sum() == 124
    failed_id = f"matr:{BATCH_IDS[2]}-37"
    bad = parsed.identity_map.set_index("physical_cell_id").loc[failed_id]
    assert not bad.survival_all_valid and not bad.paper_reproduction
    assert failed_id not in parsed.cycles.physical_cell_id.unique()
    case = parsed.targets[parsed.targets.physical_cell_id == f"matr:{BATCH_IDS[0]}-5"].set_index("target_name")
    assert case.loc["rul", "censor_type"] == "right" and case.loc["rul", "lower_event_bound"] == 2
    assert case.loc["author_paper_output", "value"] == 3
    assert case.loc["author_paper_output", "last_plus_one_convention"]
