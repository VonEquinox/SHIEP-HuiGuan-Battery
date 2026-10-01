"""Create development-only, physical-cycle MATR lifetime views."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_lab.modeling.v2.lifetime_features import build_lifetime_feature_bundle, validate_prefix_configuration


def main():
    parser = argparse.ArgumentParser(description="Build qualified MATR physical-cycle views; final/sealed/protected rows remain excluded")
    parser.add_argument("--derived", required=True, help="Already qualified V2 parsed numeric directory")
    parser.add_argument("--out", required=True, help="New immutable output directory")
    parser.add_argument("--query-prefixes", type=int, nargs="+", default=[50, 100, 200], help="Fixed physical query cycles, strictly increasing")
    parser.add_argument("--history", type=int, default=32, help="Visible history bound, at most 32")
    parser.add_argument("--points", type=int, default=256, help="Points per actual curve, at most 256")
    parser.add_argument("--exclude-identity-manifest", help="Prior feature/split JSON metadata; exclude every previously consumed MATR final barcode")
    parser.add_argument("--dry-run", action="store_true", help="Validate arguments and report the plan without opening source tables")
    args = parser.parse_args()
    try:
        queries = validate_prefix_configuration(args.query_prefixes, args.history, args.points)
        if Path(args.out).exists():
            raise FileExistsError("output must be a new directory")
        if not Path(args.derived).is_dir():
            raise FileNotFoundError(args.derived)
        if args.dry_run:
            result = {"dry_run": True, "query_prefixes": list(queries), "history": args.history, "points": args.points,
                      "development_only": True, "source_tables_opened": False, "output": args.out,
                      "exclude_identity_manifest": args.exclude_identity_manifest}
        else:
            manifest = build_lifetime_feature_bundle(args.derived, args.out, query_prefixes=queries, history=args.history, points=args.points,
                                                      exclude_identity_manifest=args.exclude_identity_manifest)
            result = {"rows": len(manifest["rows"]), "censor_counts": manifest["censor_counts"],
                      "exclusion_counts": manifest["exclusion_counts"], "manifest": str(Path(args.out) / "features.json")}
    except (ValueError, FileExistsError, FileNotFoundError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
