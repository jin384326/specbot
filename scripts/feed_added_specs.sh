#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ARTIFACTS_DIR="${ARTIFACTS_DIR:-$ROOT_DIR/artifacts}"
MODEL_DIR="${MODEL_DIR:-$ROOT_DIR/models/Qwen3-Embedding-0.6B}"
DEVICE="${DEVICE:-cuda}"

BASE_URL="${BASE_URL:-http://localhost:8080}"
CONFIG_BASE_URL="${CONFIG_BASE_URL:-http://localhost:19071}"
SCHEMA="${SCHEMA:-spec_finder}"
NAMESPACE="${NAMESPACE:-spec-finder}"
GLOBAL_ENRICHED_PATH="${GLOBAL_ENRICHED_PATH:-$ARTIFACTS_DIR/spec_finder_enriched_all.jsonl}"
ENRICHED_OVERLAY_PATH="${ENRICHED_OVERLAY_PATH:-$ARTIFACTS_DIR/spec_finder_enriched_overlay.jsonl}"
REGISTRY_PATH="${REGISTRY_PATH:-$ARTIFACTS_DIR/spec_query_registry.json}"
REGISTRIES_DIR="${REGISTRIES_DIR:-$ARTIFACTS_DIR/spec_query_registries}"

BATCH_SIZE="${BATCH_SIZE:-16}"
FEED_MAX_WORKERS="${FEED_MAX_WORKERS:-8}"

RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
INCREMENTAL_DIR="${INCREMENTAL_DIR:-$ARTIFACTS_DIR/incremental/$RUN_ID}"
CORPUS_PATH="$INCREMENTAL_DIR/spec_finder_corpus_incremental.jsonl"
ENRICHED_PATH="$INCREMENTAL_DIR/spec_finder_enriched_incremental.jsonl"
EMBEDDED_PATH="$INCREMENTAL_DIR/spec_finder_embedded_incremental.jsonl"
VESPA_FEED_PATH="$INCREMENTAL_DIR/spec_finder_vespa_incremental.jsonl"

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
Usage: $(basename "$0") <input...>

Build corpus/enriched/embeddings/feed only for the newly added specs you pass in.
Inputs can be files, directories, or glob patterns.

Examples:
  $(basename "$0") Specs/2024-09 Specs/2024-12
  $(basename "$0") Specs/2024-12/Rel-18
  $(basename "$0") Specs/2024-12/Rel-18/29512-i90.docx

Environment overrides:
  ARTIFACTS_DIR MODEL_DIR DEVICE
  BASE_URL CONFIG_BASE_URL SCHEMA NAMESPACE
  BATCH_SIZE FEED_MAX_WORKERS RUN_ID INCREMENTAL_DIR
EOF
}

if [[ "$#" -lt 1 ]]; then
  usage >&2
  exit 1
fi

INPUT_ARGS=("$@")
mkdir -p "$INCREMENTAL_DIR"

echo "Incremental feed configuration:"
echo "  inputs=${INPUT_ARGS[*]}"
echo "  incremental_dir=$INCREMENTAL_DIR"
echo "  model_dir=$MODEL_DIR"
echo "  device=$DEVICE"
echo "  base_url=$BASE_URL"
echo "  config_base_url=$CONFIG_BASE_URL"
echo "  feed_max_workers=$FEED_MAX_WORKERS"

echo "1/5 build-corpus"
run_cmd python3 -m app.main build-corpus \
  "${INPUT_ARGS[@]}" \
  --output "$CORPUS_PATH" \
  --overwrite

echo "2/5 enrich-corpus"
run_cmd python3 -m app.main enrich-corpus \
  --input "$CORPUS_PATH" \
  --output "$ENRICHED_PATH"

if [[ -f "$ENRICHED_OVERLAY_PATH" ]]; then
  cat "$ENRICHED_PATH" >> "$ENRICHED_OVERLAY_PATH"
else
  cp "$ENRICHED_PATH" "$ENRICHED_OVERLAY_PATH"
fi

REGISTRY_INPUTS=()
if [[ -f "$GLOBAL_ENRICHED_PATH" ]]; then
  REGISTRY_INPUTS+=("$GLOBAL_ENRICHED_PATH")
fi
REGISTRY_INPUTS+=("$ENRICHED_OVERLAY_PATH")

echo "3/6 build-query-registries"
run_cmd python3 -m app.release_registry_builder \
  --inputs "${REGISTRY_INPUTS[@]}" \
  --global-output "$REGISTRY_PATH" \
  --output-root "$REGISTRIES_DIR"

echo "4/6 build-embeddings"
run_cmd python3 -m app.main build-embeddings \
  --input "$ENRICHED_PATH" \
  --output "$EMBEDDED_PATH" \
  --local-model-dir "$MODEL_DIR" \
  --device "$DEVICE" \
  --batch-size "$BATCH_SIZE"

echo "5/6 export-vespa"
run_cmd python3 -m app.main export-vespa \
  --input "$EMBEDDED_PATH" \
  --output "$VESPA_FEED_PATH"

echo "6/6 feed-vespa-http"
run_cmd python3 -m app.main feed-vespa-http \
  --input "$VESPA_FEED_PATH" \
  --base-url "$BASE_URL" \
  --config-base-url "$CONFIG_BASE_URL" \
  --schema "$SCHEMA" \
  --namespace "$NAMESPACE" \
  --max-workers "$FEED_MAX_WORKERS"

echo "Incremental feed complete."
echo "Artifacts written under: $INCREMENTAL_DIR"
