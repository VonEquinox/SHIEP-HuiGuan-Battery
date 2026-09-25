"""Audit every distinct NASA MAT cell before any external model prediction."""
from __future__ import annotations

import csv
import gc
import hashlib
import io
import json
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from model_lab.data.nasa_pcoe import PARSER_VERSION, archive_inventory, first_eligible_reference, pair_operations
from model_lab.scripts.train_nested_cv import ROOT, digest


ARCHIVE = ROOT / "data/raw/nasa_pcoe/battery_data_set.zip"
SOURCE_RECORD = ROOT / "data/raw/nasa_pcoe/source_record.json"
OUT = ROOT / "reports/round3/nasa_audit"


def source_check() -> dict:
    record = json.loads(SOURCE_RECORD.read_text())
    actual = digest(ARCHIVE)
    if actual != record["sha256"] or ARCHIVE.stat().st_size != record["bytes"]:
        raise ValueError("NASA archive identity mismatch")
    return {"archive_sha256": actual, "archive_bytes": ARCHIVE.stat().st_size,
            "source_record_sha256": digest(SOURCE_RECORD)}


def parse_cell(raw: bytes, cell_id: str):
    mat = loadmat(io.BytesIO(raw), simplify_cells=True)
    keys = [key for key in mat if key.upper() == cell_id]
    if len(keys) != 1:
        raise ValueError(f"MAT cell variable does not match {cell_id}: {keys}")
    operations = mat[keys[0]]["cycle"]
    if isinstance(operations, dict):
        operations = [operations]
    if not isinstance(operations, (list, np.ndarray)):
        raise ValueError("invalid MAT operation array")
    return pair_operations(list(operations))


