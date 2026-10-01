"""Audit an immutable V2 data manifest without model fitting/scoring."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from model_lab.modeling.v2.data import audit_manifest, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = audit_manifest(Path(args.manifest))
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
