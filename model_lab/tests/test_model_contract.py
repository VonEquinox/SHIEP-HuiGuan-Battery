from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from model_lab.data.window_dataset import PrefixWindowDataset, eligible_indices, fit_scaler, load_canonical_csv, split_cell_indices
from model_lab.modeling.cada import CADA


def _cells(tmp_path: Path):
    paths = []
    for cell, offset in [("a", 0.0), ("b", 1.0), ("c", 2.0), ("d", 3.0), ("e", 4.0)]:
        frame = pd.DataFrame({"cell_id": [cell] * 6, "cycle_id": range(6), "feature_v": np.arange(6, dtype=float) + offset, "feature_i": np.ones(6), "capacity": 2.0 - np.arange(6) * 0.02})
        path = tmp_path / f"{cell}.csv"; frame.to_csv(path, index=False); paths.append(path)
    return load_canonical_csv(paths, feature_allowlist=("feature_v", "feature_i"))


def test_physical_cell_split_and_train_only_scaler(tmp_path: Path):
    cells = _cells(tmp_path)
    train, val, test = split_cell_indices(cells)
    assert not set(train) & set(val) and not set(train) & set(test) and not set(val) & set(test)
    scaler = fit_scaler(cells, train)
    assert np.allclose(scaler["mean"], np.mean(np.concatenate([cells[i].frame.loc[:, cells[i].feature_columns].to_numpy() for i in train]), axis=0))
    assert not np.allclose(scaler["mean"], np.mean(np.concatenate([x.frame.loc[:, x.feature_columns].to_numpy() for x in cells]), axis=0))


def test_future_rows_do_not_change_prefix_input(tmp_path: Path):
    cells = _cells(tmp_path)
    train, _, _ = split_cell_indices(cells)
    scaler = fit_scaler(cells, train)
    indices = eligible_indices(cells, [train[0]])
    ds = PrefixWindowDataset(cells, indices, scaler)
    before = ds[2]
    cells[train[0]].frame.loc[5, "feature_v"] = 99999.0
    after = ds[2]
    assert torch.equal(before["current"], after["current"])
    assert torch.equal(before["history"], after["history"])


def test_target_capacity_is_not_a_feature_and_padding_is_masked(tmp_path: Path):
    cells = _cells(tmp_path)
    train, _, _ = split_cell_indices(cells)
    ds = PrefixWindowDataset(cells, eligible_indices(cells, [train[0]]), fit_scaler(cells, train))
    sample = ds[0]
    assert "capacity" not in cells[train[0]].feature_columns
    assert float(sample["history_mask"].sum()) == 1.0
    model = CADA(ds.dim)
    batch = {key: value.unsqueeze(0) for key, value in sample.items() if isinstance(value, torch.Tensor)}
    out1 = model(batch["current"], batch["reference"], batch["history"], batch["history_mask"], batch["quality_gate"])
    batch["history"][batch["history_mask"] == 0] = 123456.0
    out2 = model(batch["current"], batch["reference"], batch["history"], batch["history_mask"], batch["quality_gate"])
    assert torch.allclose(out1, out2, atol=1e-6)


def test_cada_backprop_and_save_load(tmp_path: Path):
    model = CADA(3)
    inputs = [torch.randn(4, 3), torch.randn(4, 3), torch.randn(4, 8, 3), torch.ones(4, 8), torch.ones(4, 1)]
    loss = model(*inputs).pow(2).mean()
    loss.backward()
    assert any(parameter.grad is not None for parameter in model.parameters())
    path = tmp_path / "model.pt"; torch.save(model.state_dict(), path)
    restored = CADA(3); restored.load_state_dict(torch.load(path, weights_only=True))
    with torch.no_grad():
        assert torch.allclose(model(*inputs), restored(*inputs))


def test_duplicate_cell_and_target_derived_feature_are_rejected(tmp_path: Path):
    frame = pd.DataFrame({"cell_id": ["same", "same"], "cycle_id": [0, 1], "feature_v": [1.0, 1.1], "soh": [1.0, 0.9], "capacity": [2.0, 1.8]})
    first = tmp_path / "a.csv"; second = tmp_path / "b.csv"; frame.to_csv(first, index=False); frame.to_csv(second, index=False)
    with pytest.raises(ValueError, match="duplicate"):
        load_canonical_csv([first, second], feature_allowlist=("feature_v",))
    with pytest.raises(ValueError, match="target/derived"):
        load_canonical_csv([first], feature_allowlist=("soh",))


def test_nan_is_imputed_from_train_scaler_and_marked(tmp_path: Path):
    cells = _cells(tmp_path)
    cells[0].frame.loc[1, "feature_v"] = np.nan
    # Rebuild the cached array from the edited frame to model a parsed NaN source.
    path = tmp_path / "a.csv"; cells[0].frame.to_csv(path, index=False)
    cells = load_canonical_csv([path, *(tmp_path / f"{x}.csv" for x in "bcde")], feature_allowlist=("feature_v", "feature_i"))
    train, _, _ = split_cell_indices(cells)
    ds = PrefixWindowDataset(cells, eligible_indices(cells, [0]), fit_scaler(cells, train))
    sample = ds[1]
    assert torch.isfinite(sample["current"]).all()
    assert float(sample["feature_mask"][-1, 0]) == 0.0
