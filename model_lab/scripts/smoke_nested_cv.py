"""Tiny synthetic end-to-end smoke; output is not battery-model evidence."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch

from model_lab.scripts.train_nested_cv import (
    DevData, METHODS, OUT, evaluate_method_fold, split_indices,
)


def main() -> None:
    torch.set_num_threads(4)
    out = OUT.parent / "smoke_kernel"
    if out.exists():
        raise FileExistsError(f"fresh synthetic smoke output required: {out}")
    out.mkdir(parents=True)
    rng = np.random.default_rng(2047)
    names = [f"Batch-{batch}/synthetic-{number}" for batch in (4, 5, 6) for number in (1, 2, 3)]
    cell = np.repeat(names, 4)
    batch = np.array([name.split("/")[0] for name in cell])
    reference = np.repeat(rng.normal(size=(len(names), 71)).astype(np.float32), 4, axis=0)
    age = np.tile(np.arange(4), len(names))
    current = reference.copy()
    current[:, 0] += age * .04
    current[:, 1] -= age * .03
    soh = np.exp(-.025 * age + .002 * rng.normal(size=len(cell)))
    data = DevData(current, reference, (-.015 * age).astype(np.float32), soh,
                   cell, batch, np.arange(len(cell)))
    fold = {"train_cells": [name for name in names if not name.endswith("-3")],
            "validation_cells": [name for name in names if name.endswith("-3")]}
    indices = split_indices(data, fold, 0)
    results = []; start = time.monotonic()
    for method in METHODS:
        from model_lab.scripts.train_nested_cv import CONFIGS
        result = evaluate_method_fold(data, method, 0, indices, torch.device("cpu"),
                                      10, 10, out, configs=CONFIGS[method][:1], seeds=(0,))
        results.append({"method": method, "selected": result["selection"],
                        "inner_runs": result["trials"], "outer_refits": result["refits"],
                        "prediction_count": len(result["predictions"]),
                        "failures": result["failures"], "no_result": result["no_result"]})
    report = {"scope": "synthetic smoke only; not XJTU evidence", "device": "cpu",
              "methods": results, "seconds": time.monotonic() - start,
              "all_successful": all(not r["failures"] and r["prediction_count"] == 12 for r in results)}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"all_successful": report["all_successful"],
                      "methods": len(results), "seconds": report["seconds"]}), flush=True)
    if not report["all_successful"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
