"""
OctaviOS Embedding Service Plugin - Main Application

Microservicio híbrido REST + gRPC para generacion de embeddings.
Endpoints REST: /encode, /encode-single, /chunk-and-embed
gRPC: EmbeddingService (see proto/embedding_service.proto)

Ports: 8003 (HTTP), 50053 (gRPC)
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import embeddings, health

# gRPC server (optional - graceful fallback if not available)
try:
    from .grpc import start_grpc_server, stop_grpc_server, GRPC_AVAILABLE
except ImportError:
    GRPC_AVAILABLE = False
    start_grpc_server = None
    stop_grpc_server = None

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    grpc_port = 50053  # Default gRPC port

    logger.info(
        "Starting Embedding Service plugin",
        service=settings.service_name,
        http_port=settings.port,
        grpc_port=grpc_port if GRPC_AVAILABLE else "disabled",
        model=settings.model_name,
        device=settings.device,
        grpc_available=GRPC_AVAILABLE,
    )

    # Start gRPC server if available
    grpc_server = None
    if GRPC_AVAILABLE and start_grpc_server:
        try:
            grpc_server = await start_grpc_server(port=grpc_port)
            logger.info("gRPC server started", port=grpc_port)
        except Exception as e:
            logger.warning("Failed to start gRPC server", error=str(e))

    yield

    # Cleanup
    logger.info("Shutting down Embedding Service plugin")

    # Stop gRPC server
    if grpc_server and stop_grpc_server:
        try:
            await stop_grpc_server(grpc_server)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("Failed to stop gRPC server", error=str(e))


# Create FastAPI application
app = FastAPI(
    title="OctaviOS Embedding Service",
    description="Plugin for text embedding generation using sentence-transformers",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(embeddings.router, prefix="/embeddings", tags=["Embeddings"])


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "model": settings.model_name,
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "encode": "/embeddings/encode",
            "encode_single": "/embeddings/encode-single",
            "chunk_and_embed": "/embeddings/chunk-and-embed",
        },
    }
