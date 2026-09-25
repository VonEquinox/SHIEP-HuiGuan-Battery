from dataclasses import replace

import numpy as np
import torch

from model_lab.modeling.anchored_conditional import AnchoredConditionalResidual
from model_lab.modeling.conditional_kernel import ConditionalDifferenceKernel
from model_lab.modeling.conditional_reference import FiLMReferencePotential
from model_lab.modeling.embedded_potential import fit_numeric_bins
from model_lab.scripts.train_nested_cv import (
    DevData, cell_metrics, evaluate_method_fold, fit_transform, load_development,
    matched, split_indices, summarize_predictions,
)


def fixture_data():
    rng = np.random.default_rng(17)
    cells = [f"Batch-{batch}/cell-{number}" for batch in (4, 5, 6) for number in (1, 2, 3)]
    cell = np.repeat(cells, 4)
    batch = np.array([c.split("/")[0] for c in cell])
    reference = np.repeat(rng.normal(size=(len(cells), 71)).astype("float32"), 4, axis=0)
    age = np.tile(np.arange(4), len(cells))
    x = reference.copy()
    x[:, 0] += .03 * age
    x[:, 1] -= .02 * age
    soh = np.exp(-.02 * age + .001 * rng.normal(size=len(cell)))
    data = DevData(x, reference, np.log(soh).astype("float32"), soh, cell, batch,
                   np.arange(len(cell)))
    fold = {"train_cells": [c for c in cells if not c.endswith("cell-3")],
            "validation_cells": [c for c in cells if c.endswith("cell-3")]}
    return data, fold


def test_nested_cells_are_disjoint_and_cover_development():
    data, fold = fixture_data()
    a, b, train, outer = split_indices(data, fold, 0)
    assert len(set(data.cell[a])) == len(set(data.cell[b])) == len(set(data.cell[outer])) == 3
    assert not (set(data.cell[a]) & set(data.cell[b]))
    assert not (set(data.cell[train]) & set(data.cell[outer]))
    np.testing.assert_array_equal(np.sort(np.r_[train, outer]), np.arange(len(data.soh)))


def test_validation_sentinels_do_not_change_scaler_or_embedding_knots():
    data, fold = fixture_data()
    inner_train, inner_valid, _, outer_valid = split_indices(data, fold, 0)
    data.x[inner_train[0], 4] = np.nan
    sx, sr, stats = fit_transform(data, inner_train)
    bins = fit_numeric_bins(torch.from_numpy(matched(sx, sr, data.log_ratio)[inner_train]), 4)
    altered = replace(data, x=data.x.copy(), reference=data.reference.copy())
    altered.x[np.r_[inner_valid, outer_valid], :] = 1e7
    altered.reference[np.r_[inner_valid, outer_valid], :] = -1e7
    sx2, sr2, stats2 = fit_transform(altered, inner_train)
    bins2 = fit_numeric_bins(torch.from_numpy(matched(sx2, sr2, data.log_ratio)[inner_train]), 4)
    for key in stats:
        np.testing.assert_array_equal(stats[key], stats2[key])
    for first, second in zip(bins, bins2):
        torch.testing.assert_close(first, second)


def test_outer_labels_cannot_change_selection_epochs_or_refit_state():
    torch.set_num_threads(4)
    data, fold = fixture_data()
    indices = split_indices(data, fold, 0)
    configs = ({"width": 8, "rank": 2, "lr": .001, "weight_decay": .01},
               {"width": 8, "rank": 2, "lr": .003, "weight_decay": .01})
    one = evaluate_method_fold(data, "anchored_conditional", 0, indices, torch.device("cpu"),
                               10, 10, configs=configs, seeds=(0,))
    changed = replace(data, soh=data.soh.copy())
    changed.soh[indices[3]] *= 1.5
    two = evaluate_method_fold(changed, "anchored_conditional", 0, indices, torch.device("cpu"),
                               10, 10, configs=configs, seeds=(0,))
    assert one["selection"] == two["selection"]
    assert [(r["best_epoch"], r["state_sha256"]) for r in one["trials"]] == [
        (r["best_epoch"], r["state_sha256"]) for r in two["trials"]]
    assert one["refits"][0]["state_sha256"] == two["refits"][0]["state_sha256"]
    assert [r["pred_soh"] for r in one["predictions"]] == [r["pred_soh"] for r in two["predictions"]]
    assert one["refits"][0]["outer_cell_mae_pp"] != two["refits"][0]["outer_cell_mae_pp"]


