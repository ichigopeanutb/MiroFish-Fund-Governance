#!/usr/bin/env bash

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_TIME="$(date +%s)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$ROOT/.formal_harness/runs/$RUN_ID"
mkdir -p "$RUN_DIR"

CHECKS_PASSED=0
CHECKS_FAILED=0

run_check() {
  local name="$1"
  shift
  local log_path="$RUN_DIR/$name.log"

  printf '[formal-eval] %s\n' "$name"
  if "$@" >"$log_path" 2>&1; then
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
    printf '  PASS (%s)\n' "$log_path"
  else
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    printf '  FAIL (%s)\n' "$log_path"
    tail -40 "$log_path"
  fi
}

cd "$ROOT"

run_check "git-diff-check" git diff --check
run_check "backend-business-tests" env PYTHONPATH="$ROOT/backend" backend/.venv/bin/pytest -q backend/tests/test_business_simulation.py
run_check "business-public-alpha-smoke" backend/.venv/bin/python scripts/business_governance_public_alpha_smoke.py
run_check "frontend-production-build" npm --prefix frontend run build

END_TIME="$(date +%s)"
RUNTIME=$((END_TIME - START_TIME))
TOTAL=$((CHECKS_PASSED + CHECKS_FAILED))
if [[ "$TOTAL" -eq 0 ]]; then
  SCORE=0
else
  SCORE=$((CHECKS_PASSED * 100 / TOTAL))
fi

if [[ "$CHECKS_FAILED" -eq 0 ]]; then
  STATUS="pass"
else
  STATUS="fail"
fi

{
  printf 'EVAL_STATUS=%s\n' "$STATUS"
  printf 'EVAL_SCORE=%s\n' "$SCORE"
  printf 'EVAL_CHECKS_PASSED=%s\n' "$CHECKS_PASSED"
  printf 'EVAL_CHECKS_FAILED=%s\n' "$CHECKS_FAILED"
  printf 'EVAL_RUNTIME_SECONDS=%s\n' "$RUNTIME"
  printf 'EVAL_RUN_DIR=%s\n' "$RUN_DIR"
} | tee "$RUN_DIR/summary.env"

if [[ "$CHECKS_FAILED" -ne 0 ]]; then
  exit 1
fi
