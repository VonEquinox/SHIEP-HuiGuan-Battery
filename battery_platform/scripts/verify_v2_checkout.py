"""Verify committed development packages from a raw-data-free Git archive.

Uses this checkout's installed UV interpreter only for dependencies; all tested
code, manifests and numeric inputs come from the committed archive.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    with tempfile.TemporaryDirectory(prefix="huiguan-committed-checkout-") as temporary:
        root = Path(temporary)
        archive = root / "checkout.tar"
        snapshot = root / "checkout"
        snapshot.mkdir()
        with archive.open("wb") as handle:
            subprocess.run(["git", "archive", revision], cwd=repository, stdout=handle, check=True)
        with tarfile.open(archive) as handle:
            handle.extractall(snapshot, filter="data")
        assert not (snapshot / ".env").exists()
        assert not (snapshot / "model_lab/data/raw/matr").exists()
        assert not (snapshot / "model_lab/data/derived/v2/xjtu_final_20261002").exists()
        packages = sorted((snapshot / "model_lab/reports/v2/packages").glob("*/manifest.json"))
        arguments = []
        for manifest in packages:
            arguments.extend(["--package", str(manifest.parent)])
        expected = {"M1_joint_seed0_complete", "M2_joint_seed0", "M1_multisource_seed0", "M2_multisource_seed0",
                    "M1_matr_lifetime_masked_seed0", "M2_matr_lifetime_masked_seed0"}
        assert expected <= {manifest.parent.name for manifest in packages}, "All six delivered research packages must be committed."
        environment = {**os.environ, "PYTHONPATH": str(snapshot), "BATTERY_LLM_API_KEY": "",
                       "BATTERY_ML_PYTHON": str(Path(sys.executable).absolute())}
        result = subprocess.run([sys.executable, "-m", "model_lab.scripts.v2.verify_package", *arguments],
                                cwd=snapshot, env=environment, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stderr[-4000:])
        verified = json.loads(result.stdout)
        # Exercise the real API/model job using committed inputs and a disposable
        # archive-local DB. This regression performs no cloud or network request.
        check = subprocess.run([sys.executable, "-m", "pytest", "battery_platform/tests/test_v2_workflow.py",
                                "battery_platform/tests/test_v2_package_live.py", "-k",
                                "registered_safe_prediction or package_owned_inputs", "-q"], cwd=snapshot,
                               env=environment, capture_output=True, text=True, timeout=120)
        if check.returncode:
            raise RuntimeError(check.stdout[-4000:] + check.stderr[-4000:])
        evidence = {"schema_version": "committed-checkout-v2", "revision": revision,
                    "contains_local_credentials": False, "requires_raw_or_final_data": False,
                    "dependency_runtime": "existing root UV interpreter",
                    "package_replay": verified, "api_regression": check.stdout.strip(),
                    "temporary_archive_removed": True}
    destination = repository / "battery_platform/reports/v2_integration/committed_checkout.json"
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"revision": revision, "packages": len(packages), "api_regression": evidence["api_regression"],
                      "artifact": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
