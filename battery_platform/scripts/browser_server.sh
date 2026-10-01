#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
export BATTERY_PORT=8791
export BATTERY_RUNTIME="$PWD/runtime/browser-$(date +%s)-$$"
export BATTERY_DISABLE_WORKER=0
export BATTERY_LLM_API_KEY=
browser_python="../.venv/bin/python"
if [[ ! -x "$browser_python" ]]; then browser_python=".venv/bin/python"; fi
"$browser_python" scripts/bootstrap_browser.py
exec "$browser_python" -m uvicorn app.main:app --host 127.0.0.1 --port 8791 --workers 1
