#!/usr/bin/env bash
# Phase 4 smoke test. Usage: ./run_phase4.sh [mock|real]
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

# Note: guardrail_phase4.rego now, not guardrail_phase3.rego -- this is
# the one change that actually turns trifecta enforcement on.
./opa run --server --addr :8181 policy/rego/guardrail_phase4.rego policy/rego/rules_data.json > /tmp/opa.log 2>&1 &
OPA_PID=$!
sleep 1

POLICY_ENGINE=opa python3 proxy/main.py > /tmp/proxy.log 2>&1 & PROXY_PID=$!
sleep 1

echo "=== tool servers + OPA (phase 4 rego) + proxy up ==="
echo
echo "--- trifecta walk: none -> partial -> tripped, plus session isolation ---"
python3 scripts/test_phase4_trifecta.py
TRIFECTA_STATUS=$?
echo

echo "--- Phase 2's own end-to-end test, unaffected since it never trips the trifecta ---"
python3 scripts/test_phase2.py
E2E_STATUS=$?
echo

if [ "$MODE" = "real" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY is not set. Skipping harness run."
    exit $((TRIFECTA_STATUS + E2E_STATUS))
fi

echo "--- harness run (its own session, unaffected by the tests above) ---"
PROXY_URL="http://localhost:8000" python3 agent/harness.py --mode "$MODE"

exit $((TRIFECTA_STATUS + E2E_STATUS))
