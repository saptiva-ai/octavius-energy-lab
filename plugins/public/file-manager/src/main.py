"""
OctaviOS File Manager Plugin - Main Application

Microservicio híbrido REST + MCP para gestión de archivos.
Proporciona upload, download, extracción de texto y metadatos.

Port: 8001
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import download, health, metadata, upload
from .services.minio_client import init_minio_client, close_minio_client
from .services.redis_client import init_redis_client, close_redis_client

# gRPC server (optional - graceful fallback if not available)
try:
    from .grpc import start_grpc_server, stop_grpc_server

    GRPC_AVAILABLE = True
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
    logger.info(
        "Starting File Manager plugin",
        service=settings.service_name,
        http_port=settings.port,
        grpc_port=settings.grpc_port if settings.grpc_enabled else "disabled",
        minio_endpoint=settings.minio_endpoint,
        grpc_available=GRPC_AVAILABLE,
    )

    # Initialize clients
    await init_minio_client()
    await init_redis_client()

    # Start gRPC server if enabled and available
    grpc_server = None
    if settings.grpc_enabled and GRPC_AVAILABLE and start_grpc_server:
        try:
            grpc_server = await start_grpc_server(port=settings.grpc_port)
            logger.info("gRPC server started", port=settings.grpc_port)
        except Exception as e:
            logger.warning("Failed to start gRPC server", error=str(e))

    yield

    # Cleanup
    logger.info("Shutting down File Manager plugin")

    # Stop gRPC server
    if grpc_server and stop_grpc_server:
        try:
            await stop_grpc_server(grpc_server)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("Failed to stop gRPC server", error=str(e))

    await close_minio_client()
    await close_redis_client()


# Create FastAPI application
app = FastAPI(
    title="OctaviOS File Manager",
    description="Public plugin for file upload, download, and text extraction (REST + MCP)",
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
app.include_router(upload.router, tags=["Upload"])
app.include_router(download.router, tags=["Download"])
app.include_router(metadata.router, tags=["Metadata"])


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "rest": "/docs",
            "health": "/health",
            "upload": "/upload",
            "download": "/download/{file_id}",
            "metadata": "/metadata/{file_id}",
        },
    }
