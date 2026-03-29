#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CORPUS_PATH="${SPECBOT_CLAUSE_BROWSER_CORPUS:-artifacts/clause_browser_corpus.jsonl}"
CORPUS_ROOT="${SPECBOT_CLAUSE_BROWSER_CORPUS_ROOT:-artifacts/clause_browser_corpora}"
MEDIA_DIR="${SPECBOT_CLAUSE_BROWSER_MEDIA_DIR:-artifacts/clause_browser_media}"
DEFAULT_WORKERS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '1')"
WORKERS="${SPECBOT_CLAUSE_BROWSER_PREPROCESS_WORKERS:-$DEFAULT_WORKERS}"

if [ "$#" -gt 0 ]; then
  INPUT_ARGS=("$@")
else
  INPUT_ARGS=("Specs")
fi

echo "Preprocessing clause browser corpus..."
echo "  root:   $ROOT_DIR"
echo "  inputs: ${INPUT_ARGS[*]}"
echo "  output: $CORPUS_PATH"
echo "  output_root: $CORPUS_ROOT"
echo "  media:  $MEDIA_DIR"
echo "  workers: $WORKERS"

python3 -m app.clause_browser.preprocess \
  --inputs "${INPUT_ARGS[@]}" \
  --output "$CORPUS_PATH" \
  --output-root "$CORPUS_ROOT" \
  --media-dir "$MEDIA_DIR" \
  --workers "$WORKERS"

echo "Preprocess complete."
