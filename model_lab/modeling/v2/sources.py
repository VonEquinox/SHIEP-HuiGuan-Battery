"""Official-source metadata and bounded resumable raw downloads for V2."""

from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from .data import PARSER_VERSION, sha256_file, utc_now, write_json

DEFAULT_PROXY = "http://127.0.0.1:7897"
SOURCE_DEFINITIONS = {
    "xjtu": {"source_id": "xjtu", "landing_url": "https://zenodo.org/records/10963339", "metadata_api": "https://zenodo.org/api/records/10963339", "paper_doi": "10.1038/s41467-024-48779-z", "origin": "real_experimental"},
    "matr": {"source_id": "matr", "landing_url": "https://data.matr.io/1/projects/5c48dd2bc625d700019f3204", "metadata_api": None, "paper_doi": "10.1038/s41560-019-0356-8", "origin": "real_experimental", "author_repository": "rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation"},
    "dyad": {"source_id": "dyad", "landing_url": "https://figshare.com/articles/dataset/Realistic_fault_detection_of_Li-ion_battery_via_dynamical_deep_learning_approach/23659323", "metadata_api": "https://api.figshare.com/v2/articles/23659323", "paper_doi": "10.1038/s41467-023-41226-5", "origin": "real_operational"},
    "ch_batterygen": {"source_id": "ch_batterygen", "landing_url": "https://github.com/CH-BatteryGen/dataset-warehouse/releases", "metadata_api": "https://api.github.com/repos/CH-BatteryGen/dataset-warehouse/releases", "paper_doi": None, "paper_url": "https://openreview.net/forum?id=jSM71b1JsV", "origin": "public_generated", "author_repository": "CH-BatteryGen/dataset-warehouse"},
}


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"a", "script", "include-fragment"}:
            data = dict(attrs)
            value = data.get("href" if tag == "a" else "src")
            if value:
                self.urls.append(value)


def _session(proxy: str | None):
    import requests
    session = requests.Session()
    session.trust_env = False
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.headers.update({"User-Agent": "HuiGuan-Battery-V2-source-registry/1.0", "Accept": "application/json"})
    return session


def _get_snapshot(session: Any, url: str, output: Path, *, as_json: bool = True) -> tuple[Any, dict[str, Any]]:
    response = session.get(url, headers={"Accept": "application/json" if as_json else "text/html,application/xhtml+xml"}, timeout=(10, 40))
    response.raise_for_status()
    output.write_bytes(response.content)
    receipt = {"requested_url": url, "resolved_url": response.url, "http_status": response.status_code, "retrieved_at": utc_now(), "bytes": len(response.content), "sha256": sha256_file(output), "path": str(output.resolve())}
    if output.suffix in {".html", ".js", ".m"} or output.name == "author_LoadData_metadata.json":
        receipt.update(local_only=True, retention="local_snapshot_not_distributed; official URL and digest retained")
    return (response.json() if as_json else response.text), receipt


def _write_ch_readme_license(destination: Path, html: str, receipt: dict[str, Any]) -> str:
    """Persist the declared terms as small evidence, not a full website copy."""
    if not all(term in html for term in ("CC BY-NC-SA 4.0", "strictly limited to academic research", "Without explicit permission from the data provider", "must not be transferred")):
        raise ValueError("official README license or additional terms changed; manual scope review required")
    links = _Links()
    links.feed(html)
    readme_urls = [urljoin(receipt["resolved_url"], link) for link in links.urls if "/blob/" in link and link.endswith("README.md")]
    metadata = {
        "license": {"id": "CC-BY-NC-SA-4.0", "name": "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International"},
        "scope": "CH-BatteryGen published dataset; official README additional terms apply",
        "source_url": readme_urls[0] if readme_urls else receipt["resolved_url"],
        "source_repository_url": receipt["resolved_url"],
        "source_html_sha256": receipt["sha256"],
        "retrieved_at": receipt["retrieved_at"],
        "terms_summary": [
            "Academic research, non-commercial use, or separately authorized purposes only.",
            "Acknowledge the provider and respect its intellectual property rights.",
            "Provider permission is required to transfer or distribute any part of the dataset, or use it commercially.",
            "Respect privacy and applicable law; prohibited discriminatory, illegal or improper uses remain subject to provider terms.",
        ],
        "terms_summary_is_paraphrase": True,
        "full_source_snapshot_local_only": True,
        "verification": "License declaration and terms observed in the official repository README HTML; refetch official source to review current terms.",
    }
    path = destination / "license_metadata.json"
    write_json(path, metadata)
    return str(path)


