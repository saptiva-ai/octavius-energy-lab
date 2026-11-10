# =========================================
# MULTI-STAGE DOCKERFILE FOR FASTAPI BACKEND (UV-OPTIMIZED)
# =========================================
# Performance: Build time reduced from ~90s to ~5s (cached) via uv + mount cache
# Size: ~6GB with runtime deps (was 13GB with sentence-transformers)
#
# OPTIMIZATION 2026-01: Use requirements-runtime.txt by default
# - Removes ~7GB of ML dependencies (torch, nvidia, sentence-transformers)
# - Embeddings delegated to embedding-service plugin
# =========================================

# =========================================
# STAGE 1: UV Builder (Heavy - Has compilers and uv)
# =========================================
FROM python:3.11-slim-bookworm AS builder

# Copy uv binary from official image (zero latency, no curl needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UV Configuration: Compile bytecode for faster startup, copy mode for isolation
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install build dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements (runtime by default, full for local dev with embeddings)
# Use BUILD_MODE=full to include sentence-transformers
ARG BUILD_MODE=runtime
COPY requirements.txt requirements-runtime.txt ./

# THE MAGIC: Install dependencies using uv with Docker mount cache
# --mount=type=cache: Persists uv cache between builds on host machine
# Result: Second build takes ~2-5 seconds instead of 90 seconds
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    if [ "$BUILD_MODE" = "full" ]; then \
        echo "Installing FULL requirements (with sentence-transformers)..." && \
        uv pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt; \
    else \
        echo "Installing RUNTIME requirements (lightweight, ~7GB smaller)..." && \
        uv pip install -r requirements-runtime.txt; \
    fi

# =========================================
# STAGE 2: Development Runtime (With hot reload)
# =========================================
FROM python:3.11-slim-bookworm AS development

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy uv binary from builder for installing dev dependencies
COPY --from=builder /bin/uv /bin/uvx /bin/

# Activate venv by modifying PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

# Install runtime + development dependencies
# MVP-OCR: tesseract for image text extraction
# COPILOTO-AUDIT: OpenCV for logo detection (dev packages for debugging)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install dev dependencies (pytest, black, etc.)
COPY requirements-dev.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r requirements-dev.txt

# Copy application code (last for cache optimization)
COPY . .

# Non-root user disabled for development (volume mount permissions)
# In production, use the production stage below

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with hot reload (uvicorn --reload)
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =========================================
# STAGE 3: Production Runtime (Optimized - No dev tools)
# =========================================
FROM python:3.11-slim-bookworm AS production

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Activate venv by modifying PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

# Install ONLY runtime dependencies (MVP-OCR + COPILOTO-AUDIT)
# OPTIMIZED: No -dev packages, only runtime libraries
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy application code (last for cache optimization)
COPY . .

# Create non-root user for security (production only)
RUN useradd --create-home --shell /bin/bash --uid 1001 api_user && \
    chown -R api_user:api_user /app
USER api_user

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with production workers (no reload)
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
