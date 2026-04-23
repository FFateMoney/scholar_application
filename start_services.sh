#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.run_logs"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-4173}"

mkdir -p "$LOG_DIR"

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

if ! command -v uvicorn >/dev/null 2>&1; then
  echo "uvicorn was not found. Please activate the scholar_app environment first." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found." >&2
  exit 1
fi

cleanup() {
  local exit_code=$?
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  wait "${BACKEND_PID:-}" 2>/dev/null || true
  wait "${FRONTEND_PID:-}" 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup INT TERM EXIT

echo "Starting backend at http://$BACKEND_HOST:$BACKEND_PORT"
(
  cd "$BACKEND_DIR"
  exec uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

echo "Starting frontend at http://$FRONTEND_HOST:$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  exec python3 -m http.server "$FRONTEND_PORT" --bind "$FRONTEND_HOST"
) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

sleep 1

echo
echo "Services are starting."
echo "Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "Backend:  http://$BACKEND_HOST:$BACKEND_PORT"
echo "Backend log:  $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo
echo "Press Ctrl+C to stop both services."

wait -n "$BACKEND_PID" "$FRONTEND_PID"
