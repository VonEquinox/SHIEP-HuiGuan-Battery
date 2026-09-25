"""One-pass zero-shot NASA stress test of the frozen XJTU ET champion."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from model_lab.modeling.frozen_et import load_champion, outside_training_range, predict_soh
from model_lab.scripts.train_nested_cv import ROOT, digest


AUDIT = ROOT / "reports/round3/nasa_audit"
CHAMPION = ROOT / "reports/round3/champion_v3/et_champion.joblib"
OUT = ROOT / "reports/round3/nasa_transfer"


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"preserve previous transfer result: {OUT}")
    audit = json.loads((AUDIT / "summary.json").read_text())
    if not audit["external_scoring_gate_candidate"] or audit["failed_cells"]:
        raise ValueError("raw NASA audit gate not passed")
    if audit["parser_sha256"] != digest(ROOT / "data/nasa_pcoe.py"):
        raise ValueError("NASA parser changed after audit")
    if audit["protocol_sha256"] != digest(ROOT / "docs/ROUND3_EXTERNAL_PROTOCOL.md"):
        raise ValueError("external protocol changed after audit")
    champion_manifest = json.loads((CHAMPION.parent / "manifest.json").read_text())
    if champion_manifest["artifact_sha256"] != digest(CHAMPION):
        raise ValueError("frozen champion changed")
    if champion_manifest["source_hashes"]["external_protocol"] != audit["protocol_sha256"]:
        raise ValueError("champion/protocol mismatch")
    artifact = load_champion(CHAMPION)
    with np.load(AUDIT / "view.npz", allow_pickle=False) as data:
        x = data["x"]; reference = data["reference"]; ratio = data["log_window_ratio"]
        cells = data["cell"].astype(str)
        charges = data["charge_operation_index"]
        discharges = data["discharge_operation_index"]
        # All scoring decisions and prediction values are fixed before truth is opened.
        predicted = predict_soh(x, reference, ratio, artifact)
        shift = outside_training_range(x, reference, ratio, artifact)
        truth = data["true_soh"]
    if len(predicted) != audit["scored_candidate_rows"] or not np.isfinite(truth).all():
        raise ValueError("audit view/label row contract changed")
    pairs = json.loads((AUDIT / "pairs.json").read_text())
    metadata = {int(row["view_row"]): row for row in pairs if row["pair_role"] == "scored_external_candidate"}
    if set(metadata) != set(range(len(predicted))):
        raise ValueError("prediction lineage is incomplete")
    rows = []; per_cell = defaultdict(list); per_archive = defaultdict(set)
    for index, (cell, charge, discharge, y, p) in enumerate(zip(cells, charges, discharges, truth, predicted)):
        source = metadata[index]
        if source["cell"] != cell or source["charge_operation_index"] != int(charge) or source["discharge_operation_index"] != int(discharge):
            raise ValueError("source operation alignment changed")
        error = float((p-y)*100.)
        row = {"view_row": index, "cell": cell, "archive": source["archive"],
               "source_sha256": source["source_sha256"],
               "charge_operation_index": int(charge), "discharge_operation_index": int(discharge),
               "reference_charge_operation_index": source["reference_charge_operation_index"],
               "reference_discharge_operation_index": source["reference_discharge_operation_index"],
               "charge_cutoff_source_index": source["charge_cutoff_source_index"],
               "label_provenance": "integrated_negative_current_to_first_2p7V",
               "true_soh": float(y), "pred_soh": float(p), "error_pp": error,
               "abs_error_pp": abs(error)}
        rows.append(row); per_cell[cell].append(abs(error)); per_archive[source["archive"]].add(cell)
    cell_scores = [{"cell": cell, "n": len(errors), "mae_pp": float(np.mean(errors))}
                   for cell, errors in sorted(per_cell.items())]
    archive_scores = {}
    for archive, archive_cells in sorted(per_archive.items()):
        archive_scores[archive] = {"cells": len(archive_cells),
            "cell_mae_pp": float(np.mean([np.mean(per_cell[cell]) for cell in archive_cells]))}
    report = {"scope": "NASA source/protocol transfer stress test, zero-shot; not same-benchmark SOTA",
              "task": "2.7V integrated NASA operational discharge relative to first eligible calibration",
              "archive_sha256": audit["archive_sha256"],
              "raw_audit_sha256": digest(AUDIT / "summary.json"),
              "audit_view_sha256": digest(AUDIT / "view.npz"),
              "frozen_champion_sha256": digest(CHAMPION),
              "scorer_sha256": digest(Path(__file__)),
              "source_cells": audit["distinct_cells"], "eligible_cells": len(cell_scores),
              "eligible_rows": len(rows), "excluded_cells": audit["distinct_cells"]-len(cell_scores),
              "cell_macro_mae_pp": float(np.mean([r["mae_pp"] for r in cell_scores])),
              "pooled_mae_pp": float(np.mean([r["abs_error_pp"] for r in rows])),
              "prediction_range_soh": [float(predicted.min()), float(predicted.max())],
              "truth_range_soh": [float(truth.min()), float(truth.max())],
              "input_outside_training_range": shift,
              "per_cell": cell_scores, "by_source_archive": archive_scores,
              "worst_cells": sorted(cell_scores, key=lambda r: -r["mae_pp"])[:8],
              "audit_pair_roles": audit["pair_roles"],
              "xjtu_heldout_model_scores": False,
              "nasa_fitting_or_threshold_selection": False}
    OUT.mkdir(parents=True)
    with (OUT / "predictions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("per_cell", "by_source_archive", "input_outside_training_range")}, indent=2))


if __name__ == "__main__":
    main()
