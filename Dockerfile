## Stage 1: Build Next.js frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

## Stage 2: Python backend + frontend runner
FROM python:3.11-slim

WORKDIR /app

# Install Node.js for running Next.js standalone server
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install nginx for reverse proxy
RUN apt-get update && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi uvicorn python-dotenv python-multipart \
    openpyxl pymupdf pandas

COPY backend/ ./backend/
COPY data/ ./data/

# Copy Next.js standalone build
COPY --from=frontend-builder /frontend/.next/standalone ./frontend/
COPY --from=frontend-builder /frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /frontend/public ./frontend/public

# Nginx config
COPY nginx.container.conf /etc/nginx/sites-available/default

COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 80

CMD ["./start.sh"]
