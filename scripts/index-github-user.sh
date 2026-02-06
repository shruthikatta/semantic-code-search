#!/usr/bin/env bash
# Index every public Python repository belonging to a GitHub user.
#
# Usage:
#   ./scripts/index-github-user.sh <github-username> [--include-non-python] [--drop]
#
# Examples:
#   ./scripts/index-github-user.sh shruthikatta
#   ./scripts/index-github-user.sh shruthikatta --drop                # rebuild index from scratch
#   ./scripts/index-github-user.sh shruthikatta --include-non-python  # also clone non-Python repos
#                                                                     # (still indexes only .py files)
#
# Requires: git, curl, python3. The backend must already be running:
#   ./scripts/native.sh up

set -euo pipefail

USER_NAME="${1:?Usage: $0 <github-username> [--include-non-python] [--drop]}"
shift

INCLUDE_NON_PY=0
DROP_FIRST=0
for arg in "$@"; do
  case "$arg" in
    --include-non-python) INCLUDE_NON_PY=1 ;;
    --drop)               DROP_FIRST=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLES="$ROOT/samples"
API="${API_BASE:-http://127.0.0.1:8000}"

mkdir -p "$SAMPLES"

color() { printf "\033[1;36m%s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m%s\033[0m\n" "$*"; }
err()   { printf "\033[1;31m%s\033[0m\n" "$*" >&2; }

if ! curl -fsS "$API/health" >/dev/null 2>&1; then
  err "Backend not reachable at $API. Start it with ./scripts/native.sh up"
  exit 1
fi

if [ "$DROP_FIRST" = "1" ]; then
  color "==> Dropping existing index"
  curl -fsS -X DELETE "$API/index" | python3 -m json.tool
fi

color "==> Listing public repos for $USER_NAME"
PAGE=1
declare -a REPOS=()
declare -a LANGS=()
while :; do
  RAW=$(curl -fsS \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/users/$USER_NAME/repos?per_page=100&page=$PAGE&sort=updated")
  COUNT=$(printf '%s' "$RAW" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')
  [ "$COUNT" = "0" ] && break

  while IFS=$'\t' read -r NAME LANG CLONE_URL; do
    REPOS+=("$NAME"$'\t'"$LANG"$'\t'"$CLONE_URL")
  done < <(printf '%s' "$RAW" | python3 -c "
import json, sys
for r in json.load(sys.stdin):
    if r.get('fork') or r.get('archived'):
        continue
    print(f\"{r['name']}\t{r.get('language') or ''}\t{r['clone_url']}\")
")
  PAGE=$((PAGE + 1))
done

if [ ${#REPOS[@]} -eq 0 ]; then
  warn "No repositories found for $USER_NAME (or all are forks/archived)."
  exit 0
fi

color "==> Found ${#REPOS[@]} repo(s):"
for line in "${REPOS[@]}"; do
  IFS=$'\t' read -r NAME LANG _ <<< "$line"
  printf "    - %-50s [%s]\n" "$NAME" "${LANG:-unknown}"
done

INDEXED=0
SKIPPED=0
for line in "${REPOS[@]}"; do
  IFS=$'\t' read -r NAME LANG CLONE_URL <<< "$line"
  TARGET="$SAMPLES/$NAME"

  if [ "$INCLUDE_NON_PY" = "0" ] && [ -n "$LANG" ] && [ "$LANG" != "Python" ] && [ "$LANG" != "Jupyter Notebook" ]; then
    warn "==> Skipping $NAME (primary language: $LANG). Use --include-non-python to clone anyway."
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if [ ! -d "$TARGET" ]; then
    color "==> Cloning $CLONE_URL"
    git clone --depth 1 "$CLONE_URL" "$TARGET"
  else
    color "==> $NAME already cloned at $TARGET"
  fi

  PY_COUNT=$(find "$TARGET" -name '*.py' -not -path '*/.git/*' -not -path '*/node_modules/*' 2>/dev/null | wc -l | tr -d ' ')
  if [ "$PY_COUNT" = "0" ]; then
    warn "    no .py files in $NAME, nothing to index"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  color "==> POST /index for $NAME ($PY_COUNT Python file(s))"
  curl -sS -X POST "$API/index" \
    -H 'Content-Type: application/json' \
    -d "{\"path\": \"$TARGET\", \"repo\": \"$NAME\", \"drop_existing\": false}" \
    --max-time 1800 \
    | python3 -m json.tool
  INDEXED=$((INDEXED + 1))
done

color ""
color "==> Done. Indexed $INDEXED repo(s), skipped $SKIPPED."
color "==> Final stats:"
curl -fsS "$API/index/stats" | python3 -m json.tool
