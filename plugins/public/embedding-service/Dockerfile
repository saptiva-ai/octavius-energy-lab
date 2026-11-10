# =============================================================================
# OctaviOS Embedding Service Plugin - Dockerfile (UV + PyTorch CPU)
# =============================================================================
# Public plugin for text embedding generation (sentence-transformers)
# Port: 8002
# Size: ~1.15GB (torch CPU-only + sentence-transformers model)
#
# OPTIMIZATION: PyTorch CPU-only to avoid CUDA/nvidia (~5GB savings)
# Model: paraphrase-multilingual-MiniLM-L12-v2 (384 dims, ~120MB)
# =============================================================================

# =============================================================================
# STAGE 1: UV Builder
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UV Configuration
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first (Docker cache optimization)
COPY plugins/public/embedding-service/requirements.txt .

# Install dependencies with PyTorch CPU-only
# Step 1: Install torch CPU-only FIRST (prevents nvidia deps)
# Step 2: Install remaining dependencies
ARG TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install \
        --index-url ${TORCH_CPU_INDEX_URL} \
        --index-strategy unsafe-best-match \
        torch torchvision torchaudio && \
    uv pip install \
        --index-strategy unsafe-best-match \
        --extra-index-url ${TORCH_CPU_INDEX_URL} \
        -r requirements.txt

# =============================================================================
# STAGE 2: Runtime
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

# Metadata
LABEL maintainer="Saptiva Team <dev@saptiva.com>"
LABEL description="OctaviOS Embedding Service - Text to Vector conversion"
LABEL version="1.0.0"

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Activate venv by modifying PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8003 \
    GRPC_PORT=50053

# Runtime dependencies (minimal - no CUDA)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy source code FIRST (then proto generation won't be overwritten)
COPY plugins/public/embedding-service/src/ ./src/

# Copy proto files and generate gRPC code AFTER source copy
# This ensures generated files aren't overwritten by placeholder __init__.py
COPY plugins/public/embedding-service/proto/ ./proto/
RUN mkdir -p ./src/grpc/generated && \
    python -m grpc_tools.protoc -I./proto \
        --python_out=./src/grpc/generated \
        --grpc_python_out=./src/grpc/generated \
        ./proto/embedding_service.proto

# Create non-root user for security (commented for development)
# RUN useradd --create-home --shell /bin/bash --uid 1001 plugin_user && \
#     chown -R plugin_user:plugin_user /app
# USER plugin_user

# Expose ports: HTTP + gRPC
EXPOSE 8003 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Start server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]
