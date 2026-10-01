#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root="$PWD"
export PYTHONDONTWRITEBYTECODE=1
export BATTERY_RUNTIME="${BATTERY_RUNTIME:-$repo_root/battery_platform/runtime/v2-demo}"
export BATTERY_ML_PYTHON="${BATTERY_ML_PYTHON:-$repo_root/.venv/bin/python}"
export BATTERY_LLM_PROXY="${BATTERY_LLM_PROXY:-http://127.0.0.1:7897}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
case "${1:-help}" in
  install)
    export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
    export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7897}"
    uv sync --frozen --python 3.12
    (cd battery_platform/frontend && npm ci --proxy "$HTTP_PROXY" && npm run build)
    (cd battery_platform && "$repo_root/.venv/bin/python" -m app.cli init)
    ;;
  serve)
    cd battery_platform
    exec "$repo_root/.venv/bin/python" -m uvicorn app.main:app --host "${BATTERY_HOST:-127.0.0.1}" --port "${BATTERY_PORT:-8787}" --workers 1
    ;;
  test) exec "$repo_root/.venv/bin/python" -m pytest "${@:2}" ;;
  bootstrap|user|demo|status|backup|restore)
    command="$1"; shift
    cd battery_platform
    exec "$repo_root/.venv/bin/python" -m app.cli "$command" "$@"
    ;;
  *) printf 'Usage: scripts/v2.sh {install|serve|test|bootstrap|user|demo|status|backup|restore}\n' ;;
esac