def refresh_metadata(source_id: str, report_dir: str | Path, proxy: str | None = DEFAULT_PROXY) -> dict[str, Any]:
    """Fetch metadata only. A reachable page never implies imported raw data."""
    if source_id not in SOURCE_DEFINITIONS:
        raise ValueError(f"unknown source: {source_id}")
    definition = SOURCE_DEFINITIONS[source_id]
    destination = Path(report_dir).resolve() / source_id
    destination.mkdir(parents=True, exist_ok=True)
    previous_path = destination / "registry_record.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    row = {**definition, "resolved_download_url": [], "license_status": "unverified", "license_text_path": None, "retrieved_at": utc_now(), "original_filename": [], "bytes": None, "sha256": None, "author_checksum": [], "parser_version": PARSER_VERSION, "status": "metadata_only", "files": [], "metadata_receipts": [], "errors": []}
    session = _session(proxy)
    try:
        if source_id == "xjtu":
            payload, receipt = _get_snapshot(session, definition["metadata_api"], destination / "official_record.json")
            row["metadata_receipts"].append(receipt)
            license_info = payload.get("metadata", {}).get("license")
            if license_info:
                write_json(destination / "license_metadata.json", {"license": license_info, "source_url": receipt["resolved_url"], "scope": "specific Zenodo record; not repository modeling code"})
                row.update(license_status="declared_in_official_record", license_text_path=str(destination / "license_metadata.json"), license=license_info)
            row["files"] = [{"name": entry["key"], "bytes": entry["size"], "url": entry.get("links", {}).get("self") or entry.get("links", {}).get("content"), "author_checksum": entry.get("checksum")} for entry in payload.get("files", [])]
        elif source_id == "dyad":
            payload, receipt = _get_snapshot(session, definition["metadata_api"], destination / "official_record.json")
            row["metadata_receipts"].append(receipt)
            license_info = payload.get("license")
            if license_info:
                write_json(destination / "license_metadata.json", {"license": license_info, "source_url": receipt["resolved_url"]})
                row.update(license_status="declared_in_official_record", license_text_path=str(destination / "license_metadata.json"), license=license_info)
            row["files"] = [{"name": entry["name"], "bytes": entry["size"], "url": entry.get("download_url"), "author_checksum": f"md5:{entry['computed_md5']}" if entry.get("computed_md5") else None} for entry in payload.get("files", [])]
        elif source_id == "ch_batterygen":
            payload, receipt = _get_snapshot(session, definition["metadata_api"], destination / "official_releases.json")
            row["metadata_receipts"].append(receipt)
            row["files"] = [{"name": asset["name"], "bytes": asset["size"], "url": asset["browser_download_url"], "author_checksum": asset.get("digest"), "release_tag": release["tag_name"], "release_published_at": release.get("published_at")} for release in payload if not release.get("draft") for asset in release.get("assets", [])]
            try:
                license_payload, license_receipt = _get_snapshot(session, f"https://api.github.com/repos/{definition['author_repository']}/license", destination / "official_license.json")
                row["metadata_receipts"].append(license_receipt)
                text = base64.b64decode(license_payload.get("content", "")).decode("utf-8")
                (destination / "LICENSE.txt").write_text(text, encoding="utf-8")
                row.update(license_status="declared_repository_license_scope_requires_review", license_text_path=str(destination / "LICENSE.txt"), license=license_payload.get("license"))
            except Exception as exc:
                row["errors"].append(f"repository license unavailable: {type(exc).__name__}: {exc}")
        else:
            text, receipt = _get_snapshot(session, definition["landing_url"], destination / "official_page.html", as_json=False)
            row["metadata_receipts"].append(receipt)
            parser = _Links()
            parser.feed(text)
            row["discovered_official_links"] = [urljoin(receipt["resolved_url"], url) for url in parser.urls]
            # Resolve only raw-file links actually published by the official
            # project, never fabricate a third-party mirror or guessed API URL.
            row["files"] = [{"name": Path(urlparse(url).path).name, "bytes": None, "url": url, "author_checksum": None} for url in row["discovered_official_links"] if urlparse(url).path.lower().endswith((".mat", ".h5", ".hdf5", ".zip"))]
            if not row["files"]:
                row["status"] = "blocked"
                row["errors"].append("official project is a JavaScript shell; current raw-file URLs and dataset license were not resolved; no guessed URLs used")
                # Follow the published app, not a third-party mirrored ID.
                # Current SPA declares edp/projects, batches, file/{id}/download
                # and an API prefix. Fail closed if that published contract
                # changes instead of inventing new endpoint candidates.
                app_urls = [url for url in row["discovered_official_links"] if "/main." in url and url.endswith(".js")]
                if app_urls:
                    app_text, app_receipt = _get_snapshot(session, app_urls[0], destination / "official_app.js", as_json=False)
                    row["metadata_receipts"].append(app_receipt)
                    if 'An="edp"' in app_text and '/api/v1' in app_text and 'url:"projects"' in app_text and 'url:"batches"' in app_text:
                        landing = urlparse(definition["landing_url"])
                        prefix = landing.path.split("/projects/", 1)[0]
                        project_id = landing.path.rsplit("/", 1)[-1]
                        api_base = f"{landing.scheme}://{landing.netloc}{prefix}/api/v1/"
                        project_url = api_base + f"edp/projects/{project_id}"
                        project, project_receipt = _get_snapshot(session, project_url, destination / "official_project.json")
                        batches, batches_receipt = _get_snapshot(session, project_url + "/batches", destination / "official_batches.json")
                        configuration, configuration_receipt = _get_snapshot(session, api_base + "edp/configuration", destination / "official_configuration.json")
                        row["metadata_receipts"].extend((project_receipt, batches_receipt, configuration_receipt))
                        row["metadata_api"] = project_url
                        row["license"] = configuration.get("license")
                        row["license_status"] = "declared_official_platform_license_dataset_scope_recorded"
                        write_json(destination / "license_metadata.json", {"license": configuration.get("license"), "source_url": configuration_receipt["resolved_url"], "project_id": project_id, "scope": "official dataset platform; author modeling code has separate licensing"})
                        row["license_text_path"] = str(destination / "license_metadata.json")
                        row["files"] = []
                        for batch in batches:
                            file_id = batch.get("structFileId")
                            if not file_id:
                                continue
                            metadata, metadata_receipt = _get_snapshot(session, api_base + f"file/{file_id}", destination / f"official_file_{batch['title']}.json")
                            row["metadata_receipts"].append(metadata_receipt)
                            row["files"].append({"name": metadata["name"], "bytes": metadata["size"], "url": api_base + f"file/{file_id}/download", "author_checksum": metadata.get("sha256"), "file_id": file_id, "batch_id": batch["title"]})
                        if row["files"]:
                            row["status"] = "metadata_only"
                            row["errors"].append("JavaScript-shell obstacle resolved through paths and file IDs actually published by the current official SPA")
            # Preserve author's processing source without executing it. Its
            # licensing does not automatically grant the dataset/code license.
            try:
                repo_api = f"https://api.github.com/repos/{definition['author_repository']}/contents/LoadData.m"
                source_payload, source_receipt = _get_snapshot(session, repo_api, destination / "author_LoadData_metadata.json")
                row["metadata_receipts"].append(source_receipt)
                (destination / "author_LoadData.m").write_bytes(base64.b64decode(source_payload.get("content", "")))
            except Exception as exc:
                row["errors"].append(f"author processing source unavailable: {type(exc).__name__}: {exc}")
                try:
                    repository_url = f"https://github.com/{definition['author_repository']}"
                    repo_html, repo_receipt = _get_snapshot(session, repository_url, destination / "official_author_repository.html", as_json=False)
                    row["metadata_receipts"].append(repo_receipt)
                    repo_links = _Links()
                    repo_links.feed(repo_html)
                    author_links = [urljoin(repo_receipt["resolved_url"], url) for url in repo_links.urls if "/blob/" in url and url.endswith("LoadData.m")]
                    if not author_links:
                        raise ValueError("author repo HTML has no published LoadData.m path")
                    author_url = author_links[0].replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")
                    source_text, source_receipt = _get_snapshot(session, author_url, destination / "author_LoadData.m", as_json=False)
                    row["metadata_receipts"].append(source_receipt)
                    row["author_processing_url"] = source_receipt["resolved_url"]
                except Exception as fallback_exc:
                    row["errors"].append(f"official author HTML fallback failed: {type(fallback_exc).__name__}: {fallback_exc}")
        row["resolved_download_url"] = [entry["url"] for entry in row["files"] if entry.get("url")]
        row["original_filename"] = [entry["name"] for entry in row["files"]]
        row["author_checksum"] = [entry["author_checksum"] for entry in row["files"] if entry.get("author_checksum")]
        if row["files"] and all(entry.get("bytes") is not None for entry in row["files"]):
            row["bytes"] = sum(entry["bytes"] for entry in row["files"])
        if not row["files"]:
            row["status"] = "blocked"
    except Exception as exc:
        row["status"] = "blocked"
        row["errors"].append(f"metadata request failed: {type(exc).__name__}: {exc}")
        if source_id == "ch_batterygen":
            # Public HTML is an official fallback when anonymous GitHub API
            # quotas are exhausted. Asset URLs come from actual linked lazy
            # fragments; file paths/tags/checksums are never guessed.
            try:
                text, receipt = _get_snapshot(session, definition["landing_url"], destination / "official_releases.html", as_json=False)
                row["metadata_receipts"].append(receipt)
                links = _Links()
                links.feed(text)
                published = [urljoin(receipt["resolved_url"], url) for url in links.urls]
                for index, fragment_url in enumerate(url for url in published if "/releases/expanded_assets/" in url):
                    fragment, fragment_receipt = _get_snapshot(session, fragment_url, destination / f"official_assets_{index}.html", as_json=False)
                    row["metadata_receipts"].append(fragment_receipt)
                    fragment_links = _Links()
                    fragment_links.feed(fragment)
                    published.extend(urljoin(fragment_receipt["resolved_url"], url) for url in fragment_links.urls)
                asset_urls = sorted(set(url for url in published if "/releases/download/" in url))
                row["files"] = [{"name": Path(urlparse(url).path).name, "bytes": None, "url": url, "author_checksum": None} for url in asset_urls]
                for entry in row["files"]:
                    try:
                        head = session.head(entry["url"], headers={"Accept": "*/*"}, allow_redirects=True, timeout=(10, 30))
                        head.raise_for_status()
                        entry["bytes"] = int(head.headers["Content-Length"]) if head.headers.get("Content-Length") else None
                        entry["size_source"] = "current_official_asset_HEAD"
                    except Exception as head_exc:
                        row["errors"].append(f"asset size unavailable: {type(head_exc).__name__}: {head_exc}")
                repository_url = f"https://github.com/{definition['author_repository']}"
                repo_html, repo_receipt = _get_snapshot(session, repository_url, destination / "official_repository.html", as_json=False)
                row["metadata_receipts"].append(repo_receipt)
                if "CC BY-NC-SA 4.0" in repo_html:
                    row.update(license_status="declared_noncommercial_readme_terms", license="CC BY-NC-SA 4.0; academic/non-commercial or specifically authorized use", license_text_path=_write_ch_readme_license(destination, repo_html, repo_receipt))
                row["resolved_download_url"] = asset_urls
                row["original_filename"] = [entry["name"] for entry in row["files"]]
                row["status"] = "metadata_only" if asset_urls else "blocked"
            except Exception as fallback_exc:
                row["errors"].append(f"official HTML fallback failed: {type(fallback_exc).__name__}: {fallback_exc}")
    finally:
        session.close()
    row["resolved_download_url"] = [entry["url"] for entry in row["files"] if entry.get("url")]
    row["original_filename"] = [entry["name"] for entry in row["files"]]
    row["author_checksum"] = [entry["author_checksum"] for entry in row["files"] if entry.get("author_checksum")]
    if row["files"] and all(entry.get("bytes") is not None for entry in row["files"]):
        row["bytes"] = sum(entry["bytes"] for entry in row["files"])
    old_files = {entry["name"]: entry for entry in previous.get("files", [])}
    new_files = {entry["name"]: entry for entry in row["files"]}
    same_published_files = old_files.keys() == new_files.keys() and all(old_files[name].get("url") == new_files[name].get("url") and (old_files[name].get("bytes") is None or new_files[name].get("bytes") is None or old_files[name]["bytes"] == new_files[name]["bytes"]) and old_files[name].get("author_checksum") == new_files[name].get("author_checksum") for name in old_files)
    if same_published_files and previous.get("status") in {"verified", "parsed"}:
        for key in ("raw_receipts", "raw_scope", "raw_verified_bytes", "raw_sha256", "sha256", "unfetched_official_files", "parsed_manifest"):
            if key in previous:
                row[key] = previous[key]
        row["status"] = previous["status"]
    write_json(destination / "registry_record.json", row)
    return row


