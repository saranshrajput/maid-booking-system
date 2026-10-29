#!/usr/bin/env bash
# Starts a fresh in-memory server, runs the UI test, stops the server.
set -e
PORT="${PORT:-8765}"
PY="${PYTHON:-python}"
cd "$(dirname "$0")/.."
"$PY" -m uvicorn maidbooking.api:app --port "$PORT" >/tmp/ui-e2e-server.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT
for _ in $(seq 1 30); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 0.3; done
BASE="http://127.0.0.1:$PORT" node e2e/ui.e2e.js
