#!/usr/bin/env python3
"""Auditable registry, download, archive inspection, and cell manifest CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data_sources.json"
DERIVED = ROOT / "data" / "derived"
RAW = ROOT / "data" / "raw"
MAX_RETRIES = 3
CHUNK = 8 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, Any]) -> None:
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


def event(kind: str, **fields: Any) -> None:
    path = DERIVED / "download_events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": now(), "kind": kind, **fields}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


def source_entry(source_id: str) -> dict[str, Any]:
    for source in load_registry()["sources"]:
        if source["id"] == source_id:
            return source
    raise SystemExit(f"unknown source: {source_id}")


def update_status(source_id: str, status: str, **extra: Any) -> None:
    registry = load_registry()
    for source in registry["sources"]:
        if source["id"] == source_id:
            source["status"] = status
            source.update(extra)
            break
    save_registry(registry)


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "model-lab/0.1 metadata-check"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def cmd_registry(_: argparse.Namespace) -> int:
    for source in load_registry()["sources"]:
        print(f"{source['id']}: {source['status']} - {source['official_url']}")
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    source = source_entry(args.source)
    if not source.get("metadata_api"):
        event("metadata_blocked", source=args.source, reason="no_official_api_configured")
        update_status(args.source, "blocked", blocked_reason="official metadata API not configured")
        return 2
    try:
        metadata = fetch_json(source["metadata_api"])
    except Exception as exc:  # noqa: BLE001 - persisted as an audit event
        event("metadata_error", source=args.source, error=repr(exc))
        update_status(args.source, "blocked", blocked_reason=repr(exc))
        return 2
    target = DERIVED / args.source / "official_record.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata_block = metadata.get("metadata", {})
    files = metadata.get("files", [])
    file_summary = []
    for item in files:
        file_url = item.get("links", {}).get("self")
        file_summary.append({"key": item.get("key"), "size": item.get("size"), "checksum": item.get("checksum"), "url": file_url})
    summary = {
        "record_id": metadata.get("id"),
        "version": metadata_block.get("version"),
        "license": (metadata_block.get("license") or {}).get("id"),
        "title": metadata_block.get("title"),
        "modified": metadata.get("modified"),
        "files": file_summary,
    }
    (target.parent / "official_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_status(args.source, "metadata_verified", official_record=str(target.relative_to(ROOT)), official_summary=summary)
    event("metadata_verified", source=args.source, record_id=metadata.get("id"), file_count=len(files), license=summary["license"], version=summary["version"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def checksum(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as fh:
        while block := fh.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def archive_file_info(source: dict[str, Any]) -> dict[str, Any]:
    summary = source.get("official_summary", {})
    for item in summary.get("files", []):
        if str(item.get("key", "")).lower().endswith((".zip", ".tar", ".tgz", ".gz")) or item.get("key") == "Battery Dataset.zip":
            return item
    raise SystemExit("no downloadable archive was recorded; run metadata first")


def download_file(url: str, target: Path, expected_size: int | None, expected_md5: str | None, source_id: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    if target.exists() and expected_size is not None and target.stat().st_size == expected_size:
        md5 = checksum(target, "md5")
        if not expected_md5 or md5 == expected_md5:
            event("download_complete_existing", source=source_id, path=str(target.relative_to(ROOT)), bytes=target.stat().st_size, md5=md5)
            return
        target.unlink()
    disk_policy = load_registry()["disk_policy"]
    max_new = int(disk_policy["max_new_bytes"])
    projected = (part.stat().st_size if part.exists() else 0) + (expected_size or 0)
    if projected > max_new:
        raise RuntimeError(f"download exceeds new-byte budget: {projected} > {max_new}")
    if free_bytes(ROOT) - (expected_size or 0) < int(disk_policy["min_free_bytes"]):
        raise RuntimeError("download would violate minimum free-space policy")
    for attempt in range(1, MAX_RETRIES + 1):
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "model-lab/0.1 downloader"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        event("download_attempt", source=source_id, attempt=attempt, url=url, offset=offset)
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                supports_resume = response.status == 206 and offset > 0
                if offset and not supports_resume:
                    raise IOError("Server did not honor Range; preserving the existing partial file rather than restarting destructively")
                if supports_resume:
                    content_range = response.headers.get("Content-Range", "")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range.strip())
                    if not match or int(match.group(1)) != offset:
                        raise IOError(f"Invalid resume Content-Range: {content_range!r}; partial file preserved")
                    if expected_size is not None and match.group(3) != str(expected_size):
                        raise IOError(f"Resume total size changed: {content_range!r}; partial file preserved")
                mode = "ab" if supports_resume else "wb"
                received = offset
                transfer_started = time.monotonic()
                with part.open(mode) as out:
                    while block := response.read(CHUNK):
                        if time.monotonic() - transfer_started > 300:
                            raise TimeoutError("Bounded transfer window exceeded; keeping partial file for a later explicit resume")
                        if expected_size is not None and received + len(block) > expected_size:
                            raise IOError("Response exceeds declared source size; refusing extra bytes")
                        out.write(block)
                        received += len(block)
            if expected_size is not None and part.stat().st_size != expected_size:
                raise IOError(f"size mismatch after transfer: {part.stat().st_size} != {expected_size}")
            md5 = checksum(part, "md5")
            if expected_md5 and md5 != expected_md5:
                raise IOError(f"MD5 mismatch: {md5} != {expected_md5}")
            sha256 = checksum(part, "sha256")
            part.replace(target)
            event("download_verified", source=source_id, path=str(target.relative_to(ROOT)), bytes=target.stat().st_size, md5=md5, sha256=sha256)
            return
        except Exception as exc:  # noqa: BLE001 - bounded retry is intentional
            event("download_error", source=source_id, attempt=attempt, error=repr(exc), partial_bytes=part.stat().st_size if part.exists() else 0)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 ** (attempt - 1))


def cmd_download(args: argparse.Namespace) -> int:
    source = source_entry(args.source)
    info = archive_file_info(source)
    url = info["url"]
    if not url:
        raise SystemExit("recorded file has no content URL")
    target = ROOT / source["raw_dir"] / str(info["key"])
    expected_md5 = str(info.get("checksum", "")).removeprefix("md5:") or None
    download_file(url, target, int(info["size"]) if info.get("size") is not None else None, expected_md5, args.source)
    update_status(args.source, "complete", downloaded_file=str(target.relative_to(ROOT)), downloaded_bytes=target.stat().st_size, md5=checksum(target, "md5"), sha256=checksum(target, "sha256"))
    return 0


def safe_member_name(name: str) -> PurePosixPath:
    if "\x00" in name:
        raise ValueError("NUL in archive member")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe archive member path: {name!r}")
    if re.match(r"^[A-Za-z]:", name):
        raise ValueError(f"drive-qualified archive member path: {name!r}")
    return path


def inspect_zip(zip_path: Path, source_id: str) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as archive:
        members = []
        total_uncompressed = 0
        for info in archive.infolist():
            path = safe_member_name(info.filename)
            total_uncompressed += info.file_size
            members.append({"name": str(path), "compressed_size": info.compress_size, "uncompressed_size": info.file_size, "is_dir": info.is_dir()})
        free = free_bytes(ROOT)
        if total_uncompressed > load_registry()["disk_policy"]["max_new_bytes"]:
            raise RuntimeError(f"archive expansion exceeds new-byte budget: {total_uncompressed}")
        if free - total_uncompressed < load_registry()["disk_policy"]["min_free_bytes"]:
            raise RuntimeError("archive expansion would violate minimum free-space policy")
    summary = {"archive": str(zip_path.relative_to(ROOT)), "member_count": len(members), "estimated_uncompressed_bytes": total_uncompressed, "members": members}
    target = DERIVED / source_id / "archive_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    event("archive_inspected", source=source_id, member_count=len(members), estimated_uncompressed_bytes=total_uncompressed)
    return summary


def extract_zip(zip_path: Path, target_dir: Path, source_id: str) -> None:
    summary = inspect_zip(zip_path, source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            member = safe_member_name(info.filename)
            destination = target_dir.joinpath(*member.parts)
            resolved_root = target_dir.resolve()
            if not destination.resolve().is_relative_to(resolved_root):
                raise ValueError(f"archive path escapes extraction root: {info.filename!r}")
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=CHUNK)
    event("archive_extracted", source=source_id, target=str(target_dir.relative_to(ROOT)), member_count=summary["member_count"])


def cmd_inspect(args: argparse.Namespace) -> int:
    source = source_entry(args.source)
    downloaded = source.get("downloaded_file")
    if not downloaded:
        raise SystemExit("source has no downloaded file; run download first")
    archive = ROOT / downloaded
    summary = inspect_zip(archive, args.source)
    extract_dir = ROOT / source["raw_dir"] / "extracted"
    if args.extract:
        extract_zip(archive, extract_dir, args.source)
    candidates = [item["name"] for item in summary["members"] if not item["is_dir"]][:30]
    print(json.dumps({"archive": summary["archive"], "member_count": summary["member_count"], "estimated_uncompressed_bytes": summary["estimated_uncompressed_bytes"], "first_files": candidates}, ensure_ascii=False, indent=2))
    return 0


def find_cell_like_paths(root: Path) -> list[str]:
    paths = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".mat", ".csv", ".xlsx", ".xls", ".txt", ".json"}:
            paths.append(str(path.relative_to(root)))
    return sorted(paths)


def cmd_cells(args: argparse.Namespace) -> int:
    source = source_entry(args.source)
    extracted = ROOT / source["raw_dir"] / "extracted"
    if not extracted.exists():
        raise SystemExit("source is not extracted; run inspect --extract first")
    files = find_cell_like_paths(extracted)
    report = {"source": args.source, "generated_at": now(), "raw_root": str(extracted.relative_to(ROOT)), "candidate_files": files, "cell_count": None, "field_preview": [], "label_semantics": "unverified"}
    target = DERIVED / args.source / "cell_field_preview.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    event("source_inventory", source=args.source, candidate_file_count=len(files), label_semantics="unverified")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    source = source_entry(args.source)
    report_path = DERIVED / args.source / "cell_field_preview.json"
    if not report_path.exists():
        raise SystemExit("run inspect --extract and cells first")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cells = report.get("cell_ids") or []
    if not cells:
        raise SystemExit("no verified physical cell IDs available; candidate split not fabricated")
    cells = sorted(dict.fromkeys(cells))
    n = len(cells)
    n_train = max(1, round(n * 0.6))
    n_val = max(1, round(n * 0.2))
    if n_train + n_val >= n:
        n_train, n_val = max(1, n - 2), 1
    split = {"schema_version": "0.1", "source": args.source, "strategy": "physical_cell_candidate_60_20_20", "generated_at": now(), "identity_mapping": [{"raw_cell_id": cell, "canonical_cell_id": f"{args.source}:{cell}"} for cell in cells], "train": cells[:n_train], "validation": cells[n_train:n_train+n_val], "test": cells[n_train+n_val:], "status": "candidate_requires_review"}
    target = DERIVED / "cell_split_candidate.json"
    target.write_text(json.dumps(split, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    event("candidate_split_created", source=args.source, cell_count=n)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("registry").set_defaults(func=cmd_registry)
    p = sub.add_parser("metadata"); p.add_argument("source"); p.set_defaults(func=cmd_metadata)
    p = sub.add_parser("download"); p.add_argument("source"); p.set_defaults(func=cmd_download)
    p = sub.add_parser("inspect"); p.add_argument("source"); p.add_argument("--extract", action="store_true"); p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("cells"); p.add_argument("source"); p.set_defaults(func=cmd_cells)
    p = sub.add_parser("split"); p.add_argument("source"); p.set_defaults(func=cmd_split)
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    raise SystemExit(parsed.func(parsed))