def get_local_registry(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return [{**entry, "status": "metadata_only", "license_status": "unverified", "files": []} for entry in SOURCE_DEFINITIONS.values()]
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("sources", []) if isinstance(data, dict) else data


def save_registry(path: str | Path, records: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"schema_version": "source-registry-v2", "retrieved_at": utc_now(), "sources": records}, sort_keys=False, allow_unicode=True), encoding="utf-8")


def download_verified(file_record: dict[str, Any], output: str | Path, proxy: str | None = DEFAULT_PROXY, *, retries: int = 3, max_bytes: int = 4 * 1024**3) -> dict[str, Any]:
    """Range resume + author digest + SHA256 + immutable atomic finalization."""
    url = file_record.get("url")
    if not url or urlparse(url).scheme != "https":
        raise ValueError("download requires a resolved official HTTPS file URL")
    expected_bytes = file_record.get("bytes")
    if expected_bytes is not None and expected_bytes > max_bytes:
        raise ValueError("download exceeds configured raw-byte budget")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("raw originals are immutable; choose a new path or verify existing independently")
    partial = destination.with_name(destination.name + ".part")
    session = _session(proxy)
    errors = []
    try:
        for attempt in range(max(1, retries)):
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > max_bytes:
                raise ValueError("partial file exceeds configured budget")
            try:
                with session.get(url, headers={"Accept": "*/*", **({"Range": f"bytes={offset}-"} if offset else {})}, stream=True, timeout=(10, 60)) as response:
                    response.raise_for_status()
                    if offset and response.status_code == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                            raise ValueError("server returned mismatched resume offset")
                        mode = "ab"
                    else:
                        # Range unsupported: restart rather than append a full
                        # response to a partial file.
                        mode, offset = "wb", 0
                    with partial.open(mode) as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            if not chunk:
                                continue
                            offset += len(chunk)
                            if offset > max_bytes:
                                raise ValueError("download crossed configured raw-byte budget")
                            stream.write(chunk)
                if expected_bytes is not None and partial.stat().st_size != expected_bytes:
                    raise ValueError("download byte count does not match official metadata")
                checksum = file_record.get("author_checksum")
                if checksum:
                    algorithm, expected = checksum.split(":", 1)
                    if algorithm not in {"md5", "sha256", "sha1"}:
                        raise ValueError("unsupported author checksum algorithm")
                    digest = hashlib.new(algorithm)
                    with partial.open("rb") as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                    if digest.hexdigest().lower() != expected.lower():
                        # A corrupted complete partial cannot be resumed.
                        partial.rename(partial.with_name(partial.name + f".checksum-failed-{attempt}"))
                        raise ValueError("author checksum mismatch; corrupt attempt retained")
                redirect = urlparse(response.url)
                stable_redirect = redirect._replace(query="", fragment="").geturl()
                result = {"status": "verified", "path": str(destination.resolve()), "resolved_download_url": url, "transport_destination": stable_redirect, "original_filename": file_record.get("name"), "bytes": partial.stat().st_size, "sha256": sha256_file(partial), "author_checksum": checksum, "retrieved_at": utc_now(), "attempts": attempt + 1, "prior_errors": errors}
                os.replace(partial, destination)
                destination.chmod(0o444)
                return result
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if isinstance(exc, ValueError) and "budget" in str(exc):
                    break
        raise RuntimeError("download did not verify: " + " | ".join(errors))
    finally:
        session.close()


