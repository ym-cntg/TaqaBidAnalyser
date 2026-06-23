FROM python:3.11-slim

WORKDIR /app

# Install system deps for openpyxl/pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Install all Python dependencies from pyproject.toml
RUN pip install --no-cache-dir \
    fastapi uvicorn python-dotenv python-multipart \
    openpyxl pymupdf pandas \
    anthropic azure-ai-documentintelligence azure-core

COPY backend/ ./backend/
COPY data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
