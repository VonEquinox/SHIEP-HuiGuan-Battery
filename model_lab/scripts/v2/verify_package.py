"""Replay shipped label-free development inputs without raw data or sklearn pickle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from model_lab.modeling.v2.prediction import load_package
from model_lab.modeling.v2.contracts import sha256_file
from .common import write_json


def compare(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError("profile contract mismatch")
        for key in expected:
            compare(actual[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("profile list mismatch")
        for a, b in zip(actual, expected):
            compare(a, b)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not np.isclose(actual, expected, atol=1e-7, rtol=1e-7):
            raise ValueError("numerical reload mismatch")
    elif actual != expected:
        raise ValueError("profile value mismatch")


def verify(path):
    path = Path(path)
    package = load_package(path)
    if not package.manifest.get("reload_verified"):
        raise ValueError("package was not export-verified")
    samples = [("reload_sample.npz", [json.loads((path / "reload_sample_query.json").read_text())],
                [json.loads((path / "reload_verification.json").read_text())["sample_profile"]])]
    if "reload_domain_samples.npz" in package.manifest["files"]:
        samples.append(("reload_domain_samples.npz", json.loads((path / "reload_domain_queries.json").read_text()),
                        json.loads((path / "reload_domain_profiles.json").read_text())))
    checks = []
    for filename, queries, profiles in samples:
        with np.load(path / filename, allow_pickle=False) as archive:
            if set(archive.files) != {"features", "sequences", "sequence_mask", "domain"}:
                raise ValueError("reload input must be label-free numeric features only")
            arrays = {key: archive[key] for key in archive.files}
        if len(profiles) != len(queries) or any(len(v) != len(queries) for v in arrays.values()):
            raise ValueError("sample and query counts differ")
        for i, (query, expected) in enumerate(zip(queries, profiles)):
            if query.get("split") != "dev":
                raise ValueError("replay examples must come from development split")
            actual = package.predict(query, {key: value[i:i+1] for key, value in arrays.items()})
            compare(actual, expected)
            checks.append({"source_id": query["source_id"], "physical_cell_id": query["physical_cell_id"],
                           "heads": {key: value["support"] for key, value in actual["heads"].items()}})
    return {"package_id": path.name, "manifest_sha256": sha256_file(path / "manifest.json"),
            "model_version": package.model_version, "passed": True, "absolute_tolerance": 1e-7,
            "no_raw_or_final_data_required": True, "samples": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", action="append", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = {"schema_version": "safe-package-replay-v2", "packages": [verify(p) for p in args.package]}
    if args.output:
        if Path(args.output).exists():
            raise ValueError("verification receipt already exists")
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