def decode_dyad_numeric_archive(payload: bytes) -> Any:
    """Decode only the author's declarative numeric subset, never unpickle.

    GLOBAL/REDUCE tokens are recognized as data markers; no named callable is
    resolved or invoked. Arbitrary pickle/joblib remains forbidden in the
    platform parser. This offline converter additionally runs in an OS sandbox.
    """
    import io
    import pickletools
    import zipfile
    import numpy as np

    if len(payload) > 2 * 1024**2:
        raise ValueError("DyAD member exceeds conversion budget")
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if name.endswith("/data.pkl")]
            if len(names) != 1 or archive.getinfo(names[0]).file_size > 2 * 1024**2:
                raise ValueError("unrecognized bounded Torch archive")
            payload = archive.read(names[0])
    marker = object()
    stack, memo = [], {}

    class Token:
        def __init__(self, kind: str, value: Any = None):
            self.kind, self.value = kind, value

    def reduce_mark() -> list[Any]:
        index = max(index for index, value in enumerate(stack) if value is marker)
        values = stack[index + 1:]
        del stack[index:]
        return values

    allowed_globals = {"numpy.core.multiarray _reconstruct", "numpy._core.multiarray _reconstruct", "numpy ndarray", "numpy dtype", "_codecs encode"}
    for count, (operation, argument, _) in enumerate(pickletools.genops(payload)):
        if count > 2048:
            raise ValueError("DyAD opcode count exceeds budget")
        name = operation.name
        if name in {"PROTO", "FRAME"}:
            continue
        if name == "MARK":
            stack.append(marker)
        elif name in {"BININT", "BININT1", "BININT2", "LONG1", "LONG4", "BINFLOAT", "BINUNICODE", "SHORT_BINUNICODE", "BINBYTES", "SHORT_BINBYTES"}:
            stack.append(argument)
        elif name in {"NONE", "NEWTRUE", "NEWFALSE"}:
            stack.append({"NONE": None, "NEWTRUE": True, "NEWFALSE": False}[name])
        elif name == "EMPTY_DICT":
            stack.append({})
        elif name == "EMPTY_LIST":
            stack.append([])
        elif name == "EMPTY_TUPLE":
            stack.append(())
        elif name in {"BINPUT", "LONG_BINPUT"}:
            memo[argument] = stack[-1]
        elif name == "MEMOIZE":
            memo[len(memo)] = stack[-1]
        elif name in {"BINGET", "LONG_BINGET"}:
            stack.append(memo[argument])
        elif name == "GLOBAL":
            if argument not in allowed_globals:
                raise ValueError("non-numeric executable pickle global rejected")
            stack.append(Token("global", argument))
        elif name.startswith("TUPLE"):
            if name == "TUPLE":
                values = reduce_mark()
            else:
                length = int(name[-1])
                values = stack[-length:]
                del stack[-length:]
            stack.append(tuple(values))
        elif name in {"SETITEMS", "APPENDS"}:
            values = reduce_mark()
            if name == "SETITEMS":
                if not isinstance(stack[-1], dict) or len(values) % 2:
                    raise ValueError("invalid dictionary state")
                stack[-1].update(zip(values[::2], values[1::2]))
            else:
                if not isinstance(stack[-1], list):
                    raise ValueError("invalid list state")
                stack[-1].extend(values)
        elif name == "REDUCE":
            args, token = stack.pop(), stack.pop()
            if not isinstance(token, Token) or token.kind != "global" or not isinstance(args, tuple):
                raise ValueError("non-declarative constructor rejected")
            if token.value == "_codecs encode":
                if len(args) != 2 or args[1] != "latin1" or not isinstance(args[0], str):
                    raise ValueError("only exact numeric latin1 byte storage is accepted")
                stack.append(args[0].encode("latin1"))
            elif token.value == "numpy dtype":
                dtype = np.dtype(args[0])
                if dtype.kind not in "fiu" or dtype.itemsize > 8 or dtype.hasobject:
                    raise ValueError("only primitive numeric dtypes are accepted")
                stack.append(Token("dtype", dtype))
            elif token.value.endswith(" _reconstruct"):
                stack.append(Token("array"))
            else:
                raise ValueError("constructor is not part of numeric grammar")
        elif name == "BUILD":
            state = stack.pop()
            token = stack[-1]
            if not isinstance(token, Token):
                raise ValueError("custom object state rejected")
            if token.kind == "dtype":
                if not isinstance(state, tuple) or len(state) < 2 or state[1] not in ("<", ">", "=", "|"):
                    raise ValueError("invalid numeric dtype state")
                token.value = token.value.newbyteorder(state[1])
            elif token.kind == "array":
                if not isinstance(state, tuple) or len(state) != 5:
                    raise ValueError("invalid numeric ndarray state")
                version, shape, dtype, fortran_order, raw = state
                if version != 1 or not isinstance(shape, tuple) or not 1 <= len(shape) <= 2 or any(not isinstance(size, int) or size < 1 or size > 4096 for size in shape) or not isinstance(dtype, Token) or dtype.kind != "dtype" or not isinstance(raw, bytes):
                    raise ValueError("unrecognized bounded numeric array")
                required = int(np.prod(shape)) * dtype.value.itemsize
                if required != len(raw) or required > 2 * 1024**2:
                    raise ValueError("numeric byte length mismatch")
                token.value = np.frombuffer(raw, dtype=dtype.value).reshape(shape, order="F" if fortran_order else "C").copy()
            else:
                raise ValueError("unsupported object state")
        elif name == "STOP":
            if len(stack) != 1:
                raise ValueError("unexpected final pickle stack")
            value = stack[0]
            if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], Token) and value[0].kind == "array" and isinstance(value[1], dict):
                return value[0].value, value[1]
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return value
            raise ValueError("only numeric snippet + metadata or column names accepted")
        else:
            raise ValueError(f"unrecognized opcode denied: {name}")
    raise ValueError("incomplete numeric record")


