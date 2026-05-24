#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-localhost}"
WEB_PORT="${WEB_PORT:-5173}"
VITE_API_BASE="${VITE_API_BASE:-http://${API_HOST}:${API_PORT}}"

API_PID=""
WEB_PID=""

cleanup() {
  echo
  echo "Stopping dev services..."

  if [[ -n "${API_PID}" ]]; then
    kill "${API_PID}" 2>/dev/null || true
  fi

  if [[ -n "${WEB_PID}" ]]; then
    kill "${WEB_PID}" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Starting backend:"
echo "  http://${API_HOST}:${API_PORT}"
echo

(
  cd "$ROOT/backend"
  uvicorn app.main:app --reload --host "$API_HOST" --port "$API_PORT"
) > >(sed -u 's/^/[api] /') 2> >(sed -u 's/^/[api:err] /' >&2) &
API_PID=$!

echo "Starting frontend:"
echo "  http://${WEB_HOST}:${WEB_PORT}"
echo "  VITE_API_BASE=${VITE_API_BASE}"
echo

(
  cd "$ROOT/frontend"
  VITE_API_BASE="$VITE_API_BASE" npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT"
) > >(sed -u 's/^/[web] /') 2> >(sed -u 's/^/[web:err] /' >&2) &
WEB_PID=$!

echo "Dev environment running."
echo "Press Ctrl+C to stop both."
echo

while true; do
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo
    echo "Backend stopped. Shutting down frontend."
    exit 1
  fi

  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    echo
    echo "Frontend stopped. Shutting down backend."
    exit 1
  fi

  sleep 1
done
