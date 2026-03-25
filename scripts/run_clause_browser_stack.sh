#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

QUERY_HOST="${SPECBOT_QUERY_API_HOST:-0.0.0.0}"
QUERY_PORT="${SPECBOT_QUERY_API_PORT:-8010}"
BROWSER_HOST="${SPECBOT_CLAUSE_BROWSER_HOST:-0.0.0.0}"
BROWSER_PORT="${SPECBOT_CLAUSE_BROWSER_PORT:-8000}"
QUERY_URL="${SPECBOT_QUERY_API_URL:-http://127.0.0.1:${QUERY_PORT}}"
LOG_DIR="${SPECBOT_STACK_LOG_DIR:-/tmp}"
MODE="${1:-foreground}"

export SPECBOT_QUERY_API_URL="$QUERY_URL"

run_background() {
  mkdir -p "$LOG_DIR"
  nohup python3 -m uvicorn app.specbot_query_server:create_app --factory --host "$QUERY_HOST" --port "$QUERY_PORT" \
    > "${LOG_DIR}/specbot-query.log" 2>&1 &
  QUERY_PID=$!

  nohup python3 -m uvicorn app.clause_browser.server:create_app --factory --host "$BROWSER_HOST" --port "$BROWSER_PORT" \
    > "${LOG_DIR}/clause-browser.log" 2>&1 &
  BROWSER_PID=$!

  echo "Started SpecBot Query API  pid=${QUERY_PID}  log=${LOG_DIR}/specbot-query.log"
  echo "Started Clause Browser     pid=${BROWSER_PID}  log=${LOG_DIR}/clause-browser.log"
  echo "Clause Browser URL: http://<server-ip>:${BROWSER_PORT}/clause-browser/"
}

run_foreground() {
  python3 -m uvicorn app.specbot_query_server:create_app --factory --host "$QUERY_HOST" --port "$QUERY_PORT" &
  QUERY_PID=$!

  cleanup() {
    if kill -0 "$QUERY_PID" >/dev/null 2>&1; then
      kill "$QUERY_PID" >/dev/null 2>&1 || true
    fi
  }
  trap cleanup EXIT INT TERM

  python3 -m uvicorn app.clause_browser.server:create_app --factory --host "$BROWSER_HOST" --port "$BROWSER_PORT"
}

case "$MODE" in
  background|--background)
    run_background
    ;;
  foreground|--foreground|"")
    run_foreground
    ;;
  *)
    echo "Usage: $0 [foreground|background]" >&2
    exit 1
    ;;
esac
