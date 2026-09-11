#!/usr/bin/env bash
# Phase 1 smoke test: start the three tool servers + the proxy, then run
# the harness with PROXY_URL set so it never talks to a tool server directly.
# Usage: ./run_phase1.sh [mock|real]
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

echo "=== tool servers + proxy up (pids: $FS_PID $EMAIL_PID $DB_PID $PROXY_PID) ==="

if [ "$MODE" = "real" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY is not set. Export it first, or run with 'mock'."
    exit 1
fi

PROXY_URL="http://localhost:8000" python3 agent/harness.py --mode "$MODE"
