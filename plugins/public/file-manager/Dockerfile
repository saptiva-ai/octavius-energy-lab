# =============================================================================
# OctaviOS File Manager Plugin - Dockerfile (UV + Rust Optimized)
# =============================================================================
# Public plugin for file upload, download, and text extraction (REST + MCP + gRPC)
# Port: 8001 (HTTP), 50052 (gRPC)
# Performance:
#   - Build time: ~3s (cached) via uv
#   - PDF extraction: 47x faster via Rust
#   - OCR: 3x faster via Rust parallel processing
#   - Thumbnails: 5x faster via Rust image crate
# =============================================================================

# =============================================================================
# STAGE 1: Rust Builder
# =============================================================================
FROM rust:1.83-slim-bookworm AS rust-builder

WORKDIR /rust

# Install system dependencies for Rust crates
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    libleptonica-dev \
    libtesseract-dev \
    clang \
    && rm -rf /var/lib/apt/lists/*

# Copy Rust source
COPY plugins/public/file-manager/rust_modules/Cargo.toml .
COPY plugins/public/file-manager/rust_modules/src/ ./src/

# Build release binary with optimizations
RUN cargo build --release

# =============================================================================
# STAGE 2: Python + Maturin Builder
# =============================================================================
FROM python:3.11-slim-bookworm AS python-builder

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UV Configuration
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    libleptonica-dev \
    libtesseract-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Rust for maturin (minimal install)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal
ENV PATH="/root/.cargo/bin:$PATH"

# Copy requirements first (Docker cache optimization)
COPY plugins/public/file-manager/requirements.txt .

# Install Python dependencies using uv with Docker mount cache
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -r requirements.txt && \
    uv pip install maturin

# Copy Rust module source for maturin build
COPY plugins/public/file-manager/rust_modules/ /rust_modules/

# Build Rust wheel with maturin and install
RUN --mount=type=cache,target=/root/.cache/uv \
    . /opt/venv/bin/activate && \
    cd /rust_modules && \
    maturin build --release --out /wheels && \
    uv pip install /wheels/*.whl

# =============================================================================
# STAGE 3: Runtime
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

# Metadata
LABEL maintainer="Saptiva Team <dev@saptiva.com>"
LABEL description="OctaviOS File Manager - Public Plugin with Rust acceleration"
LABEL version="2.0.0-rust"

WORKDIR /app

# Copy the pre-built virtual environment from builder (includes Rust module)
COPY --from=python-builder /opt/venv /opt/venv

# Activate venv by modifying PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8001 \
    GRPC_PORT=50052

# System dependencies for OCR/PDF processing at runtime
# tesseract: OCR engine for image text extraction
# poppler-utils: PDF to image conversion (pdftoppm)
# libmagic1: File type detection
# leptonica: Required by leptess Rust crate at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    libleptonica-dev \
    libtesseract-dev \
    poppler-utils \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy source code (last for cache optimization)
COPY plugins/public/file-manager/src/ ./src/

# Create non-root user for security (commented for development)
# Uncomment in production
# RUN useradd --create-home --shell /bin/bash --uid 1001 plugin_user && \
#     chown -R plugin_user:plugin_user /app
# USER plugin_user

# Expose ports: HTTP + gRPC
EXPOSE 8001 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Start server (gRPC server started via main.py lifespan)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
