"""Small deterministic toy fixtures only: no real CH benchmark training."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_lab.modeling.v2.generated_fault import (
    FAULT_CLASSES, FEATURE_NAMES, LIMITATION, NumericalGBDT,
    evaluate_generated_split, first_landmarks, fit_temperature,
    load_generated_dataset, multiclass_metrics, train_chemistry_models,
)


def write_bundle(tmp_path: Path) -> Path:
    """All four classes/chemistries appear in every split in this toy fixture."""
    identity, segments, targets, assignments, roots = [], [], [], {}, {}
    for split_index, split in enumerate(("train", "dev", "calibration", "final")):
        for label, name in enumerate(FAULT_CLASSES):
            for replica in range(2):
                root = f"toy-vin-{split_index}-{label}-{replica}"
                roots[root] = split
                for chemistry_index, chemistry in enumerate(("LFP", "NCM")):
                    physical = f"ch_batterygen:{chemistry}:{root}"
                    segment = physical + ":charge_1"
                    assignments[physical] = split
                    identity.append({"physical_cell_id": physical, "source_id": "ch_batterygen", "root_scenario_id": root, "chemistry": chemistry, "namespace": "demo_synthetic", "generation_parent_id": None})
                    statistics = {feature: label * 10 + chemistry_index + replica * .1 + index * .01 for index, feature in enumerate(FEATURE_NAMES)}
                    segments.append({"physical_cell_id": physical, "source_id": "ch_batterygen", "root_scenario_id": root, "chemistry": chemistry, "segment_id": segment, "cycle_index": 1, "provenance": "public_generated", **statistics})
                    targets.append({"physical_cell_id": physical, "source_id": "ch_batterygen", "segment_id": segment, "target_name": "fault", "class_name": name, "label_status": "available", "origin": "public_generated"})
    manifest = {"namespace": "demo_synthetic", "sources": [{"source_id": "ch_batterygen", "origin": "public_generated"}], "tables": {}, "split_manifest": "split_manifest.json"}
    for name, rows in (("identity_map", identity), ("segments", segments), ("targets", targets)):
        path = tmp_path / f"{name}.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False)
        # A stale machine-local path exercises relocatable bundle fallback.
        manifest["tables"][name] = {"path": f"/old-host/bundle/{name}.parquet", "rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (tmp_path / "split_manifest.json").write_text(json.dumps({"group_column": "root_scenario_id", "assignments": assignments, "root_assignments": roots}))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def change_table(manifest: Path, name: str, mutate) -> None:
    path = manifest.parent / f"{name}.parquet"
    frame = pd.read_parquet(path)
    mutate(frame)
    frame.to_parquet(path, index=False)
    data = json.loads(manifest.read_text())
    data["tables"][name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))


@pytest.fixture
def toy_bundle(tmp_path):
    return write_bundle(tmp_path)


def test_bundle_keeps_final_sealed_and_distinguishes_expert_synthesis(toy_bundle):
    data = load_generated_dataset(toy_bundle)
    assert set(data.rows["split"]) == {"train", "dev", "calibration"}
    with pytest.raises(ValueError, match="sealed"):
        data.subset("final")
    opened = load_generated_dataset(toy_bundle, allow_exploratory_final=True)
    assert opened.subset("final")["root_scenario_id"].nunique() == 8
    manifest = json.loads(toy_bundle.read_text())
    manifest["sources"][0]["origin"] = "expert_synthetic"
    toy_bundle.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="public_generated"):
        load_generated_dataset(toy_bundle)


def test_bundle_hashes_and_conservative_VIN_split_are_enforced(toy_bundle):
    path = toy_bundle.parent / "segments.parquet"
    original = path.read_bytes()
    path.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_generated_dataset(toy_bundle)
    path.write_bytes(original)
    split_path = toy_bundle.parent / "split_manifest.json"
    split = json.loads(split_path.read_text())
    key = next(k for k, v in split["assignments"].items() if v == "train")
    split["assignments"][key] = "dev"
    split_path.write_text(json.dumps(split))
    with pytest.raises(ValueError, match="leaks across splits"):
        load_generated_dataset(toy_bundle)


def test_unknown_fault_class_and_identity_disagreement_fail(toy_bundle):
    change_table(toy_bundle, "targets", lambda frame: frame.loc.__setitem__((0, "class_name"), "unknown_fault"))
    with pytest.raises(ValueError, match="unknown published"):
        load_generated_dataset(toy_bundle)
    change_table(toy_bundle, "targets", lambda frame: frame.loc.__setitem__((0, "class_name"), FAULT_CLASSES[0]))
    change_table(toy_bundle, "segments", lambda frame: frame.loc.__setitem__((0, "chemistry"), "unknown_chemistry"))
    with pytest.raises(ValueError, match="identity mismatch"):
        load_generated_dataset(toy_bundle)


def test_safe_tree_reload_and_calibration_only_use_legal_splits(toy_bundle):
    data = load_generated_dataset(toy_bundle)
    train = data.subset("train").query("chemistry == 'LFP'")
    model = NumericalGBDT.fit(train, seed=0, n_estimators=2, min_samples_leaf=1)
    reloaded = NumericalGBDT(json.loads(json.dumps(model.to_dict())))
    assert np.array_equal(model.predict_proba(train), reloaded.predict_proba(train))
    assert np.allclose(model.predict_proba(train).sum(axis=1), 1)
    assert set(model.to_dict()) == {"kind", "class_names", "feature_names", "medians", "initial", "learning_rate", "trees"}
    with pytest.raises(ValueError, match="only frozen train"):
        NumericalGBDT.fit(data.subset("dev"), n_estimators=1)
    with pytest.raises(ValueError, match="only isolated calibration"):
        fit_temperature(model, data.subset("dev"))
    calibrated = fit_temperature(model, data.subset("calibration").query("chemistry == 'LFP'"))
    assert calibrated["fit_split"] == "calibration"
    assert calibrated["independent_vins"] == 8
    assert not set(calibrated["root_scenario_ids"]) & set(train["root_scenario_id"])
    assert "no population calibration claim" in calibrated["limitation"]


def test_tree_loader_rejects_cycle_nonfinite_and_invalid_feature(toy_bundle):
    train = load_generated_dataset(toy_bundle).subset("train").query("chemistry == 'LFP'")
    recipe = NumericalGBDT.fit(train, n_estimators=1, min_samples_leaf=1).to_dict()
    cyclic = json.loads(json.dumps(recipe))
    cyclic["trees"][0][0]["left"][0] = 0
    with pytest.raises(ValueError, match="cycles"):
        NumericalGBDT(cyclic)
    invalid = json.loads(json.dumps(recipe))
    invalid["trees"][0][0]["feature"][0] = 10_000
    with pytest.raises(ValueError, match="out of bounds"):
        NumericalGBDT(invalid)
    invalid = json.loads(json.dumps(recipe))
    invalid["medians"][0] = float("nan")
    with pytest.raises(ValueError):
        NumericalGBDT(invalid)
    for field in ("threshold", "value"):
        invalid = json.loads(json.dumps(recipe))
        invalid["trees"][0][0][field][0] = "0.1"
        with pytest.raises(ValueError, match="JSON numbers"):
            NumericalGBDT(invalid)


def test_landmarks_and_missing_classes_do_not_inflate_independent_support(toy_bundle):
    data = load_generated_dataset(toy_bundle)
    rows = data.subset("dev").query("chemistry == 'LFP'")
    later = rows.copy()
    later["cycle_index"] = 2
    later["segment_id"] += ":later"
    landmarks = first_landmarks(pd.concat([later, rows], ignore_index=True))
    assert len(landmarks) == 8 and landmarks["cycle_index"].eq(1).all()
    # Match actual CH dev's absent high-resistance class: report AP as null.
    subset = landmarks.loc[landmarks["label"].ne(0)]
    probability = np.full((len(subset), 4), .1)
    probability[np.arange(len(subset)), subset["label"].to_numpy()] = .7
    metrics = multiclass_metrics(subset, probability)
    assert metrics["macro_auprc"] == 1
    assert metrics["macro_auprc_all_four_classes"] is None
    assert metrics["evaluable_class_count"] == 3
    assert metrics["per_class"]["high_resistance"]["auprc"] is None
    assert metrics["per_class"]["high_resistance"]["positive_VINs"] == 0
    assert all(r["small_positive_support"] for r in metrics["per_class"].values())
    assert "accuracy" not in metrics
    with pytest.raises(ValueError, match="one independent"):
        multiclass_metrics(pd.concat([subset, subset]), np.vstack([probability, probability]))


def test_per_chemistry_export_pools_same_root_and_preserves_exploratory_status(toy_bundle):
    data = load_generated_dataset(toy_bundle)
    recipe = train_chemistry_models(data, seed=1, n_estimators=2, min_samples_leaf=1)
    report, predictions = evaluate_generated_split(data, json.loads(json.dumps(recipe)), "dev")
    assert len(predictions) == 16
    assert report["LFP"]["independent_vins"] == report["NCM"]["independent_vins"] == 8
    assert report["pooled_conservative_VIN"]["independent_vins"] == 8
    assert report["pooled_conservative_VIN"]["macro_auprc_all_four_classes"] is not None
    assert recipe["namespace"] == "demo_synthetic" and recipe["origin"] == "public_generated"
    assert recipe["evidence_status"] == "exploratory_generated_only"
    assert "mother" in LIMITATION and "real-fleet" in LIMITATION
    with pytest.raises(ValueError, match="sealed"):
        evaluate_generated_split(data, recipe, "final")
    other = load_generated_dataset(toy_bundle, allow_exploratory_final=True)
    final_report, _ = evaluate_generated_split(other, recipe, "final")
    assert "exploratory final" in final_report["final_policy"]
    assert final_report["pooled_conservative_VIN"]["evidence_status"] == "exploratory_generated_only"


def test_train_only_imputation_and_empty_calibration_status(toy_bundle):
    data = load_generated_dataset(toy_bundle)
    train = data.subset("train").query("chemistry == 'LFP'").copy()
    train[FEATURE_NAMES[0]] = np.nan
    model = NumericalGBDT.fit(train, n_estimators=1, min_samples_leaf=1)
    assert model.to_dict()["medians"][0] == 0
    # Availability is explicit; identity temperature is not a fitted calibrator.
    absent = fit_temperature(model, data.subset("calibration").iloc[:0])
    assert absent["status"] == "unavailable" and absent["temperature"] == 1


def test_ece_counts_boundary_probabilities_once():
    from model_lab.modeling.v2.generated_fault import _binary_ece
    assert _binary_ece(np.array([0., .3, 1.]), np.array([0., 1., 1.])) == pytest.approx(.7 / 3)


def test_cli_three_toy_seeds_default_final_gate_and_json_outputs(toy_bundle, tmp_path, capsys):
    import yaml
    from model_lab.scripts.v2.benchmark_generated import main
    config = tmp_path / "toy.yaml"
    output = tmp_path / "result"
    config.write_text(yaml.safe_dump({"dataset_manifest": str(toy_bundle), "output_dir": str(output), "namespace": "demo_synthetic", "origin": "public_generated", "seeds": [0, 1, 2], "gbdt": {"n_estimators": 1, "min_samples_leaf": 1}}))
    assert main(["--config", str(config)]) == 0
    summary = json.loads((output / "summary.json").read_text())
    assert summary["seeds"] == [0, 1, 2]
    assert summary["final_status"] == "sealed_not_scored"
    assert set(summary["aggregate_metrics"]) == {"train", "dev"}
    assert "final" not in summary["counts"]
    assert len(summary["runs"]) == 3
    assert "std_across_seeds" in summary["aggregate_metrics"]["dev"]["pooled_conservative_VIN"]["macro_auprc"]
    assert len(capsys.readouterr().out.strip().splitlines()) == 4
    for seed in (0, 1, 2):
        prediction = json.loads((output / f"seed{seed}" / "landmark_predictions.json").read_text())
        assert set(prediction) == {"train", "dev"}
        assert (output / f"seed{seed}" / "model.json").exists()
