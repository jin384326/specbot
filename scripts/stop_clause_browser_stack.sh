#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

QUERY_PATTERN='app.specbot_query_server:create_app'
BROWSER_PATTERN='app.clause_browser.server:create_app'
WAIT_SECONDS="${SPECBOT_STACK_STOP_WAIT_SECONDS:-5}"

matching_pids() {
  local pattern="$1"
  pgrep -f "$pattern" 2>/dev/null | grep -vw "$$" || true
}

stop_pattern() {
  local pattern="$1"
  local pids
  pids="$(matching_pids "$pattern")"
  if [[ -n "$pids" ]]; then
    xargs -r kill <<<"$pids" >/dev/null 2>&1 || true
  fi
}

has_pattern() {
  local pattern="$1"
  [[ -n "$(matching_pids "$pattern")" ]]
}

force_stop_pattern() {
  local pattern="$1"
  local pids
  pids="$(matching_pids "$pattern")"
  if [[ -n "$pids" ]]; then
    xargs -r kill -9 <<<"$pids" >/dev/null 2>&1 || true
  fi
}

stop_pattern "$BROWSER_PATTERN"
stop_pattern "$QUERY_PATTERN"

deadline=$((SECONDS + WAIT_SECONDS))
while (( SECONDS < deadline )); do
  if ! has_pattern "$BROWSER_PATTERN" && ! has_pattern "$QUERY_PATTERN"; then
    break
  fi
  sleep 0.2
done

if has_pattern "$BROWSER_PATTERN"; then
  force_stop_pattern "$BROWSER_PATTERN"
fi

if has_pattern "$QUERY_PATTERN"; then
  force_stop_pattern "$QUERY_PATTERN"
fi

echo "Stopped Clause Browser stack."
