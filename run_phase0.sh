#!/usr/bin/env bash
# Phase 0 smoke test: start the three tool servers, run the harness, tear down.
# Usage: ./run_phase0.sh [mock|real]
set -e
MODE="${1:-mock}"

cleanup() {
    kill "$FS_PID" "$EMAIL_PID" "$DB_PID" 2>/dev/null || true
}
trap cleanup EXIT

python3 tools/fs_server/app.py > /tmp/fs.log 2>&1 &   FS_PID=$!
python3 tools/email_mock/app.py > /tmp/email.log 2>&1 & EMAIL_PID=$!
python3 tools/db_mock/app.py > /tmp/db.log 2>&1 &     DB_PID=$!

sleep 2
echo "=== tool servers up (pids: $FS_PID $EMAIL_PID $DB_PID) ==="

if [ "$MODE" = "real" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY is not set. Export it first, or run with 'mock'."
    exit 1
fi

python3 agent/harness.py --mode "$MODE"

