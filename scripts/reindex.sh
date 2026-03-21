#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SPECS_DIR="${SPECS_DIR:-$ROOT_DIR/Specs/2025-12/Rel-18}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$ROOT_DIR/artifacts}"
VESPA_APP_DIR="${VESPA_APP_DIR:-$ROOT_DIR/vespa}"
MODEL_DIR="${MODEL_DIR:-$ROOT_DIR/models/Qwen3-Embedding-0.6B}"
DEVICE="${DEVICE:-cuda}"

BASE_URL="${BASE_URL:-http://localhost:8080}"
CONFIG_BASE_URL="${CONFIG_BASE_URL:-http://localhost:19071}"
SCHEMA="${SCHEMA:-spec_finder}"
NAMESPACE="${NAMESPACE:-spec-finder}"

CORPUS_PATH="${CORPUS_PATH:-$ARTIFACTS_DIR/spec_finder_corpus_all.jsonl}"
ENRICHED_PATH="${ENRICHED_PATH:-$ARTIFACTS_DIR/spec_finder_enriched_all.jsonl}"
REGISTRY_PATH="${REGISTRY_PATH:-$ARTIFACTS_DIR/spec_query_registry.json}"
EMBEDDED_PATH="${EMBEDDED_PATH:-$ARTIFACTS_DIR/spec_finder_embedded_all.jsonl}"
VESPA_FEED_PATH="${VESPA_FEED_PATH:-$ARTIFACTS_DIR/spec_finder_vespa_embedded_all.jsonl}"

BATCH_SIZE="${BATCH_SIZE:-16}"
FEED_MAX_WORKERS="${FEED_MAX_WORKERS:-8}"
START_VESPA="${START_VESPA:-0}"

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
Usage: $(basename "$0") [options]

Rebuild corpus, enrich, embeddings, Vespa feed, deploy, wait, and feed.

Options:
  --specs-dir PATH        Source DOCX directory
  --artifacts-dir PATH    Artifact output directory
  --model-dir PATH        Local embedding model directory
  --device DEVICE         Embedding device (default: cuda)
  --base-url URL          Vespa query/feed base URL
  --config-base-url URL   Vespa config URL
  --batch-size N          Embedding batch size
  --feed-max-workers N    Concurrent Vespa feed workers
  --start-vespa           Run docker compose up -d in vespa/
  -h, --help              Show this help

Environment overrides:
  SPECS_DIR ARTIFACTS_DIR VESPA_APP_DIR MODEL_DIR DEVICE
  BASE_URL CONFIG_BASE_URL SCHEMA NAMESPACE
  CORPUS_PATH ENRICHED_PATH REGISTRY_PATH EMBEDDED_PATH VESPA_FEED_PATH
  BATCH_SIZE FEED_MAX_WORKERS START_VESPA
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --specs-dir)
      SPECS_DIR="$2"
      shift 2
      ;;
    --artifacts-dir)
      ARTIFACTS_DIR="$2"
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
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --config-base-url)
      CONFIG_BASE_URL="$2"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="$2"
      shift 2
      ;;
    --feed-max-workers)
      FEED_MAX_WORKERS="$2"
      shift 2
      ;;
    --start-vespa)
      START_VESPA=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$ARTIFACTS_DIR"

echo "Reindex configuration:"
echo "  specs_dir=$SPECS_DIR"
echo "  artifacts_dir=$ARTIFACTS_DIR"
echo "  model_dir=$MODEL_DIR"
echo "  device=$DEVICE"
echo "  base_url=$BASE_URL"
echo "  config_base_url=$CONFIG_BASE_URL"
echo "  feed_max_workers=$FEED_MAX_WORKERS"

if [[ "$START_VESPA" == "1" ]]; then
  echo "Starting Vespa containers"
  run_cmd docker compose -f "$VESPA_APP_DIR/docker-compose.yml" up -d
fi

echo "1/8 build-corpus"
run_cmd python3 -m app.main build-corpus \
  "$SPECS_DIR" \
  --output "$CORPUS_PATH" \
  --overwrite

echo "2/8 enrich-corpus"
run_cmd python3 -m app.main enrich-corpus \
  --input "$CORPUS_PATH" \
  --output "$ENRICHED_PATH"

echo "3/8 build-query-registry"
run_cmd python3 -m app.main build-query-registry \
  --input "$ENRICHED_PATH" \
  --output "$REGISTRY_PATH"

echo "4/8 build-embeddings"
run_cmd python3 -m app.main build-embeddings \
  --input "$ENRICHED_PATH" \
  --output "$EMBEDDED_PATH" \
  --local-model-dir "$MODEL_DIR" \
  --device "$DEVICE" \
  --batch-size "$BATCH_SIZE"

echo "5/8 export-vespa"
run_cmd python3 -m app.main export-vespa \
  --input "$EMBEDDED_PATH" \
  --output "$VESPA_FEED_PATH"

echo "6/8 deploy-vespa-http"
run_cmd python3 -m app.main deploy-vespa-http \
  --app-dir "$VESPA_APP_DIR" \
  --base-url "$BASE_URL" \
  --config-base-url "$CONFIG_BASE_URL" \
  --schema "$SCHEMA" \
  --namespace "$NAMESPACE"

echo "7/8 wait-vespa-http"
run_cmd python3 -m app.main wait-vespa-http \
  --base-url "$BASE_URL" \
  --config-base-url "$CONFIG_BASE_URL" \
  --schema "$SCHEMA" \
  --namespace "$NAMESPACE"

echo "8/8 feed-vespa-http"
run_cmd python3 -m app.main feed-vespa-http \
  --input "$VESPA_FEED_PATH" \
  --base-url "$BASE_URL" \
  --config-base-url "$CONFIG_BASE_URL" \
  --schema "$SCHEMA" \
  --namespace "$NAMESPACE" \
  --max-workers "$FEED_MAX_WORKERS"

echo "Reindex complete."
