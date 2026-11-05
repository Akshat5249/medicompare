#!/usr/bin/env bash
# Runs every gate from a freshly built stack. Each gate's full output goes to verification/logs/.
# A gate is PASS only if its command exits 0 here, in this run.
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="verification/logs"; mkdir -p "$LOGS"
STATUS="verification/gate_status.tsv"; : > "$STATUS"
gate() { # name command...
  local name="$1"; shift
  local log="$LOGS/$name.log"
  echo "=== $name"
  { echo "\$ $*"; date -u; } > "$log"
  local start=$SECONDS
  if "$@" >> "$log" 2>&1; then result=PASS; else result=FAIL; fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$result" "$((SECONDS - start))" "$*" >> "$STATUS"
  echo "    $result ($((SECONDS - start))s)"
}
[[ -d frontend/node_modules ]] || (cd frontend && npm ci)
[[ -d backend/.venv ]] || (cd backend && uv sync --frozen)
(cd frontend && npx playwright install chromium) >/dev/null 2>&1
if [[ "${FRESH:-1}" == "1" ]]; then docker compose --profile test down -v >/dev/null 2>&1; fi
# All E2E and load traffic comes from one address, so per-address limits are raised for this run.
# test_rate_limit_* proves the limits themselves work.
export RATE_LIMIT_PUBLIC_PER_MINUTE=100000 RATE_LIMIT_AUTH_PER_MINUTE=10000 RATE_LIMIT_UPLOAD_PER_HOUR=10000
gate build_stack docker compose up -d --build --wait
gate seed_demo_users docker compose exec -T backend python -m app.cli seed-demo-users
gate lint make -s lint
gate types make -s types
gate backend_tests make -s test-backend
gate safety_suite make -s test-safety
gate frontend_tests make -s test-frontend
gate smoke make -s smoke
gate data_quality make -s data-check
gate e2e_accessibility make -s e2e
gate demo_media backend/.venv/bin/python scripts/collect_demo.py
gate performance make -s perf
gate backup_restore make -s backup-test
gate security make -s security
gate zap_baseline bash scripts/zap_baseline.sh
gate prod_config docker compose --env-file scripts/prod.env.check -f docker-compose.yml -f docker-compose.prod.yml config --quiet
backend/.venv/bin/python scripts/make_report.py
gate docs make -s docs-check
backend/.venv/bin/python scripts/make_report.py
awk -F'\t' '{printf "%-20s %s\n",$1,$2}' "$STATUS"
! grep -q $'\tFAIL\t' "$STATUS"
