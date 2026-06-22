#!/bin/bash
set -e

# Start FastAPI backend
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# Start Next.js frontend on port 3000 (App Service overrides PORT to 80 for nginx)
cd /app/frontend && HOSTNAME=0.0.0.0 PORT=3000 node server.js &

# Wait for services to be ready
sleep 2

# Start nginx (foreground to keep container alive)
nginx -g "daemon off;"
