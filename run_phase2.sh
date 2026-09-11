#!/usr/bin/env bash
# Phase 2 smoke test: start tool servers + proxy, run the policy checks,
# then optionally run the harness through the (now enforcing) proxy.
# Usage: ./run_phase2.sh [mock|real]
set -e
MODE="${1:-mock}"

cleanup() {
    kill "$FS_PID" "$EMAIL_PID" "$DB_PID" "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT

python3 tools/fs_server/app.py > /tmp/fs.log 2>&1 &    FS_PID=$!
python3 tools/email_mock/app.py > /tmp/email.log 2>&1 & EMAIL_PID=$!
python3 tools/db_mock/app.py > /tmp/db.log 2>&1 &      DB_PID=$!
sleep 2

python3 proxy/main.py > /tmp/proxy.log 2>&1 &          PROXY_PID=$!
sleep 1

echo "=== tool servers + policy-enforcing proxy up ==="
echo
echo "--- policy checks ---"
python3 scripts/test_phase2.py
POLICY_STATUS=$?
echo

if [ "$MODE" = "real" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY is not set. Skipping harness run (policy checks above still count)."
    exit $POLICY_STATUS
fi

echo "--- harness run through the enforcing proxy ---"
PROXY_URL="http://localhost:8000" python3 agent/harness.py --mode "$MODE"

exit $POLICY_STATUS
