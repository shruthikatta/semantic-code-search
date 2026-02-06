#!/usr/bin/env bash
# Native (no-Docker) controller for the Semantic Code Search stack.
#
#   ./scripts/native.sh setup      Download ES, create venv, install backend + frontend deps
#   ./scripts/native.sh up         Start ES + backend + frontend in the background
#   ./scripts/native.sh down       Stop all background services
#   ./scripts/native.sh status     Show pid/port/health for each service
#   ./scripts/native.sh logs <svc> Tail logs for elasticsearch|backend|frontend
#   ./scripts/native.sh index      Index ./samples/requests (clones it if missing)
#
# Files live under ./.local: tarballs, ES install, pid files, log files.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL="$ROOT/.local"
LOGS="$LOCAL/logs"
PIDS="$LOCAL/pids"
ES_VERSION="8.14.3"
ES_TGZ_URL="https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-${ES_VERSION}-darwin-aarch64.tar.gz"
ES_DIR="$LOCAL/elasticsearch-${ES_VERSION}"
ES_DATA="$LOCAL/es-data"
VENV="$ROOT/backend/.venv"
PY_BIN="$(command -v python3.11 || command -v python3)"

mkdir -p "$LOCAL" "$LOGS" "$PIDS" "$ES_DATA"

color() { printf "\033[1;36m%s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m%s\033[0m\n" "$*"; }
err()   { printf "\033[1;31m%s\033[0m\n" "$*" >&2; }

cmd="${1:-help}"
shift || true

case "$cmd" in
  setup)
    color "==> Using python: $PY_BIN ($($PY_BIN --version))"

    if [ ! -d "$ES_DIR" ]; then
      color "==> Downloading Elasticsearch $ES_VERSION"
      curl -fL -o "$LOCAL/es.tgz" "$ES_TGZ_URL"
      tar -xzf "$LOCAL/es.tgz" -C "$LOCAL"
      rm "$LOCAL/es.tgz"
    else
      color "==> ES already extracted at $ES_DIR"
    fi

    color "==> Configuring Elasticsearch (security disabled, single-node, bound to 127.0.0.1)"
    cat > "$ES_DIR/config/elasticsearch.yml" <<EOF
cluster.name: scs-cluster
node.name: scs-node
network.host: 127.0.0.1
http.port: 9200
discovery.type: single-node
xpack.security.enabled: false
xpack.security.http.ssl.enabled: false
xpack.security.transport.ssl.enabled: false
xpack.ml.enabled: false
path.data: $ES_DATA
EOF
    cat > "$ES_DIR/config/jvm.options.d/heap.options" <<EOF
