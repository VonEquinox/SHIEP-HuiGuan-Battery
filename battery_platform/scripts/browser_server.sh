#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
export BATTERY_PORT=8791
export BATTERY_RUNTIME="$PWD/runtime/browser-$(date +%s)-$$"
export BATTERY_DISABLE_WORKER=0
.venv/bin/python scripts/bootstrap_browser.py
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8791 --workers 1
