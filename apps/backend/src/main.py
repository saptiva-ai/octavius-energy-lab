"""
FastAPI application for Copilot OS API.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.auth import get_current_user
from .core.cache_invalidation import start_invalidation_listener
from .core.config import get_settings
from .core.database import Database
from .core.exceptions import (
    APIError,
    api_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .core.logging import setup_logging
from .core.telemetry import (
    increment_tool_invocation,
    instrument_fastapi,
    setup_telemetry,
    shutdown_telemetry,
)
from .middleware.auth import AuthMiddleware
from .middleware.cache_control import CacheControlMiddleware
from .middleware.rate_limit import (
    RateLimitMiddleware,
    _rate_limit_exceeded_handler,
    limiter,
)
from .middleware.telemetry import TelemetryMiddleware
from .routers import (
    artifacts,
    auth,
    chat,
    conversations,
    deep_research,
    documents,
    features,
    feedback,
    files,
    health,
    history,
    intent,
    internal,
    mcp_admin,
    metrics,
    models,
    reports,
    resources,
    review,
    stream,
)
from .routers import settings as settings_router
from .services.llm_semantic_cache import get_llm_semantic_cache
from .services.storage import storage
from .workers.resource_cleanup_worker import get_cleanup_worker

logger = structlog.get_logger(__name__)

# MCP (Model Context Protocol) integration - Using FastMCP (official SDK)
# Note: Using mcp_integration to avoid namespace collision with external 'mcp' package
try:
    from .mcp_integration.fastapi_adapter import MCPFastAPIAdapter
    from .mcp_integration.lazy_routes import create_lazy_mcp_router
    from .mcp_integration.server import mcp as mcp_server
    from .mcp_integration.tasks import task_manager

    _mcp_enabled = True
except (
    ModuleNotFoundError
) as mcp_import_err:  # pragma: no cover - defensive guard for missing SDK deps
    # If fastmcp dependency chain is broken (e.g., mcp.types missing), downgrade gracefully
    structlog.get_logger(__name__).warning(
        "MCP disabled - dependency missing",
        error=str(mcp_import_err),
    )
    mcp_server = None
    MCPFastAPIAdapter = None  # type: ignore
    task_manager = None  # type: ignore
    create_lazy_mcp_router = None  # type: ignore
    _mcp_enabled = False


PURGE_INITIAL_DELAY = 3600  # 1 hour after startup
PURGE_INTERVAL = 86400  # every 24 hours


async def _scheduled_cache_purge() -> None:
    """Run periodically: purge expired + cold entries from LLM semantic cache."""
    await asyncio.sleep(PURGE_INITIAL_DELAY)
    while True:
        try:
            cache = get_llm_semantic_cache()
            if cache:
                expired = await asyncio.to_thread(cache.purge_expired)
                cold = await asyncio.to_thread(cache.purge_cold)
                logger.info(
                    "scheduled_purge.completed",
                    expired_deleted=expired,
                    cold_deleted=cold,
                )
        except Exception as e:
            logger.error("scheduled_purge.error", error=str(e))
        await asyncio.sleep(PURGE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    app_settings = get_settings()
    logger = structlog.get_logger()

    # Setup logging and telemetry
    setup_logging(app_settings.log_level)
    setup_telemetry(app_settings)

    # Connect to MongoDB
    await Database.connect_to_mongo()
    await storage.start_reaper()

    # Start MCP task manager (only if MCP is enabled)
    if _mcp_enabled and task_manager:
        await task_manager.start()

    # Start resource cleanup worker
    cleanup_worker = get_cleanup_worker()
    await cleanup_worker.start()

    # Start cache invalidation listener (Pub/Sub)
    _invalidation_task = None
    try:
        from .core.redis_cache import get_redis_cache

        redis_cache = await get_redis_cache()
        if redis_cache.client:
            _invalidation_task = asyncio.create_task(
                start_invalidation_listener(redis_cache.client)
            )
            logger.info("Cache invalidation listener started")
    except Exception as e:
        logger.warning("Cache invalidation listener not started", error=str(e))

    # Start scheduled cache purge (Weaviate LLM cache)
    _purge_task = asyncio.create_task(_scheduled_cache_purge())
    logger.info(
        "Scheduled cache purge started",
        initial_delay_h=PURGE_INITIAL_DELAY // 3600,
        interval_h=PURGE_INTERVAL // 3600,
    )

    logger.info("Starting Copilot OS API", version=app.version)

    yield

    # Stop scheduled cache purge
    if not _purge_task.done():
        _purge_task.cancel()
        try:
            await _purge_task
        except asyncio.CancelledError:
            pass

    # Stop cache invalidation listener
    if _invalidation_task and not _invalidation_task.done():
        _invalidation_task.cancel()
        try:
            await _invalidation_task
        except asyncio.CancelledError:
            pass

    # Shutdown telemetry
    shutdown_telemetry()

    # Stop resource cleanup worker
    await cleanup_worker.stop()

    # Stop MCP task manager
    if _mcp_enabled and task_manager:
        await task_manager.stop()

    # Close database connection
    await Database.close_mongo_connection()
    await storage.stop_reaper()
    logger.info("Shutting down Copilot OS API")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="OctaviOS Chat API",
        description="Conversational AI API with document review capabilities powered by SAPTIVA models",
        version="1.4.42",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Security middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.parsed_allowed_hosts,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Custom middleware
    app.add_middleware(TelemetryMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CacheControlMiddleware
    )  # ISSUE-023: Prevent caching of API responses

    # Rate limiter state
    app.state.limiter = limiter

    # Exception handlers
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(APIError, api_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # Include routers
    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(intent.router, prefix="/api", tags=["intent"])
    app.include_router(deep_research.router, prefix="/api", tags=["research"])
    app.include_router(stream.router, prefix="/api", tags=["streaming"])
    app.include_router(history.router, prefix="/api", tags=["history"])
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(reports.router, prefix="/api", tags=["reports"])
    app.include_router(metrics.router, prefix="/api", tags=["monitoring"])
    app.include_router(settings_router.router, prefix="/api", tags=["settings"])
    app.include_router(models.router, prefix="/api", tags=["models"])
    app.include_router(features.router, prefix="/api", tags=["features"])
    app.include_router(files.router, prefix="/api", tags=["files"])
    app.include_router(documents.router, prefix="/api", tags=["documents"])
    app.include_router(review.router, prefix="/api", tags=["review"])
    app.include_router(resources.router, prefix="/api", tags=["resources"])
    app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
    app.include_router(feedback.router, prefix="/api", tags=["feedback"])
    app.include_router(internal.router, prefix="/api/internal", tags=["internal"])
    # app.include_router(files.router, prefix="/api", tags=["files"])  # Temporarily disabled - Phase 3

    # MCP integration - Using FastMCP (official SDK) with FastAPI adapter
    # Tools defined in src/mcp/server.py: audit_file, excel_analyzer, viz_tool
    app.state.mcp_server = mcp_server if _mcp_enabled else None

    def _on_mcp_invoke(response):
        """Telemetry callback for tool invocations"""
        try:
            increment_tool_invocation(response["tool"])
        except Exception:  # pragma: no cover - telemetry best-effort
            pass

    # Create adapter to expose FastMCP tools via FastAPI REST endpoints
    mcp_adapter = None
    if _mcp_enabled and MCPFastAPIAdapter:
        mcp_adapter = MCPFastAPIAdapter(
            mcp_server=mcp_server,
            auth_dependency=get_current_user,
            on_invoke=_on_mcp_invoke,
        )

    # Store adapter in app.state for internal tool invocation (Phase 2 MCP integration)
    app.state.mcp_adapter = mcp_adapter

    # Mount MCP routes: GET /api/mcp/tools, POST /api/mcp/invoke, GET /api/mcp/health
    if _mcp_enabled and mcp_adapter:
        app.include_router(
            mcp_adapter.create_router(prefix="/mcp", tags=["mcp"]),
            prefix="/api",
        )

    # Mount MCP lazy loading routes (optimized - 98% context reduction)
    # GET /api/mcp/lazy/discover, GET /api/mcp/lazy/tools/{name}, POST /api/mcp/lazy/invoke
    if _mcp_enabled and create_lazy_mcp_router:
        lazy_mcp_router = create_lazy_mcp_router(
            auth_dependency=get_current_user,
            on_invoke=_on_mcp_invoke,
        )
        app.include_router(lazy_mcp_router, prefix="/api")

    # Mount MCP admin routes for cache management
    # DELETE /api/mcp/cache/*, GET /api/mcp/cache/stats, POST /api/mcp/cache/warmup
    if _mcp_enabled:
        app.include_router(mcp_admin.router, prefix="/api/mcp", tags=["mcp-admin"])

    # Instrument FastAPI for telemetry
    instrument_fastapi(app)

    # --- INICIO BLOQUE TIDEWAVE ---
    # Solo se activa si la variable de entorno está presente
    if os.getenv("TIDEWAVE_ENABLED", "false").lower() == "true":
        try:
            from tidewave.fastapi import Tidewave

            # Configuración crítica para Docker: permitir acceso desde la red interna (Gateway)
            # apps/web (Frontend) y el agente (Host) se conectarán aquí.
            tidewave = Tidewave(config={"allow_remote_access": True})
            tidewave.install(app)
            print("🌊 Tidewave MCP Middleware inyectado correctamente")
            logger.info("tidewave.enabled", allow_remote_access=True)
        except ImportError:
            print(
                "⚠️ TIDEWAVE_ENABLED es True pero el paquete 'tidewave' no está instalado."
            )
            logger.warning("tidewave.import_error")
    # --- FIN BLOQUE TIDEWAVE ---

    return app


app = create_app()


if __name__ == "__main__":
    app_settings = get_settings()
    uvicorn.run(
        "main:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=app_settings.debug,
        log_level=app_settings.log_level.lower(),
    )
