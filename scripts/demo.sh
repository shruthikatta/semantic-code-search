#!/usr/bin/env bash
# Indexes a real OSS Python repo into the running stack and runs side-by-side
# BM25-only vs hybrid queries to show the relevance difference.
#
# Usage: ./scripts/demo.sh [REPO_URL] [REPO_NAME]
set -euo pipefail

REPO_URL="${1:-https://github.com/psf/requests.git}"
REPO_NAME="${2:-requests}"
API="${API_BASE:-http://localhost:8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLES="$ROOT/samples"

mkdir -p "$SAMPLES"

if [ ! -d "$SAMPLES/$REPO_NAME" ]; then
  echo "==> Cloning $REPO_URL into samples/$REPO_NAME"
  git clone --depth 1 "$REPO_URL" "$SAMPLES/$REPO_NAME"
fi

echo "==> Triggering /index for /samples/$REPO_NAME (path inside the backend container)"
curl -fsS -X POST "$API/index" \
  -H 'Content-Type: application/json' \
  -d "{\"path\": \"/samples/$REPO_NAME\", \"repo\": \"$REPO_NAME\", \"drop_existing\": true}" \
  | python3 -m json.tool

queries=(
  "retry with exponential backoff"
  "parse HTTP chunked transfer encoding"
  "thread-safe LRU cache"
  "walk a directory tree skipping hidden files"
)

for q in "${queries[@]}"; do
  echo
  echo "============================================================"
  echo "QUERY: $q"
  echo "============================================================"
  for mode in bm25 hybrid; do
    echo
    echo "-- mode=$mode (top 3) --"
    enc=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$q")
    curl -fsS "$API/search?q=$enc&k=3&mode=$mode&repo=$REPO_NAME" \
      | python3 -c "
import json, sys
d = json.load(sys.stdin)
for i, h in enumerate(d['hits'], 1):
    print(f\"  {i}. [{h['symbol_kind']}] {h['qualified_name']}  ({h['file_path']}:{h['start_line']}-{h['end_line']})  score={h['score']:.4f}\")
"
  done
done

echo
echo "==> Stats:"
curl -fsS "$API/index/stats" | python3 -m json.tool
