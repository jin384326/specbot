#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CORPUS_PATH="${SPECBOT_CLAUSE_BROWSER_CORPUS:-artifacts/clause_browser_corpus.jsonl}"
MEDIA_DIR="${SPECBOT_CLAUSE_BROWSER_MEDIA_DIR:-artifacts/clause_browser_media}"

if [ "$#" -gt 0 ]; then
  INPUT_ARGS=("$@")
else
  INPUT_ARGS=("Specs")
fi

echo "Preprocessing clause browser corpus..."
echo "  root:   $ROOT_DIR"
echo "  inputs: ${INPUT_ARGS[*]}"
echo "  output: $CORPUS_PATH"
echo "  media:  $MEDIA_DIR"

python3 -m app.clause_browser.preprocess \
  --inputs "${INPUT_ARGS[@]}" \
  --output "$CORPUS_PATH" \
  --media-dir "$MEDIA_DIR"

echo "Preprocess complete."