-Xms1g
-Xmx1g
EOF

    color "==> Creating Python venv"
    "$PY_BIN" -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    color "==> Installing backend requirements (this includes torch; ~1-2 GB, will take a few minutes)"
    "$VENV/bin/pip" install -r "$ROOT/backend/requirements.txt"

    color "==> Installing frontend dependencies"
    (cd "$ROOT/frontend" && npm install --no-audit --no-fund)

    color "==> Setup complete. Next: ./scripts/native.sh up"
    ;;

  up)
    [ -d "$ES_DIR" ]   || { err "Run setup first (no ES at $ES_DIR)"; exit 1; }
    [ -d "$VENV" ]     || { err "Run setup first (no venv at $VENV)"; exit 1; }
    [ -d "$ROOT/frontend/node_modules" ] || { err "Run setup first (no node_modules)"; exit 1; }

    if [ ! -f "$PIDS/es.pid" ] || ! kill -0 "$(cat "$PIDS/es.pid" 2>/dev/null)" 2>/dev/null; then
      color "==> Starting Elasticsearch (logs: $LOGS/elasticsearch.log)"
      ES_JAVA_HOME="$ES_DIR/jdk.app/Contents/Home" \
        nohup "$ES_DIR/bin/elasticsearch" >"$LOGS/elasticsearch.log" 2>&1 &
      echo $! > "$PIDS/es.pid"
    else
      color "==> Elasticsearch already running (pid $(cat "$PIDS/es.pid"))"
    fi

    color "==> Waiting for Elasticsearch to be healthy..."
    for i in $(seq 1 60); do
      if curl -fsS "http://127.0.0.1:9200/_cluster/health" 2>/dev/null | grep -qE '"status":"(yellow|green)"'; then
        color "    healthy after ${i}s"
        break
      fi
      sleep 1
      [ $i -eq 60 ] && { err "ES did not become healthy. See $LOGS/elasticsearch.log"; exit 1; }
    done

    if [ ! -f "$PIDS/backend.pid" ] || ! kill -0 "$(cat "$PIDS/backend.pid" 2>/dev/null)" 2>/dev/null; then
      color "==> Starting backend (logs: $LOGS/backend.log)"
      cd "$ROOT/backend"
      ELASTICSEARCH_URL="http://127.0.0.1:9200" \
      ES_INDEX="code_chunks" \
      EMBEDDING_MODEL="${EMBEDDING_MODEL:-jinaai/jina-embeddings-v2-base-code}" \
      EMBEDDING_DIM="${EMBEDDING_DIM:-768}" \
      EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-auto}" \
      EMBEDDING_TRUST_REMOTE_CODE="${EMBEDDING_TRUST_REMOTE_CODE:-true}" \
      SAMPLES_DIR="$ROOT/samples" \
      HF_HOME="$LOCAL/hf-cache" \
        nohup "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 >"$LOGS/backend.log" 2>&1 &
      echo $! > "$PIDS/backend.pid"
      cd - >/dev/null
    else
      color "==> Backend already running (pid $(cat "$PIDS/backend.pid"))"
    fi

    color "==> Waiting for backend health..."
    for i in $(seq 1 30); do
      if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
        color "    healthy after ${i}s"
        break
      fi
      sleep 1
      [ $i -eq 30 ] && warn "    backend not yet healthy; check $LOGS/backend.log"
    done

    if [ ! -f "$PIDS/frontend.pid" ] || ! kill -0 "$(cat "$PIDS/frontend.pid" 2>/dev/null)" 2>/dev/null; then
      color "==> Starting frontend (logs: $LOGS/frontend.log)"
      cd "$ROOT/frontend"
      NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://localhost:8000}" \
        nohup npm run dev >"$LOGS/frontend.log" 2>&1 &
      echo $! > "$PIDS/frontend.pid"
      cd - >/dev/null
    else
      color "==> Frontend already running (pid $(cat "$PIDS/frontend.pid"))"
    fi

    sleep 2
    color ""
    color "All services launching. Open http://localhost:3000"
    color "Backend docs:  http://localhost:8000/docs"
    color "ES health:     http://localhost:9200/_cluster/health"
    ;;

  down)
    for svc in frontend backend es; do
      pidf="$PIDS/$svc.pid"
      if [ -f "$pidf" ]; then
        pid=$(cat "$pidf")
        if kill -0 "$pid" 2>/dev/null; then
          color "==> Stopping $svc (pid $pid)"
          kill "$pid" 2>/dev/null || true
          for _ in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
          done
          kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pidf"
      fi
    done
    color "All stopped."
    ;;

  status)
    for svc in es backend frontend; do
      pidf="$PIDS/$svc.pid"
      if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
        printf "  %-9s pid=%s  RUNNING\n" "$svc" "$(cat "$pidf")"
      else
        printf "  %-9s              stopped\n" "$svc"
      fi
    done
    echo
    curl -fsS "http://127.0.0.1:9200/_cluster/health" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "ES: unreachable"
    echo
    curl -fsS "http://127.0.0.1:8000/health"          2>/dev/null | python3 -m json.tool 2>/dev/null || echo "Backend: unreachable"
    ;;

  logs)
    svc="${1:-}"
    case "$svc" in
      es|elasticsearch) tail -n 80 -f "$LOGS/elasticsearch.log" ;;
      backend)          tail -n 80 -f "$LOGS/backend.log" ;;
      frontend)         tail -n 80 -f "$LOGS/frontend.log" ;;
      *) err "Usage: $0 logs <es|backend|frontend>"; exit 2 ;;
    esac
    ;;

  index)
    REPO_URL="${1:-https://github.com/psf/requests.git}"
    REPO_NAME="${2:-requests}"
    SAMPLES="$ROOT/samples"
    mkdir -p "$SAMPLES"
    if [ ! -d "$SAMPLES/$REPO_NAME" ]; then
      color "==> Cloning $REPO_URL into samples/$REPO_NAME"
      git clone --depth 1 "$REPO_URL" "$SAMPLES/$REPO_NAME"
    fi
    color "==> POST /index for $SAMPLES/$REPO_NAME (this triggers model download on first run)"
    curl -fsS -X POST "http://127.0.0.1:8000/index" \
      -H 'Content-Type: application/json' \
      -d "{\"path\": \"$SAMPLES/$REPO_NAME\", \"repo\": \"$REPO_NAME\", \"drop_existing\": true}" \
      | python3 -m json.tool
    ;;

  help|*)
    sed -n '2,12p' "$0"
    ;;
esac
