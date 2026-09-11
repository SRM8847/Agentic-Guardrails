#!/usr/bin/env bash
# Phase 3 smoke test: start tool servers + OPA + the OPA-backed proxy,
# run the Python-vs-OPA regression check, re-run Phase 2's own end-to-end
# test against the new engine, then optionally run the harness.
# Usage: ./run_phase3.sh [mock|real]
set -e
MODE="${1:-mock}"

cleanup() {
    kill "$FS_PID" "$EMAIL_PID" "$DB_PID" "$OPA_PID" "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT

python3 tools/fs_server/app.py > /tmp/fs.log 2>&1 &    FS_PID=$!
python3 tools/email_mock/app.py > /tmp/email.log 2>&1 & EMAIL_PID=$!
python3 tools/db_mock/app.py > /tmp/db.log 2>&1 &      DB_PID=$!
sleep 2

./opa run --server --addr :8181 policy/rego/guardrail_phase3.rego policy/rego/rules_data.json > /tmp/opa.log 2>&1 &
OPA_PID=$!
sleep 1

POLICY_ENGINE=opa python3 proxy/main.py > /tmp/proxy.log 2>&1 & PROXY_PID=$!
sleep 1

echo "=== tool servers + OPA + OPA-backed proxy up ==="
echo
echo "--- unit-level regression: python engine vs opa engine ---"
python3 scripts/test_phase3_regression.py
REGRESSION_STATUS=$?
echo

echo "--- end-to-end: Phase 2's own test, now against the OPA-backed proxy ---"
python3 scripts/test_phase2.py
E2E_STATUS=$?
echo

if [ "$MODE" = "real" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY is not set. Skipping harness run."
    exit $((REGRESSION_STATUS + E2E_STATUS))
fi

echo "--- harness run through the OPA-backed proxy ---"
PROXY_URL="http://localhost:8000" python3 agent/harness.py --mode "$MODE"

exit $((REGRESSION_STATUS + E2E_STATUS))
