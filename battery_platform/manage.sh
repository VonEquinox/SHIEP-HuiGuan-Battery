#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
platform_repo_root="$(cd .. && pwd)"
if [[ -f "$platform_repo_root/.env" ]]; then set -a; source "$platform_repo_root/.env"; set +a; fi
if [[ -n "${BATTERY_RUNTIME:-}" && "$BATTERY_RUNTIME" != /* ]]; then
 export BATTERY_RUNTIME="$platform_repo_root/$BATTERY_RUNTIME"
fi
if [[ -n "${BATTERY_ML_PYTHON:-}" && "$BATTERY_ML_PYTHON" != /* ]]; then
 export BATTERY_ML_PYTHON="$platform_repo_root/$BATTERY_ML_PYTHON"
fi
export PYTHONDONTWRITEBYTECODE=1
export UV_CACHE_DIR="$PWD/runtime/package-cache"
platform_python="../.venv/bin/python"
if [[ ! -x "$platform_python" ]]; then platform_python=".venv/bin/python"; fi
case "${1:-help}" in
 setup)
  exec ../scripts/v2.sh install
  ;;
 bootstrap) shift; "$platform_python" -m app.cli bootstrap "$@" ;;
 user) shift; "$platform_python" -m app.cli user "$@" ;;
 demo) "$platform_python" -m app.cli demo ;;
 status) "$platform_python" -m app.cli status ;;
 backup) "$platform_python" -m app.cli backup ;;
 restore) shift; "$platform_python" -m app.cli restore "$@" ;;
 build) (cd frontend && npm run build) ;;
 serve) exec "$platform_python" -m uvicorn app.main:app --host 127.0.0.1 --port "${BATTERY_PORT:-8787}" --workers 1 ;;
 dev) (cd frontend && npm run dev) ;;
 test) BATTERY_LLM_API_KEY= "$platform_python" -m pytest -q tests ;;
 e2e) (cd frontend && PLAYWRIGHT_BROWSERS_PATH=../runtime/browsers npm run test:e2e) ;;
 browsers) (cd frontend && PLAYWRIGHT_BROWSERS_PATH=../runtime/browsers npx playwright install chromium) ;;
 verify-models) "$platform_python" scripts/verify_real_model_pipeline.py ;;
 *) printf 'Usage: ./manage.sh {setup|bootstrap|user|demo|status|backup|restore|build|serve|dev|test|browsers|e2e|verify-models}\n' ;;
esac
