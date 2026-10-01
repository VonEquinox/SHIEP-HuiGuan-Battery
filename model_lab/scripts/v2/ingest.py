"""Metadata refresh and immutable V2-only measurement preprocessing."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from model_lab.modeling.v2.data import ParsedDataset, audit_manifest, freeze_group_split, parse_matr_mat, parse_table, parse_xjtu_mat, protected_xjtu_filename, write_json, sha256_file
from model_lab.modeling.v2.sources import DEFAULT_PROXY, SOURCE_DEFINITIONS, download_verified, get_local_registry, refresh_metadata, save_registry, register_raw_receipts, discover_matr_test_file

ROOT = Path(__file__).resolve().parents[2]


def _resolve(path: str | Path, base: Path) -> Path:
    path = Path(path)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def ingest(config: dict[str, Any], source: str, *, config_base: Path = ROOT, metadata_only: bool = False, include_final: bool = False, output_override: str | None = None, download_only: bool = False, file_name: str | None = None) -> dict[str, Any]:
    """Pure orchestration contract usable by an asynchronous worker.

    Network metadata refresh is separate from preprocessing; no formal work
    order, asset identity or training artifact is modified by this function.
    """
    source = "ch_batterygen" if source in {"ch", "ch-batterygen"} else source
    report_dir = _resolve(config.get("source_report_dir", "reports/v2/sources"), config_base)
    registry_path = _resolve(config.get("source_registry", "reports/v2/sources/source_registry.yaml"), config_base)
    if download_only:
        if source not in SOURCE_DEFINITIONS:
            raise ValueError("download one registered source at a time")
        row = refresh_metadata(source, report_dir, proxy=config.get("proxy", DEFAULT_PROXY))
        files = [record for record in row["files"] if file_name is None or record["name"] == file_name]
        if not files and source == "matr" and file_name:
            files = [discover_matr_test_file(file_name, report_dir, proxy=config.get("proxy", DEFAULT_PROXY))]
        if not files:
            raise ValueError("requested file was not resolved from current official metadata")
        raw_output = _resolve(config.get("sources", {}).get(source, {}).get("raw_download_root", f"data/raw/{source}"), config_base)
        raw_output.mkdir(parents=True, exist_ok=True)
        max_bytes = int(config.get("max_download_bytes", 4 * 1024**3))
        reserve = int(config.get("min_free_bytes", 70 * 1024**3))
        receipts = []
        prior_parsed_manifest = row.get("parsed_manifest")
        registry = {entry["source_id"]: entry for entry in get_local_registry(registry_path)}
        registry[source] = {**row, "status": "downloading"}
        save_registry(registry_path, list(registry.values()))
        for record in files:
            if Path(record["name"]).name != record["name"]:
                raise ValueError("unsafe official filename rejected")
            budget = record.get("bytes") or max_bytes
            if shutil.disk_usage(raw_output).free - budget < reserve:
                raise ValueError("download would violate the configured free-disk reserve")
            destination = raw_output / record["name"]
            if destination.exists():
                if record.get("bytes") is not None and destination.stat().st_size != record["bytes"]:
                    raise ValueError("existing raw original size differs from current official metadata")
                checksum = record.get("author_checksum")
                if checksum:
                    import hashlib
                    algorithm, expected = checksum.split(":", 1)
                    digest = hashlib.new(algorithm)
                    with destination.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                    if digest.hexdigest().lower() != expected.lower():
                        raise ValueError("existing raw original failed author checksum")
                receipts.append({"status": "verified_reused_original", "path": str(destination), "original_filename": record["name"], "resolved_download_url": record["url"], "bytes": destination.stat().st_size, "sha256": sha256_file(destination), "author_checksum": checksum})
            else:
                receipts.append(download_verified(record, destination, config.get("proxy", DEFAULT_PROXY), max_bytes=max_bytes))
        register_raw_receipts(source, report_dir, registry_path, receipts, parsed_manifest=prior_parsed_manifest, scope="selected_official_files_verified; existing parsed subset identified separately")
        return {"status": "verified", "source_id": source, "receipts": receipts}
    if metadata_only:
        ids = list(SOURCE_DEFINITIONS) if source == "all" else [source]
        with ThreadPoolExecutor(max_workers=min(4, len(ids))) as executor:
            records = list(executor.map(lambda source_id: refresh_metadata(source_id, report_dir, proxy=config.get("proxy", DEFAULT_PROXY)), ids))
        existing = {row["source_id"]: row for row in get_local_registry(registry_path)}
        existing.update({row["source_id"]: row for row in records})
        save_registry(registry_path, list(existing.values()))
        return {"status": "metadata_refreshed", "registry_path": str(registry_path), "sources": records}
    if source == "all":
        raise ValueError("preprocess one declared source at a time")
    settings = config.get("sources", {}).get(source, {})
    raw_root = _resolve(settings.get("raw_root", f"data/raw/{source}"), config_base)
    output = _resolve(output_override or settings.get("derived_dir", f"data/derived/v2/{source}"), config_base)
    if output.exists() and (output / "manifest.json").exists():
        raise FileExistsError("parsed V2 runs are immutable; select a new --out")
    if source == "xjtu":
        paths = [_resolve(name, raw_root) for name in settings.get("files", [])]
        if not paths:
            paths = sorted(raw_root.glob("Batch-*/*.mat"))
        # Filename-only gates and splits freeze before opening/hash of raw.
        paths = [path for path in paths if not protected_xjtu_filename(path)]
        if not paths:
            raise FileNotFoundError("no eligible XJTU development raw files")
        filenames = pd.DataFrame([{"physical_cell_id": f"xjtu:{path.parent.name}/{path.stem}", "source_id": "xjtu", "source_cell_id": f"{path.parent.name}/{path.stem}", "chemistry": "NCM", "nominal_capacity_Ah": 2., "protocol_id": path.stem.rsplit("-", 1)[0], "batch_id": path.parent.name, "namespace": "experimental"} for path in paths])
        split = freeze_group_split(filenames, seed=config.get("seed", 20261001), ratios=tuple(config.get("split_ratios", (.6, .15, .1, .15))))
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "preparse_split_manifest.json", split)
        datasets, sealed_rows, parse_errors = [], [], []
        for path in paths:
            identity_id = f"xjtu:{path.parent.name}/{path.stem}"
            if split["assignments"][identity_id] == "final" and not include_final:
                identity = filenames[filenames.physical_cell_id == identity_id].copy()
                identity["ingest_status"] = "sealed_filename_only_not_opened"
                sealed_rows.append(identity)
                continue
            try:
                datasets.append(parse_xjtu_mat(path, max_segments=settings.get("max_segments_per_cell", 32)))
            except Exception as exc:
                parse_errors.append({"physical_cell_id": identity_id, "reason": "parser_failed", "error": f"{type(exc).__name__}: {exc}"})
        dataset = ParsedDataset.concat(datasets)
        if sealed_rows:
            dataset.identity_map = pd.concat([dataset.identity_map, *sealed_rows], ignore_index=True)
        if parse_errors:
            dataset.exclusions.extend(parse_errors)
            # Retain all filename identities in the split, even failed parses.
            missing = filenames[~filenames.physical_cell_id.isin(dataset.identity_map.physical_cell_id)].copy()
            missing["ingest_status"] = "failed_raw_parse"
            dataset.identity_map = pd.concat([dataset.identity_map, missing], ignore_index=True)
        dataset.exclusions.extend({"physical_cell_id": row.iloc[0].physical_cell_id, "reason": "final_split_sealed_before_raw_access"} for row in sealed_rows)
    elif source == "matr":
        paths = [_resolve(name, raw_root) for name in settings.get("files", [])]
        if not paths:
            raise FileNotFoundError("MATR official URLs remain unresolved; raw import is not successful")
        dataset = parse_matr_mat(paths, repair_continuations=True, paper_exclusion_record_ids=settings.get("verified_paper_exclusion_record_ids", []))
        split = freeze_group_split(dataset.identity_map, seed=config.get("seed", 20261001), ratios=tuple(config.get("split_ratios", (.6, .15, .1, .15))))
    elif source in {"dyad", "ch_batterygen"}:
        files = settings.get("files", [])
        if not files or not settings.get("table_contract"):
            raise ValueError("operational/generated raw import needs an inspected file and explicit original table contract")
        dataset = ParsedDataset.concat(parse_table(_resolve(name, raw_root), settings["table_contract"]) for name in files)
        split = freeze_group_split(dataset.identity_map, seed=config.get("seed", 20261001), ratios=tuple(config.get("split_ratios", (.6, .15, .1, .15))))
    else:
        raise ValueError(f"unknown source: {source}")
    manifest = dataset.write(output, split)
    manifest["sealed_final_content_loaded"] = include_final
    manifest["eligible_measured_objects"] = int(dataset.cycles.physical_cell_id.nunique()) if not dataset.cycles.empty else int(dataset.segments.physical_cell_id.nunique()) if not dataset.segments.empty else 0
    write_json(output / "manifest.json", manifest)
    audit = audit_manifest(output / "manifest.json")
    write_json(output / "audit.json", audit)
    if not audit["passed"]:
        raise ValueError("V2 import did not pass structural audit: " + "; ".join(audit["failures"]))
    return {"status": "parsed", "manifest_path": str(output / "manifest.json"), "manifest": manifest, "audit": audit}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--config", default=str(ROOT / "configs/data_v2.yaml"))
    parser.add_argument("--metadata-only", action="store_true", help="refresh actual official metadata without downloading raw")
    parser.add_argument("--download-only", action="store_true", help="download selected current official files with checksum/resume/disk reserve; never execute archives")
    parser.add_argument("--file-name", help="exact published filename for --download-only; omitted downloads all declared files within budgets")
    parser.add_argument("--include-final", action="store_true", help="prepare newly frozen V2 final split after model recipe freeze; protected V1 cells remain rejected")
    parser.add_argument("--out", help="new immutable derived/v2 output directory")
    args = parser.parse_args()
    config_path = Path(args.config)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if args.metadata_only and args.download_only:
        parser.error("metadata-only and download-only are separate operations")
    result = ingest(config, args.source, config_base=ROOT, metadata_only=args.metadata_only, include_final=args.include_final, output_override=args.out, download_only=args.download_only, file_name=args.file_name)
    if args.metadata_only:
        print(json.dumps({"registry_path": result["registry_path"], "sources": [{"source_id": row["source_id"], "status": row["status"], "file_count": len(row["files"]), "license_status": row["license_status"], "errors": row["errors"]} for row in result["sources"]]}, ensure_ascii=False, indent=2))
    elif args.download_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": result["status"], "manifest_path": result["manifest_path"], "audit": result["audit"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
