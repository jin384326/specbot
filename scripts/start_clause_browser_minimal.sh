#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VESPA_DIR="${VESPA_DIR:-$ROOT_DIR/vespa}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
CONFIG_BASE_URL="${CONFIG_BASE_URL:-http://localhost:19071}"
SCHEMA="${SCHEMA:-spec_finder}"
NAMESPACE="${NAMESPACE:-spec_finder}"
STACK_MODE="${1:-background}"

print_command() {
  printf '+'
  for arg in "$@"; do
    printf ' %q' "$arg"
  done
  printf '\n'
}

run_cmd() {
  print_command "$@"
  "$@"
}

usage() {
  cat <<EOF
Usage: $(basename "$0") [background|foreground]

Start the minimum runtime stack after reboot:
1. Start Vespa containers
2. Wait until Vespa query/config endpoints are ready
3. Start SpecBot Query API + Clause Browser

This script does NOT rebuild corpus, redeploy schema, or feed Vespa again.

Environment overrides:
  VESPA_DIR BASE_URL CONFIG_BASE_URL SCHEMA NAMESPACE
  SPECBOT_QUERY_API_HOST SPECBOT_QUERY_API_PORT
  SPECBOT_CLAUSE_BROWSER_HOST SPECBOT_CLAUSE_BROWSER_PORT
  SPECBOT_STACK_LOG_DIR
EOF
}

case "$STACK_MODE" in
  background|foreground) ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown mode: $STACK_MODE" >&2
    usage >&2
    exit 1
    ;;
esac

echo "Starting Vespa containers without re-feeding"
run_cmd docker compose -f "$VESPA_DIR/docker-compose.yml" up -d

echo "Waiting for Vespa readiness"
run_cmd python3 -m app.main wait-for-vespa-http \
  --base-url "$BASE_URL" \
  --config-base-url "$CONFIG_BASE_URL" \
  --schema "$SCHEMA" \
  --namespace "$NAMESPACE"

echo "Starting Clause Browser stack"
run_cmd "$ROOT_DIR/scripts/run_clause_browser_stack.sh" "$STACK_MODE"

