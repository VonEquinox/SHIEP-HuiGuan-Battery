"""Prepare immutable official V2 subsets without fitting or evaluating models.

Paths are resolved against the working directory. Help and --dry-list never
open measurement files. Fetch raw originals separately with the ingest CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
KINDS = {"matr-summary": "matr", "matr-csv": "matr", "matr-corrected": "matr", "dyad": "dyad", "ch": "ch_batterygen"}


def _file(value: str | None, name: str) -> Path:
    if not value:
        raise ValueError(f"missing --{name}")
    declared = Path(value)
    path = declared.resolve()
    if not path.is_file() or declared.is_symlink():
        raise FileNotFoundError(f"required original/metadata file unavailable: {path}")
    return path


def _new_output(value: str | None, name: str) -> Path:
    if not value:
        raise ValueError(f"missing --{name}")
    path = Path(value).resolve()
    if path.exists():
        raise FileExistsError(f"immutable output already exists; select a new --{name}: {path}")
    if not any(path.parts[i:i + 3] == ("data", "derived", "v2") for i in range(len(path.parts) - 2)):
        raise ValueError(f"--{name} must be a new directory under data/derived/v2")
    return path


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _identity_from_ch(paths: list[Path]):
    import pandas as pd
    rows = []
    for path in paths:
        chemistry, category, vin = path.parts[-4:-1]
        if chemistry not in {"LFP", "NCM"} or category not in {"normal", "high_resistance", "low_capacity", "self_discharge"} or not vin.startswith("vin_"):
            raise ValueError("CH paths must preserve chemistry/fault/VIN/file.csv release layout")
        rows.append({"physical_cell_id": f"ch_batterygen:{chemistry}:{category}:{vin}", "root_scenario_id": f"ch_batterygen:conservative-{vin}"})
    return pd.DataFrame(rows).drop_duplicates("physical_cell_id")


def _ch_paths(root: Path, selection: Path) -> list[Path]:
    payload = _json(selection)
    entries = payload.get("selected") if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not 0 < len(entries) <= 512:
        raise ValueError("CH selection must explicitly list 1..512 original CSV paths")
    paths = []
    for entry in entries:
        relative = Path(entry["path"] if isinstance(entry, dict) else entry)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".csv":
            raise ValueError("unsafe or non-CSV CH selection entry")
        path = _file(str(root / relative), "csv-root/selection-json")
        if not path.is_relative_to(root.resolve()):
            raise ValueError("CH selection escapes CSV root")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate CH selected path")
    return sorted(paths)


def _verify_original(path: Path, *, sha256: str | None = None, md5: str | None = None) -> dict[str, Any]:
    if path.stat().st_size > 4 * 1024**3:
        raise ValueError("original exceeds 4 GiB preparation budget")
    sha, md = hashlib.sha256(), hashlib.md5() if md5 else None
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            sha.update(chunk)
            if md is not None:
                md.update(chunk)
    actual = sha.hexdigest()
    if sha256 and actual.lower() != sha256.lower():
        raise ValueError("original failed saved official-download SHA256")
    if md5 and md.hexdigest().lower() != md5.lower():
        raise ValueError("original failed official author MD5")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual, "author_md5": md5, "author_md5_verified": bool(md5), "saved_download_sha256_verified": bool(sha256)}


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Check prerequisites, freeze IDs before numeric parsing, export, audit."""
    if args.dry_list:
        return {"status": "dry_list_no_measurements_opened", "kind": args.kind, "source_id": KINDS[args.kind], "options": {key: value for key, value in vars(args).items() if value is not None}, "fits_or_scores_models": False}
    output = _new_output(args.out, "out")
    registry_path = _file(args.source_registry, "source-registry")
    from model_lab.modeling.v2.data import audit_manifest, freeze_group_split, parse_ch_csvs, parse_matr_csv, parse_matr_official, parse_table, write_json
    from model_lab.modeling.v2.sources import convert_dyad_archive, get_local_registry
    import pandas as pd

    source = next((row for row in get_local_registry(registry_path) if row["source_id"] == KINDS[args.kind]), None)
    if source is None or source.get("license_status") in {None, "unverified"}:
        raise ValueError("declared official source and license record required")
    raw_receipts = {row["original_filename"]: row for row in source.get("raw_receipts", [])}
    receipts: list[dict[str, Any]] = []
    conversion = None

    if args.kind == "matr-summary":
        tests = _file(args.tests_json, "tests-json")
        candidates = [row for row in _json(tests) if row.get("cellId") and row.get("name", "").startswith("2018-04-12_")]
        candidates = sorted(candidates, key=lambda row: hashlib.sha256(str(row["cellId"]).encode()).hexdigest())[:args.max_cells]
        identity = pd.DataFrame({"physical_cell_id": [f"matr:{row['cellId']}" for row in candidates]})
        if identity.empty or identity.physical_cell_id.duplicated().any():
            raise ValueError("eligible distinct 2018 original barcodes required")
        split = freeze_group_split(identity, ratios=(.5, 1/6, 1/6, 1/6))
        receipts.append(_verify_original(tests))
    elif args.kind == "matr-csv":
        csv = _file(args.csv, "csv")
        metadata = _file(args.metadata_json, "metadata-json")
        payload = _json(metadata)
        if isinstance(payload, list):
            matches = [row for row in payload if row.get("name") == csv.stem]
            if len(matches) != 1:
                raise ValueError("CSV basename must match exactly one original official test")
            test = matches[0]
        else:
            test = payload.get("source_test", payload)
        if not test.get("cellId") or test.get("name") != csv.stem or not test.get("dataFileId"):
            raise ValueError("original CSV name, barcode and official dataFileId required")
        split = freeze_group_split(pd.DataFrame({"physical_cell_id": [f"matr:{test['cellId']}"]}))
        saved_sha = raw_receipts.get(csv.name, {}).get("sha256")
        if isinstance(payload, dict):
            saved_sha = saved_sha or payload.get("sha256")
        receipts.extend([_verify_original(csv, sha256=saved_sha), _verify_original(metadata)])
    elif args.kind == "matr-corrected":
        from model_lab.modeling.v2.matr_stream import inventory_matr_hdf5, inventory_identity_frame
        if not args.mat_files or len(args.mat_files) != 3 or not args.batch_tests_json or len(args.batch_tests_json) != 3:
            raise ValueError("matr-corrected needs all three --mat-files and --batch-tests-json")
        if args.max_segments > 32:
            raise ValueError("corrected streaming parser permits at most 32 original curves per physical cell")
        paths = [_file(path, "mat-files") for path in args.mat_files]
        metadata_paths = [_file(path, "batch-tests-json") for path in args.batch_tests_json]
        for path in paths:
            saved = raw_receipts.get(path.name, {}).get("sha256")
            if not saved:
                raise ValueError("corrected original requires a verified official-download receipt in source registry")
            receipts.append(_verify_original(path, sha256=saved))
        inventory = inventory_matr_hdf5(paths, raw_sha256={row["path"]: row["sha256"] for row in receipts})
        official_tests = {}
        for metadata_path in metadata_paths:
            for row in _json(metadata_path):
                official_tests[(row["name"][:10], str(row["cellId"]).strip().casefold())] = row
            receipts.append(_verify_original(metadata_path))
        for row in inventory["records"]:
            official_test = official_tests.get((row["batch_id"], row["source_identity"]))
            if official_test is None or str(official_test.get("channel")) != str(row["original_channel"]):
                raise ValueError("original MAT barcode/channel disagrees with official test metadata")
            row.update(barcode_verified=True, original_channel_verified=True)
        split = freeze_group_split(inventory_identity_frame(inventory), ratios=(.6, .2, .2, 0.))
        split["final_policy"] = "development_only_no_final_objects_or_scoring"
    elif args.kind == "dyad":
        archive = _file(args.archive, "archive")
        labels = _file(args.labels_csv, "labels-csv")
        official = _file(args.official_record, "official-record")
        numeric_output = _new_output(args.numeric_out, "numeric-out")
        if output == numeric_output or output.is_relative_to(numeric_output) or numeric_output.is_relative_to(output):
            raise ValueError("numeric-out and out must be separate immutable directories")
        files = [row for row in _json(official).get("files", []) if row.get("name") == archive.name]
        if len(files) != 1 or not files[0].get("computed_md5"):
            raise ValueError("archive must match actual Figshare file metadata with author MD5")
        vehicles = pd.read_csv(labels, usecols=["car"])
        if vehicles.empty or vehicles.car.isna().any() or vehicles.car.duplicated().any():
            raise ValueError("original unique vehicle IDs required before numeric conversion")
        identity = pd.DataFrame({"physical_cell_id": vehicles.car.astype(int).map(lambda value: f"dyad:brand3:vehicle-{value}")})
        split = freeze_group_split(identity)
        receipts.extend([_verify_original(archive, sha256=raw_receipts.get(archive.name, {}).get("sha256"), md5=files[0]["computed_md5"]), _verify_original(labels), _verify_original(official)])
    else:
        archive = _file(args.archive, "archive")
        selection = _file(args.selection_json, "selection-json")
        if not args.csv_root or not Path(args.csv_root).is_dir():
            raise FileNotFoundError("--csv-root must contain already extracted original CSVs")
        paths = _ch_paths(Path(args.csv_root).resolve(), selection)
        identity = _identity_from_ch(paths)
        root_split = freeze_group_split(identity[["root_scenario_id"]].drop_duplicates(), group_column="root_scenario_id")
        split = {**root_split, "assignments": {row.physical_cell_id: root_split["assignments"][row.root_scenario_id] for row in identity.itertuples()}, "root_assignments": root_split["assignments"], "independent_root_count": identity.root_scenario_id.nunique(), "generation_parent_overlap": "unavailable_original_generator_mother_ids_not_published", "final_benchmark_eligibility": "exploratory_only_mother_overlap_unknown"}
        receipts.extend([_verify_original(archive, sha256=raw_receipts.get(archive.name, {}).get("sha256")), _verify_original(selection)])

    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "preparse_split_manifest.json", split)
    if args.kind == "matr-corrected":
        write_json(output / "identity_inventory.json", inventory)
    if args.kind == "matr-summary":
        dataset, parsed_split = parse_matr_official(tests, max_cells=args.max_cells, reference_ordinal=args.reference_ordinal, query_stride=args.query_stride)
        if parsed_split["assignments"] != split["assignments"]:
            raise ValueError("parser identity split differs from frozen preparse split")
    elif args.kind == "matr-csv":
        dataset = parse_matr_csv(csv, test, max_segments=args.max_segments)
    elif args.kind == "matr-corrected":
        from model_lab.modeling.v2.matr_stream import parse_matr_hdf5
        dataset = parse_matr_hdf5(paths, inventory, max_segments_per_cell=args.max_segments)
    elif args.kind == "dyad":
        conversion = convert_dyad_archive(archive, numeric_output, max_per_vehicle=args.max_per_vehicle)
        dataset = parse_table(conversion["table_path"], {"source_id": "dyad", "origin": "real_operational", "group_column": "physical_cell_id", "label_column": "fault_label", "label_only_columns": ["original_snippet_label"], "target_definition_id": "dyad-original-retrospective-vehicle-anomaly-v2", "sensor_level": "vehicle", "protocol_id": "vehicle_charging"})
    else:
        dataset, parsed_split = parse_ch_csvs(paths, archive_ref=str(archive))
        if parsed_split["assignments"] != split["assignments"]:
            raise ValueError("parser VIN groups differ from frozen preparse split")
    if not set(dataset.identity_map.physical_cell_id) <= set(split["assignments"]):
        raise ValueError("numeric parser introduced an unfrozen object")
    manifest = dataset.write(output, split)
    audit = audit_manifest(output / "manifest.json")
    write_json(output / "audit.json", audit)
    receipt = {"schema_version": "official-subset-preparation-v2", "status": "parsed" if audit["passed"] else "audit_failed", "kind": args.kind, "source_id": KINDS[args.kind], "source_registry": str(registry_path), "landing_url": source["landing_url"], "license_status": source["license_status"], "raw_inputs": receipts, "numeric_conversion": conversion, "manifest_path": str(output / "manifest.json"), "namespace": manifest["namespace"], "split_frozen_before_numeric_parse": True, "counts": {name: info["rows"] for name, info in manifest["tables"].items()}, "audit": audit, "fits_or_scores_models": False}
    write_json(output / "preparation_receipt.json", receipt)
    if not audit["passed"]:
        raise ValueError("official subset failed audit: " + "; ".join(audit["failures"]))
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=tuple(KINDS))
    parser.add_argument("--out", help="new immutable data/derived/v2 directory")
    parser.add_argument("--source-registry", default=str(ROOT / "reports/v2/sources/source_registry.yaml"))
    parser.add_argument("--dry-list", action="store_true", help="print declared inputs only; do not open measurements or write output")
    for name in ("tests-json", "csv", "metadata-json", "archive", "labels-csv", "official-record", "numeric-out", "csv-root", "selection-json"):
        parser.add_argument("--" + name)
    parser.add_argument("--mat-files", nargs="+", help="all three official corrected MATLAB files")
    parser.add_argument("--batch-tests-json", nargs="+", help="official tests JSON for all three batches, for independent barcode/channel verification")
    for name, default in (("max-cells", 36), ("reference-ordinal", 10), ("query-stride", 10), ("max-segments", 32), ("max-per-vehicle", 8)):
        parser.add_argument("--" + name, type=int, default=default)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if any(getattr(args, name) <= 0 for name in ("max_cells", "reference_ordinal", "query_stride", "max_segments", "max_per_vehicle")) or args.max_cells > 128 or args.max_segments > 128 or args.max_per_vehicle > 32:
        parser.error("positive bounded limits required: cells/segments <=128, per-vehicle <=32")
    try:
        receipt = prepare(args)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