def test_heldout_label_perturbation_is_removed_by_loader(tmp_path):
    cells = np.array([f"Batch-{4+i//8}/cell-{i}" for i in range(24)])
    held = np.array([False] * 21 + [True] * 3)
    values = np.ones(24)
    def write(path, labels):
        np.savez(path, x=np.ones((24, 71), dtype="float32"),
                 reference=np.ones((24, 71), dtype="float32"),
                 log_window_ratio=np.zeros(24, dtype="float32"), soh=labels,
                 cell=cells, protocol=np.array([c.split("/")[0] for c in cells]), holdout=held)
    first = tmp_path / "first.npz"; second = tmp_path / "second.npz"
    write(first, values)
    changed = values.copy(); changed[held] = [10, 20, 30]
    write(second, changed)
    a, _ = load_development(first); b, _ = load_development(second)
    for key in ("x", "reference", "log_ratio", "soh", "cell", "batch", "source_row"):
        np.testing.assert_array_equal(getattr(a, key), getattr(b, key))


def test_single_seed_and_geometric_ensemble_are_distinct():
    cell = np.array(["Batch-4/A", "Batch-5/B"])
    data = DevData(np.zeros((2, 71), dtype="float32"), np.zeros((2, 71), dtype="float32"),
                   np.zeros(2, dtype="float32"), np.ones(2), cell,
                   np.array(["Batch-4", "Batch-5"]),
                   np.arange(2))
    predictions = []
    for seed, values in enumerate(([.8, 1.2], [1., 1.], [1.2, .8])):
        for row, value in enumerate(values):
            predictions.append({"method": "matched_mlp", "source_row": row, "seed": seed,
                                "cell": str(cell[row]), "true_soh": 1., "pred_soh": value})
    summaries, missing = summarize_predictions(predictions, data, methods=("matched_mlp",))
    assert not missing
    np.testing.assert_allclose(summaries[0]["single_seed_cell_mae_pp"], [20., 0., 20.])
    assert np.isclose(summaries[0]["single_seed_mean_pp"], 40/3)
    assert summaries[0]["geometric_ensemble"]["cell_mae_pp"] < 2.
    assert np.isclose(cell_metrics(np.array([1., 1., 1.]), np.array([1., 1., .7]),
                                   np.array(["A", "A", "B"]))["cell_mae_pp"], 15.)


def test_anchored_identity_and_context_changes_slope():
    model = AnchoredConditionalResidual(4, width=8, rank=2)
    x = torch.randn(5, 4)
    torch.testing.assert_close(model(x, x), torch.zeros(5, 1), atol=1e-6, rtol=1e-6)
    with torch.no_grad():
        model.u.fill_(.2); model.v.fill_(.3)
    delta = torch.full_like(x, .1)
    first = model(x + delta, x)
    second = model(x + 1 + delta, x + 1)
    assert not torch.allclose(first, second)
    no_context = FiLMReferencePotential(4, 8, 2, False)
    torch.testing.assert_close(no_context.potential(x, x), no_context.potential(x, x+1))


def test_conditional_difference_kernel_psd_and_reference_identity():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(7, 4))
    reference = rng.normal(size=(7, 4))
    model = ConditionalDifferenceKernel(alpha=.1, gamma=.25)
    gram = model.kernel(x, reference, x, reference)
    np.testing.assert_allclose(gram, gram.T, atol=1e-12)
    assert np.linalg.eigvalsh(gram).min() >= -1e-10
    model.fit(x, reference, rng.normal(size=7) * .1, np.ones(7))
    np.testing.assert_allclose(model.predict_log(reference, reference), 0., atol=1e-12)
    assert model.scale > 0


def test_kernel_nested_state_is_outer_label_independent():
    data, fold = fixture_data()
    indices = split_indices(data, fold, 0)
    configs = ({"alpha": .1, "gamma": .25/142}, {"alpha": 1., "gamma": 1/142})
    one = evaluate_method_fold(data, "conditional_kernel", 0, indices, torch.device("cpu"),
                               10, 10, configs=configs, seeds=(0,))
    changed = replace(data, soh=data.soh.copy())
    changed.soh[indices[3]] *= 1.5
    two = evaluate_method_fold(changed, "conditional_kernel", 0, indices, torch.device("cpu"),
                               10, 10, configs=configs, seeds=(0,))
    assert one["selection"] == two["selection"]
    assert one["refits"][0]["state_sha256"] == two["refits"][0]["state_sha256"]
