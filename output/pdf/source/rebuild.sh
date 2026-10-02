#!/usr/bin/env bash
set -euo pipefail
report_source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$report_source_dir/assemble_report.py"
uv run --locked --script "$report_source_dir/build_report.py"
uv run --locked --script "$report_source_dir/verify_report.py"
