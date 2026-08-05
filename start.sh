#!/usr/bin/env bash
# Starts both processes for local dev and for Databricks Apps deployment.
#
# FastAPI runs on localhost:8001 only -- it's never exposed externally, and
# deliberately NOT 8000, since Databricks Apps may assign that as the
# externally-exposed port for the Next.js process below. If both processes
# tried to bind the same port, whichever started first would win silently
# and the other would fail to bind -- exactly the kind of failure that's
# invisible until you dig into logs, which is why this script checks and
# reports explicitly rather than trusting it silently worked.
#
# NOTE: the exact env var Databricks Apps injects for "which port to bind
# to" is unconfirmed as of writing -- falling back through a couple of
# likely names, then a hardcoded default. If the deployed app fails to
# bind correctly, check the Databricks Apps docs/UI for the real variable
# name and fix the PORT line below.
set -e

echo "[start.sh] Starting FastAPI backend on 127.0.0.1:8001 ..."
uvicorn backend.main:app --host 127.0.0.1 --port 8001 &
BACKEND_PID=$!

sleep 2
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "[start.sh] FATAL: FastAPI backend (pid $BACKEND_PID) died immediately after starting." >&2
    echo "[start.sh] Check the log output above this line for the actual uvicorn/Python error." >&2
    exit 1
fi

if command -v curl >/dev/null 2>&1; then
    if curl -sf "http://127.0.0.1:8001/health" > /dev/null; then
        echo "[start.sh] FastAPI backend is up and responding on /health."
    else
        echo "[start.sh] FATAL: FastAPI backend process is running but /health did not respond." >&2
        exit 1
    fi
else
    echo "[start.sh] (curl not available -- skipping /health check, process liveness check above passed.)"
fi

INCOMING_PORT="${PORT:-<unset>}"
PORT="${DATABRICKS_APP_PORT:-${PORT:-8080}}"
export PORT
echo "[start.sh] Starting Next.js frontend on port $PORT (DATABRICKS_APP_PORT=${DATABRICKS_APP_PORT:-<unset>}, incoming PORT was ${INCOMING_PORT}) ..."

cd frontend
npm install
npm run build
exec npm run start
