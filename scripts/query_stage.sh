#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE_URL="${BASE_URL:-http://localhost:8080}"
CONFIG_BASE_URL="${CONFIG_BASE_URL:-http://localhost:19071}"
LIMIT="${LIMIT:-4}"
SUMMARY="${SUMMARY:-short}"
REGISTRY_PATH="${REGISTRY_PATH:-$ROOT_DIR/artifacts/spec_query_registry.json}"
MODEL_DIR="${MODEL_DIR:-$ROOT_DIR/models/Qwen3-Embedding-0.6B}"
DEVICE="${DEVICE:-cuda}"
SPARSE_BOOST="${SPARSE_BOOST:-0}"
VECTOR_BOOST="${VECTOR_BOOST:-1}"
STAGE_FILTER="${STAGE_FILTER:-stage2}"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

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
Usage: $(basename "$0") [options] <query>

Run query-vespa-http with project defaults.

Arguments:
  query                     User query string

Options:
  --base-url URL            Vespa base URL
  --config-base-url URL     Vespa config URL
  --limit N                 Requested hit count
  --summary NAME            Vespa summary profile
  --registry PATH           Query registry path
  --model-dir PATH          Local embedding model directory
  --device DEVICE           Embedding device
  --sparse-boost VALUE      Sparse score boost
  --vector-boost VALUE      Vector score boost
  --stage-filter VALUE      stage2, stage3, or else
  -h, --help                Show this help

Environment overrides:
  BASE_URL CONFIG_BASE_URL LIMIT SUMMARY REGISTRY_PATH
  MODEL_DIR DEVICE SPARSE_BOOST VECTOR_BOOST STAGE_FILTER
EOF
}

QUERY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --config-base-url)
      CONFIG_BASE_URL="$2"
      shift 2
      ;;
    --limit)
      LIMIT="$2"
      shift 2
      ;;
    --summary)
      SUMMARY="$2"
      shift 2
      ;;
    --registry)
      REGISTRY_PATH="$2"
      shift 2
      ;;
    --model-dir)
      MODEL_DIR="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --sparse-boost)
      SPARSE_BOOST="$2"
      shift 2
      ;;
    --vector-boost)
      VECTOR_BOOST="$2"
      shift 2
      ;;
    --stage-filter)
      STAGE_FILTER="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "$QUERY" ]]; then
        echo "Only one query argument is supported." >&2
        usage >&2
        exit 1
      fi
      QUERY="$1"
      shift
      ;;
  esac
done

if [[ -z "$QUERY" ]]; then
  echo "Query is required." >&2
  usage >&2
  exit 1
fi

CMD=(
  python3 -m app.main query-vespa-http
  --query "$QUERY"
  --base-url "$BASE_URL"
  --config-base-url "$CONFIG_BASE_URL"
  --limit "$LIMIT"
  --summary "$SUMMARY"
  --registry "$REGISTRY_PATH"
  --local-model-dir "$MODEL_DIR"
  --device "$DEVICE"
  --sparse-boost "$SPARSE_BOOST"
  --vector-boost "$VECTOR_BOOST"
  --stage-filter "$STAGE_FILTER"
)

START_EPOCH="$(date +%s)"
echo "Start time: $(timestamp)"
run_cmd "${CMD[@]}"
END_EPOCH="$(date +%s)"
echo "End time: $(timestamp)"
echo "Elapsed: $((END_EPOCH - START_EPOCH))s"
