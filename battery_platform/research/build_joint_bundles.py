"""Build immutable XJTU-only and XJTU+MATR benchmark bundles.

The source bundles under model_lab/data/derived are read-only inputs.  This
script writes new filtered/combined bundles under the battery_platform
research directory so that development runs never load final rows.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from model_lab.modeling.v2.contracts import load_dataset, sha256_file
from model_lab.modeling.v2.features import combine_feature_bundles


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "battery_platform" / "research" / "joint_xjtu_matr" / "bundles"
XJTU = ROOT / "model_lab" / "data" / "derived" / "v2" / "xjtu_features_final" / "features.json"
MATR = ROOT / "model_lab" / "data" / "derived" / "v2" / "matr_features_v2" / "features.json"


def write_subset(source: Path, destination: Path, allowed_splits: set[str]) -> Path:
    if (destination / "features.json").exists():
        raise FileExistsError(f"immutable bundle exists: {destination}")
    manifest, arrays = load_dataset(source)
    indices = [i for i, row in enumerate(manifest["rows"]) if row["split"] in allowed_splits]
    if not indices:
        raise ValueError(f"no rows retained from {source}")
    destination.mkdir(parents=True, exist_ok=False)
    subset_manifest = copy.deepcopy(manifest)
    subset_manifest["rows"] = [manifest["rows"][i] for i in indices]
    subset_manifest["source_manifest_sha256"] = sha256_file(source)
    subset_arrays = {key: value[np.asarray(indices)] for key, value in arrays.items()}
    np.savez_compressed(destination / "features.npz", **subset_arrays)
    subset_manifest["arrays_file"] = "features.npz"
    subset_manifest["arrays_sha256"] = sha256_file(destination / "features.npz")
    subset_manifest["subset_policy"] = {
        "source": str(source),
        "allowed_splits": sorted(allowed_splits),
        "final_rows_loaded": "final" in allowed_splits,
    }
    (destination / "features.json").write_text(
        json.dumps(subset_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    return destination / "features.json"


def build_pair(name: str, allowed_splits: set[str]) -> dict:
    root = OUT / name
    if root.exists():
        raise FileExistsError(f"immutable experiment bundle exists: {root}")
    root.mkdir(parents=True)
    xjtu_path = write_subset(XJTU, root / "xjtu", allowed_splits)
    matr_path = write_subset(MATR, root / "matr", allowed_splits)
    combined_path = root / "combined"
    combined = combine_feature_bundles([xjtu_path, matr_path], combined_path)
    receipt = {
        "name": name,
        "allowed_splits": sorted(allowed_splits),
        "source_manifests": [str(XJTU), str(MATR)],
        "source_manifest_sha256": [sha256_file(XJTU), sha256_file(MATR)],
        "combined_manifest": str(combined_path / "features.json"),
        "combined_manifest_sha256": sha256_file(combined_path / "features.json"),
        "combined_arrays_sha256": sha256_file(combined_path / "features.npz"),
        "rows": len(combined["rows"]),
        "objects": len({row["physical_cell_id"] for row in combined["rows"]}),
        "source_split_rows": {},
    }
    for row in combined["rows"]:
        receipt["source_split_rows"].setdefault(row["source_id"], {}).setdefault(row["split"], 0)
        receipt["source_split_rows"][row["source_id"]][row["split"]] += 1
    (root / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dev = build_pair("development", {"train", "dev", "calibration"})
    final = build_pair("final_comparison", {"train", "dev", "calibration", "final"})
    print(json.dumps({"development": dev, "final_comparison": final}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
