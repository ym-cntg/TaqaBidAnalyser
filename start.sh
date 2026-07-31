#!/usr/bin/env bash
# Starts both processes for local dev and for Databricks Apps deployment.
#
# FastAPI runs on localhost:8000 only -- it's never exposed externally.
# Next.js is the one process bound to the externally-exposed port, and
# proxies /api/* to FastAPI server-side (see frontend/next.config.ts).
#
# NOTE: the exact env var Databricks Apps injects for "which port to bind
# to" is unconfirmed as of writing -- falling back through a couple of
# likely names, then a hardcoded default. If the deployed app fails to
# bind correctly, check the Databricks Apps docs/UI for the real variable
# name and fix the PORT line below -- everything else should be unaffected.
set -e

uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

PORT="${DATABRICKS_APP_PORT:-${PORT:-8080}}"
export PORT

cd frontend
npm install
npm run build
npm run start
