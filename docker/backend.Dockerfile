# ============================================================
# AI Dashboard Generator — Backend Dockerfile
# Multi-stage build: development + production
# ============================================================

# ----- Base Stage -------------------------------------------
FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    # For PDF processing
    poppler-utils \
    # For Excel processing
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----- Development Stage ------------------------------------
FROM base AS development

# Install development dependencies
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application code
COPY --chown=appuser:appgroup . .

# Create upload directory
RUN mkdir -p /app/uploads && chown appuser:appgroup /app/uploads

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ----- Production Stage -------------------------------------
FROM base AS production

# Copy application code
COPY --chown=appuser:appgroup . .

# Create upload directory
RUN mkdir -p /app/uploads && chown appuser:appgroup /app/uploads

# Install gunicorn for production
RUN pip install --no-cache-dir gunicorn

USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["gunicorn", "app.main:app", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--workers", "4", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "120", \
    "--keepalive", "5", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]
