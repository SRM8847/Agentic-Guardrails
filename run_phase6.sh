#!/usr/bin/env bash
# Phase 6: final evaluation. Usage: ./run_phase6.sh
set -e

cleanup() {
    kill "$FS_PID" "$EMAIL_PID" "$DB_PID" "$OPA_PID" "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT

python3 tools/fs_server/app.py > /tmp/fs.log 2>&1 &    FS_PID=$!
python3 tools/email_mock/app.py > /tmp/email.log 2>&1 & EMAIL_PID=$!
python3 tools/db_mock/app.py > /tmp/db.log 2>&1 &      DB_PID=$!
sleep 2

./opa run --server --addr :8181 policy/rego/guardrail_phase4.rego policy/rego/rules_data.json > /tmp/opa.log 2>&1 &
OPA_PID=$!
sleep 2

POLICY_ENGINE=opa python3 proxy/main.py > /tmp/proxy.log 2>&1 & PROXY_PID=$!
sleep 2

echo "=== tool servers + OPA + proxy up (local mocks, no real AWS) ==="
echo
echo "--- historical regression: Phase 2, 3, 4 still hold ---"
python3 scripts/test_phase2.py
P2=$?
python3 scripts/test_phase3_regression.py
P3=$?
python3 scripts/test_phase4_trifecta.py
P4=$?
echo

echo "--- Phase 6: attack scenarios + fail-closed + latency + concurrency ---"
python3 eval/run_scenarios.py
P6=$?

exit $((P2 + P3 + P4 + P6))
