#!/usr/bin/env bash
# Multiplatform execution script for nexcoder (Linux / macOS).
# Supports starting the application locally or in containers, running test suites,
# and configuring pluggable database connectivity.

set -euo pipefail

MODE="${1:-local}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

if [ -n "${DB_URL:-}" ]; then
    echo "[nexcoder] Pluggable database configured: ${DB_URL}"
fi

case "$MODE" in
    local)
        echo "[nexcoder] Starting application locally on http://${HOST}:${PORT}..."
        exec nexcoder serve --transport sse --host "$HOST" --port "$PORT" --api
        ;;
    docker)
        echo "[nexcoder] Starting application and database with Docker Compose..."
        exec docker compose up --build
        ;;
    test)
        echo "[nexcoder] Running offline verification tests..."
        exec python -m pytest packages
        ;;
    stop)
        echo "[nexcoder] Stopping Docker Compose services..."
        exec docker compose down
        ;;
    *)
        echo "Usage: $0 [local|docker|test|stop]"
        exit 1
        ;;
esac