def convert_dyad_archive(archive_path: str | Path, output: str | Path, *, max_per_vehicle: int = 8) -> dict[str, Any]:
    """Offline conversion of the registered raw archive into safe Parquet.

    Selection groups by vehicle; original fault label is a vehicle anomaly
    label, never a confirmed single-cell root cause. Numeric channels retain
    native names because units must be established before physics heads use
    them. No pickle.load/torch.load/imported global executes here.
    """
    import io
    import tarfile
    import pandas as pd
    import numpy as np
    from collections import Counter

    archive_path, output = Path(archive_path), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "snippets.parquet").exists():
        raise FileExistsError("converted raw subset is immutable")
    counts, rows, exclusions = Counter(), [], []
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 40000 or sum(member.size for member in members) > 512 * 1024**2:
            raise ValueError("archive exceeds offline conversion budget")
        if any(member.issym() or member.islnk() or member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
            raise ValueError("archive links and traversal paths rejected")
        column_member = next(member for member in members if member.name.endswith("/column.pkl"))
        columns = decode_dyad_numeric_archive(archive.extractfile(column_member).read())
        label_member = next(member for member in members if member.name.endswith("/label/all_label.csv"))
        labels = pd.read_csv(io.BytesIO(archive.extractfile(label_member).read()))
        vehicle_labels = dict(zip(labels.car.astype(int), labels.label.astype(int)))
        # Read monotonically through gzip offsets. Reordering names would
        # repeatedly decompress the entire archive for each random seek.
        for member in sorted((member for member in members if "/data/" in member.name and member.isfile()), key=lambda member: member.offset_data):
            try:
                payload = archive.extractfile(member).read()
                values, metadata = decode_dyad_numeric_archive(payload)
                vehicle = int(metadata["car"])
                if vehicle not in vehicle_labels:
                    raise ValueError("snippet references unknown original vehicle")
                if counts[vehicle] >= max_per_vehicle:
                    continue
                if values.ndim != 2 or values.shape[1] != len(columns):
                    raise ValueError("numeric shape differs from original column names")
                row = {"source_id": "dyad", "physical_cell_id": f"dyad:brand3:vehicle-{vehicle}", "vehicle_id": str(vehicle), "snippet_id": Path(member.name).stem, "segment_id": f"dyad:brand3:{Path(member.name).stem}", "charge_segment": str(metadata.get("charge_segment")), "mileage_km": float(metadata["mileage"]), "original_snippet_label": str(metadata.get("label")), "fault_label": vehicle_labels[vehicle], "label_granularity": "vehicle_anomaly", "origin": "real_operational", "raw_ref": f"{archive_path.resolve()}#{member.name}", "raw_member_sha256": hashlib.sha256(payload).hexdigest(), "chemistry": None, "protocol_id": "vehicle_charging", "time_unit": "source_native_unverified"}
                for index, column in enumerate(columns):
                    data = values[:, index]
                    row[column] = [float(value) if np.isfinite(value) else None for value in data]
                    finite = data[np.isfinite(data)]
                    row[f"{column}_mean"] = float(np.mean(finite)) if len(finite) else None
                    row[f"{column}_std"] = float(np.std(finite)) if len(finite) else None
                # timestamp is local to a charging snippet. Never pretend it
                # is a global event date or compare two vehicles by it.
                row["observed_at"] = float(metadata["charge_segment"])
                row["available_at"] = row["observed_at"]
                row["time_basis"] = "original_vehicle_charge_segment_number"
                rows.append(row)
                counts[vehicle] += 1
            except Exception as exc:
                exclusions.append({"member": member.name, "reason": f"{type(exc).__name__}: {exc}"})
    table_path = output / "snippets.parquet"
    pd.DataFrame(rows).to_parquet(table_path, index=False)
    labels.to_csv(output / "vehicle_labels.csv", index=False)
    receipt = {"status": "converted_numeric_subset", "parser_version": "dyad-declarative-opcodes-v1", "raw_archive_sha256": sha256_file(archive_path), "table_path": str(table_path.resolve()), "table_sha256": sha256_file(table_path), "columns": columns, "rows": len(rows), "independent_vehicles": len(counts), "selection": f"original archive order first {max_per_vehicle} snippets per original vehicle", "exclusions": exclusions, "label_granularity": "vehicle_anomaly_not_cell_root_cause", "units": "native unverified; statistical adapter only", "untrusted_callables_executed": False}
    write_json(output / "conversion_manifest.json", receipt)
    return receipt


def register_raw_receipts(source_id: str, report_dir: str | Path, registry_path: str | Path, receipts: list[dict[str, Any]], *, parsed_manifest: str | None = None, scope: str = "partial_source") -> dict[str, Any]:
    """Record measured downloads/subsets without promoting unfetched files."""
    record_path = Path(report_dir) / source_id / "registry_record.json"
    row = json.loads(record_path.read_text(encoding="utf-8"))
    combined_receipts = {receipt["original_filename"]: receipt for receipt in row.get("raw_receipts", [])}
    combined_receipts.update({receipt["original_filename"]: receipt for receipt in receipts})
    receipts = list(combined_receipts.values())
    row["raw_receipts"] = receipts
    row["raw_scope"] = scope
    row["raw_verified_bytes"] = sum(receipt.get("bytes", 0) for receipt in receipts)
    row["raw_sha256"] = {receipt["original_filename"]: receipt["sha256"] for receipt in receipts if receipt.get("sha256")}
    row["sha256"] = next(iter(row["raw_sha256"].values())) if len(row["raw_sha256"]) == 1 else None
    fetched = {receipt.get("original_filename") for receipt in receipts}
    row["unfetched_official_files"] = [entry["name"] for entry in row.get("files", []) if entry["name"] not in fetched]
    row["status"] = "parsed" if parsed_manifest else "verified"
    if parsed_manifest:
        row["parsed_manifest"] = parsed_manifest
    write_json(record_path, row)
    registry = {entry["source_id"]: entry for entry in get_local_registry(registry_path)}
    registry[source_id] = row
    save_registry(registry_path, list(registry.values()))
    return row


def discover_matr_test_file(file_name: str, report_dir: str | Path, proxy: str | None = DEFAULT_PROXY) -> dict[str, Any]:
    """Resolve a small original per-test file from the actual project API."""
    destination = Path(report_dir) / "matr"
    registry = json.loads((destination / "registry_record.json").read_text())
    project_url = registry.get("metadata_api")
    if not project_url or "/edp/projects/" not in project_url:
        raise ValueError("MATR current public SPA must resolve the project API first")
    api_base = project_url.split("edp/projects/", 1)[0]
    session = _session(proxy)
    try:
        batches, _ = _get_snapshot(session, project_url + "/batches", destination / "official_batches.json")
        candidates = [batch for batch in batches if file_name.startswith(batch["title"] + "_")]
        for batch in candidates:
            tests_url = project_url + f"/batches/{batch['_id']}/tests"
            tests, receipt = _get_snapshot(session, tests_url, destination / f"official_tests_{batch['title']}.json")
            for test in tests:
                if test.get("name") != file_name.removesuffix(".csv") or not test.get("dataFileId"):
                    continue
                file_id = test["dataFileId"]
                metadata, file_receipt = _get_snapshot(session, api_base + f"file/{file_id}", destination / f"official_test_file_{file_id}.json")
                if metadata["name"] != file_name:
                    continue
                return {"name": metadata["name"], "bytes": metadata["size"], "url": api_base + f"file/{file_id}/download", "author_checksum": None, "original_cell_barcode": test.get("cellId"), "source_test_id": test["_id"], "metadata_receipts": [receipt, file_receipt]}
        raise ValueError("requested per-test filename was not published by the current official project API")
    finally:
        session.close()
