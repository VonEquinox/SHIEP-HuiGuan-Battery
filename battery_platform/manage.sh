#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export UV_CACHE_DIR="$PWD/runtime/package-cache"
case "${1:-help}" in
 setup)
  uv venv .venv --python ../model_lab/.venv/bin/python
  uv pip sync --python .venv/bin/python requirements.lock
  (cd frontend && npm ci)
  .venv/bin/python -m app.cli init
  ;;
 bootstrap) shift; .venv/bin/python -m app.cli bootstrap "$@" ;;
 user) shift; .venv/bin/python -m app.cli user "$@" ;;
 demo) .venv/bin/python -m app.cli demo ;;
 status) .venv/bin/python -m app.cli status ;;
 backup) .venv/bin/python -m app.cli backup ;;
 restore) shift; .venv/bin/python -m app.cli restore "$@" ;;
 build) (cd frontend && npm run build) ;;
 serve) exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${BATTERY_PORT:-8787}" --workers 1 ;;
 dev) (cd frontend && npm run dev) ;;
 test) .venv/bin/python -m pytest -q tests ;;
 e2e) (cd frontend && PLAYWRIGHT_BROWSERS_PATH=../runtime/browsers npm run test:e2e) ;;
 browsers) (cd frontend && PLAYWRIGHT_BROWSERS_PATH=../runtime/browsers npx playwright install chromium) ;;
 verify-models) .venv/bin/python scripts/verify_real_model_pipeline.py ;;
 *) printf 'Usage: ./manage.sh {setup|bootstrap|user|demo|status|backup|restore|build|serve|dev|test|browsers|e2e|verify-models}\n' ;;
esac
