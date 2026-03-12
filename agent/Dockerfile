FROM python:3.11-slim

WORKDIR /app

# Install system deps for pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY agent/pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source code
COPY agent/src/ src/

# Railway injects PORT env var (default 8000)
ENV PORT=8000

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port $PORT"]