def main() -> None:
    start = time.monotonic()
    if OUT.exists():
        raise FileExistsError(f"preserve previous NASA audit: {OUT}")
    identity = source_check()
    inventory = archive_inventory(ARCHIVE)
    first = {cell: copies[0] for cell, copies in inventory["cells"].items()}
    by_archive = defaultdict(list)
    for cell, entry in first.items():
        by_archive[entry["archive"]].append((cell, entry))
    OUT.mkdir(parents=True)
    (OUT / "inventory.json").write_text(json.dumps({**identity, **inventory}, indent=2) + "\n")
    operation_rows = []; pair_rows = []; scored = []; failed_cells = []
    cell_summary = []; counts = Counter()
    with zipfile.ZipFile(ARCHIVE) as outer:
        for parent in outer.infolist():
            if parent.filename not in by_archive:
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(parent))) as nested:
                for cell, entry in sorted(by_archive[parent.filename]):
                    tick = time.monotonic()
                    try:
                        raw = nested.read(entry["member"])
                        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                            raise ValueError("MAT member identity changed after inventory")
                        operations, pairs = parse_cell(raw, cell)
                        del raw
                        for row in operations:
                            operation_rows.append({"cell": cell, "archive": parent.filename,
                                                   "source_sha256": entry["sha256"], **row})
                        counts.update(row["type"] for row in operations)
                        reference = None; accepted = 0
                        reference_candidate = first_eligible_reference(pairs)
                        for pair in pairs:
                            charge = pair["charge"]; label = pair["label"]
                            row = {"cell": cell, "archive": parent.filename,
                                   "source_sha256": entry["sha256"],
                                   "charge_operation_index": charge["index"],
                                   "discharge_operation_index": pair["discharge_index"],
                                   "discharge_start_utc": pair["discharge_start"].isoformat(),
                                   "charge_start_utc": charge["start"].isoformat(),
                                   "charge_cutoff_source_index": charge["audit"]["source_end_index"],
                                   "charge_window_Ah": charge["charge_Ah"],
                                   "charge_temperature_missing": charge["audit"]["temperature_missing_in_prefix"],
                                   **label}
                            if label["status"] != "integrated_2p7":
                                row["pair_role"] = "excluded_nonstandard_capacity"
                            elif reference is None:
                                if pair is not reference_candidate:
                                    raise ValueError("noncausal reference choice")
                                reference = pair
                                row["pair_role"] = "initial_reference"
                                row["reference_discharge_operation_index"] = pair["discharge_index"]
                            else:
                                q_ref = reference["label"]["integrated_2p7_Ah"]
                                q_current = label["integrated_2p7_Ah"]
                                window_ref = reference["charge"]["charge_Ah"]
                                ratio = np.log(charge["charge_Ah"] / window_ref)
                                target = q_current / q_ref
                                if not (np.isfinite(ratio) and np.isfinite(target) and target > 0):
                                    row["pair_role"] = "excluded_invalid_ratio"
                                else:
                                    row["pair_role"] = "scored_external_candidate"
                                    row["reference_discharge_operation_index"] = reference["discharge_index"]
                                    row["reference_charge_operation_index"] = reference["charge"]["index"]
                                    row["reference_capacity_integrated_2p7_Ah"] = q_ref
                                    row["true_soh_integrated_2p7"] = target
                                    row["view_row"] = len(scored)
                                    scored.append({"x": charge["view"], "reference": reference["charge"]["view"],
                                                   "log_ratio": ratio, "soh": target, "cell": cell,
                                                   "charge_operation_index": charge["index"],
                                                   "discharge_operation_index": pair["discharge_index"]})
                                    accepted += 1
                            pair_rows.append(row)
                        statuses = Counter(row["status"] for row in operations)
                        cell_summary.append({"cell": cell, "source_sha256": entry["sha256"],
                                             "archives": [copy["archive"] for copy in inventory["cells"][cell]],
                                             "operations": len(operations), "pairs": len(pairs),
                                             "reference_discharge_operation_index":
                                                 reference["discharge_index"] if reference else None,
                                             "scored_candidates": accepted,
                                             "operation_statuses": dict(statuses),
                                             "seconds": time.monotonic()-tick})
                        print(f"NASA {len(cell_summary)}/{inventory['distinct_cells']} {cell}: "
                              f"operations={len(operations)} pairs={len(pairs)} scored={accepted}", flush=True)
                        del operations, pairs
                        gc.collect()
                    except Exception as error:
                        failed_cells.append({"cell": cell, "archive": parent.filename,
                                             "error": repr(error)})
                        print(f"NASA ERROR {cell}: {error!r}", flush=True)
    with (OUT / "operations.csv").open("w", newline="") as stream:
        fields = sorted({key for row in operation_rows for key in row})
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(operation_rows)
    (OUT / "pairs.json").write_text(json.dumps(pair_rows, indent=2) + "\n")
    if scored:
        np.savez_compressed(OUT / "view.npz",
            x=np.stack([row["x"] for row in scored]),
            reference=np.stack([row["reference"] for row in scored]),
            log_window_ratio=np.array([row["log_ratio"] for row in scored], dtype=np.float32),
            true_soh=np.array([row["soh"] for row in scored], dtype=np.float64),
            cell=np.array([row["cell"] for row in scored]),
            charge_operation_index=np.array([row["charge_operation_index"] for row in scored]),
            discharge_operation_index=np.array([row["discharge_operation_index"] for row in scored]))
    summary_mismatch = [abs(row["summary_minus_2p7_relative"]) for row in pair_rows
                        if row.get("summary_minus_2p7_relative") is not None]
    report = {**identity, "parser_version": PARSER_VERSION, "parser_sha256": digest(ROOT / "data/nasa_pcoe.py"),
              "protocol_sha256": digest(ROOT / "docs/ROUND3_EXTERNAL_PROTOCOL.md"),
              "mat_members": inventory["mat_members"], "distinct_cells": inventory["distinct_cells"],
              "duplicate_cells": sorted(inventory["duplicate_cells"]),
              "duplicate_member_count": inventory["mat_members"]-inventory["distinct_cells"],
              "parsed_cells": len(cell_summary), "failed_cells": failed_cells,
              "operations": len(operation_rows), "operation_types": dict(counts),
              "operation_statuses": dict(Counter(row["status"] for row in operation_rows)),
              "paired_discharges": len(pair_rows),
              "pair_roles": dict(Counter(row["pair_role"] for row in pair_rows)),
              "capacity_statuses": dict(Counter(row["status"] for row in pair_rows)),
              "scored_candidate_rows": len(scored),
              "scored_candidate_cells": len({row["cell"] for row in scored}),
              "summary_vs_integrated_2p7_abs_rel_quantiles":
                  np.quantile(summary_mismatch, [0,.5,.9,.95,.99,1]).tolist() if summary_mismatch else None,
              "summary_vs_integrated_2p7_over_5pct": sum(v > .05 for v in summary_mismatch),
              "cell_summary": cell_summary, "elapsed_seconds": time.monotonic()-start,
              "external_scoring_gate_candidate": not failed_cells and len({row["cell"] for row in scored}) >= 2}
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("cell_summary",)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
