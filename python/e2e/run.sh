#!/usr/bin/env bash
# Runs the browser tests, each against a fresh server: the main flow on the real clock, hold expiry on a clock the
# test moves, then "Book now" on a server with a fixed clock (daytime and night). Set DATABASE_URL to run against Postgres (empty database).
set -e
PORT="${PORT:-8765}"
PY="${PYTHON:-python}"
cd "$(dirname "$0")/.."
PIDS=""
trap 'kill $PIDS 2>/dev/null' EXIT
start() { "$@" >/tmp/ui-e2e-server.log 2>&1 & PIDS="$PIDS $!"; }
wait_for() { for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$1/health" >/dev/null && return; sleep 0.3; done; echo "server on $1 did not start"; exit 1; }
truncate_db() {
  [ -n "$DATABASE_URL" ] && "$PY" -c "
import os; from sqlalchemy import text; from maidbooking.sql_persistence import create_db_engine, create_schema
e = create_db_engine(os.environ['DATABASE_URL']); create_schema(e)
with e.begin() as c: c.execute(text('TRUNCATE idempotency_keys, payments, booking_occurrences, bookings, maid_services, maids'))" || true
}

truncate_db
start "$PY" -m uvicorn maidbooking.api:app --port "$PORT"; MAIN=$!
wait_for "$PORT"
BASE="http://127.0.0.1:$PORT" node e2e/ui.e2e.js
kill $MAIN 2>/dev/null || true

# Hold expiry: the clock is a file the test moves forward.
CLOCK_FILE="${CLOCK_FILE:-/tmp/hold-e2e-clock.txt}"; export CLOCK_FILE; rm -f "$CLOCK_FILE"
truncate_db
start "$PY" e2e/fixed_clock_server.py 2030-01-08T10:00:00 "$((PORT + 1))" "$CLOCK_FILE"; HOLD=$!
wait_for "$((PORT + 1))"
BASE="http://127.0.0.1:$((PORT + 1))" node e2e/hold.e2e.js
kill $HOLD 2>/dev/null || true
sleep 0.5

for scenario in "day 2030-01-08T10:07:30" "night 2030-01-08T21:00:00"; do
  set -- $scenario
  truncate_db
  start "$PY" e2e/fixed_clock_server.py "$2" "$((PORT + 1))"; FIXED=$!
  wait_for "$((PORT + 1))"
  SCENARIO="$1" BASE="http://127.0.0.1:$((PORT + 1))" node e2e/instant.e2e.js
  kill $FIXED 2>/dev/null || true
  sleep 0.5
done
