"""
Advanced telemetry and observability module for Copilotos Bridge.

This module provides comprehensive monitoring capabilities including:
- Custom metrics for Deep Research operations
- Request/response tracking with Prometheus
- Performance monitoring
- Error tracking with detailed context
- Business logic metrics
- OpenTelemetry integration
"""

import time
import traceback
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, AsyncIterator, Callable, Dict, Optional

import structlog
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = structlog.get_logger(__name__)

# Create custom registry for better metric isolation
CUSTOM_REGISTRY = CollectorRegistry()

# ============================================================================
# CORE METRICS
# ============================================================================

# Request metrics
REQUEST_COUNT = Counter(
    "copilotos_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=CUSTOM_REGISTRY,
)

REQUEST_DURATION = Histogram(
    "copilotos_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=CUSTOM_REGISTRY,
)

# ============================================================================
# DEEP RESEARCH METRICS
# ============================================================================

RESEARCH_REQUESTS = Counter(
    "copilotos_research_requests_total",
    "Total deep research requests",
    ["intent_type", "classification_method"],
    registry=CUSTOM_REGISTRY,
)

RESEARCH_DURATION = Histogram(
    "copilotos_research_duration_seconds",
    "Deep research operation duration",
    ["research_phase", "success"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=CUSTOM_REGISTRY,
)

RESEARCH_QUALITY = Gauge(
    "copilotos_research_quality_score",
    "Research quality score (0-1)",
    ["research_type"],
    registry=CUSTOM_REGISTRY,
)

INTENT_CLASSIFICATION = Counter(
    "copilotos_intent_classification_total",
    "Intent classification results",
    ["intent_type", "confidence_level", "method"],
    registry=CUSTOM_REGISTRY,
)

# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

ACTIVE_CONNECTIONS = Gauge(
    "copilotos_active_connections",
    "Number of active connections",
    registry=CUSTOM_REGISTRY,
)

MEMORY_USAGE = Gauge(
    "copilotos_memory_usage_bytes",
    "Memory usage in bytes",
    ["type"],
    registry=CUSTOM_REGISTRY,
)

CACHE_OPERATIONS = Counter(
    "copilotos_cache_operations_total",
    "Cache operations",
    ["operation", "backend", "hit"],
    registry=CUSTOM_REGISTRY,
)

# Document ingestion metrics
PDF_INGEST_DURATION = Histogram(
    "copilotos_pdf_ingest_seconds",
    "PDF ingestion phase duration",
    ["phase"],
    buckets=[0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0],
    registry=CUSTOM_REGISTRY,
)

PDF_INGEST_ERRORS = Counter(
    "copilotos_pdf_ingest_errors_total",
    "PDF ingestion errors by code",
    ["code"],
    registry=CUSTOM_REGISTRY,
)

# OBS-1: Document text size metric
DOC_TEXT_SIZE_CHARS = Histogram(
    "copilotos_doc_text_size_chars",
    "Extracted document text size in characters",
    ["mimetype"],
    buckets=[500, 1000, 2500, 5000, 10000, 20000, 50000, 100000],
    registry=CUSTOM_REGISTRY,
)

# OBS-1: Documents used in chat metric
DOCS_USED_TOTAL = Counter(
    "copilotos_docs_used_total",
    "Total documents used in chat context",
    ["chat_id"],
    registry=CUSTOM_REGISTRY,
)

# OBS-1: Chat completion latency metric
CHAT_COMPLETION_SECONDS = Histogram(
    "copilotos_chat_completion_seconds",
    "Chat LLM completion latency",
    ["model", "has_documents"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0],
    registry=CUSTOM_REGISTRY,
)

# OBS-1: LLM timeout counter
CHAT_LLM_TIMEOUT_TOTAL = Counter(
    "copilotos_chat_llm_timeout_total",
    "Total LLM call timeouts",
    ["model"],
    registry=CUSTOM_REGISTRY,
)

TOOL_INVOCATIONS = Counter(
    "copilotos_tool_invocations_total",
    "Tool invocations grouped by key",
    ["tool"],
    registry=CUSTOM_REGISTRY,
)


def record_pdf_ingest_phase(phase: str, duration_seconds: float) -> None:
    """Record ingestion phase duration."""
    try:
        PDF_INGEST_DURATION.labels(phase=phase).observe(duration_seconds)
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning("Failed to record pdf_ingest phase", error=str(exc), phase=phase)


def increment_pdf_ingest_error(code: str) -> None:
    """Increment ingestion error counter."""
    try:
        PDF_INGEST_ERRORS.labels(code=code).inc()
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning("Failed to record pdf_ingest error", error=str(exc), code=code)


def increment_tool_invocation(tool_key: str) -> None:
    """Register a tool invocation."""
    try:
        TOOL_INVOCATIONS.labels(tool=tool_key).inc()
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning(
            "Failed to record tool invocation", error=str(exc), tool=tool_key
        )


# OBS-1: New helper functions for PDF→Chat metrics
def record_doc_text_size(mimetype: str, size_chars: int) -> None:
    """Record extracted document text size."""
    try:
        DOC_TEXT_SIZE_CHARS.labels(mimetype=mimetype).observe(size_chars)
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning(
            "Failed to record doc text size", error=str(exc), mimetype=mimetype
        )


def increment_docs_used(chat_id: str, count: int = 1) -> None:
    """Increment documents used in chat counter."""
    try:
        DOCS_USED_TOTAL.labels(chat_id=chat_id).inc(count)
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning("Failed to record docs used", error=str(exc), chat_id=chat_id)


def record_chat_completion_latency(
    model: str, duration_seconds: float, has_documents: bool
) -> None:
    """Record chat LLM completion latency."""
    try:
        CHAT_COMPLETION_SECONDS.labels(
            model=model, has_documents=str(has_documents).lower()
        ).observe(duration_seconds)
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning(
            "Failed to record chat completion latency", error=str(exc), model=model
        )


def increment_llm_timeout(model: str) -> None:
    """Increment LLM timeout counter."""
    try:
        CHAT_LLM_TIMEOUT_TOTAL.labels(model=model).inc()
    except Exception as exc:  # pragma: no cover - best-effort metric
        logger.warning("Failed to record LLM timeout", error=str(exc), model=model)


# ============================================================================
# ERROR TRACKING
# ============================================================================

ERROR_COUNT = Counter(
    "copilotos_errors_total",
    "Total application errors",
    ["error_type", "endpoint", "severity"],
    registry=CUSTOM_REGISTRY,
)

# ============================================================================
# BUSINESS METRICS
# ============================================================================

USER_SESSIONS = Gauge(
    "copilotos_active_user_sessions",
    "Number of active user sessions",
    registry=CUSTOM_REGISTRY,
)

API_RATE_LIMITS = Counter(
    "copilotos_rate_limit_hits_total",
    "Rate limit violations",
    ["endpoint", "user_id"],
    registry=CUSTOM_REGISTRY,
)

EXTERNAL_API_CALLS = Counter(
    "copilotos_external_api_calls_total",
    "External API calls",
    ["service", "endpoint", "status"],
    registry=CUSTOM_REGISTRY,
)

EXTERNAL_API_DURATION = Histogram(
    "copilotos_external_api_duration_seconds",
    "External API call duration",
    ["service", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=CUSTOM_REGISTRY,
)

TOOL_TOGGLE_EVENTS = Counter(
    "copilotos_tool_toggle_total",
    "Tool toggles triggered by users",
    ["tool", "state"],
    registry=CUSTOM_REGISTRY,
)

TOOL_CALL_BLOCKED = Counter(
    "copilotos_tool_call_blocked_total",
    "Blocked tool call attempts",
    ["tool", "reason"],
    registry=CUSTOM_REGISTRY,
)

PLANNER_TOOL_SUGGESTED = Counter(
    "copilotos_planner_tool_suggested_total",
    "Planner tool suggestions emitted",
    ["tool"],
    registry=CUSTOM_REGISTRY,
)


class TelemetryManager:
    """Advanced telemetry manager for comprehensive observability."""

    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self._start_times: Dict[str, float] = {}

    @asynccontextmanager
    async def track_operation(
        self, operation_name: str, labels: Optional[Dict[str, str]] = None
    ):
        """Context manager to track operation duration and status."""
        labels = labels or {}
        start_time = time.time()

        try:
            yield
            # Success case
            duration = time.time() - start_time
            if "research" in operation_name.lower():
                RESEARCH_DURATION.labels(
                    research_phase=labels.get("phase", "unknown"), success="true"
                ).observe(duration)

            self.logger.info(
                "Operation completed",
                operation=operation_name,
                duration=duration,
                **labels,
            )

        except Exception as e:
            # Error case
            duration = time.time() - start_time
            error_type = type(e).__name__

            if "research" in operation_name.lower():
                RESEARCH_DURATION.labels(
                    research_phase=labels.get("phase", "unknown"), success="false"
                ).observe(duration)

            ERROR_COUNT.labels(
                error_type=error_type,
                endpoint=labels.get("endpoint", "unknown"),
                severity="error",
            ).inc()

            self.logger.error(
                "Operation failed",
                operation=operation_name,
                duration=duration,
                error=str(e),
                error_type=error_type,
                traceback=traceback.format_exc(),
                **labels,
            )
            raise

    def track_request(
        self, method: str, endpoint: str, status_code: int, duration: float
    ):
        """Track HTTP request metrics."""
        REQUEST_COUNT.labels(
            method=method, endpoint=endpoint, status_code=str(status_code)
        ).inc()

        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    def track_intent_classification(
        self, intent_type: str, confidence: float, method: str
    ):
        """Track intent classification metrics."""
        confidence_level = (
            "high" if confidence > 0.8 else "medium" if confidence > 0.5 else "low"
        )

        INTENT_CLASSIFICATION.labels(
            intent_type=intent_type, confidence_level=confidence_level, method=method
        ).inc()

    def track_research_request(self, intent_type: str, classification_method: str):
        """Track deep research request."""
        RESEARCH_REQUESTS.labels(
            intent_type=intent_type, classification_method=classification_method
        ).inc()

    def track_external_api_call(
        self, service: str, endpoint: str, status: str, duration: float
    ):
        """Track external API calls."""
        EXTERNAL_API_CALLS.labels(
            service=service, endpoint=endpoint, status=status
        ).inc()

        EXTERNAL_API_DURATION.labels(service=service, endpoint=endpoint).observe(
            duration
        )

    def track_cache_operation(self, operation: str, backend: str, hit: bool):
        """Track cache operations."""
        CACHE_OPERATIONS.labels(
            operation=operation, backend=backend, hit="hit" if hit else "miss"
        ).inc()

    def update_research_quality(self, research_type: str, quality_score: float):
        """Update research quality metrics."""
        RESEARCH_QUALITY.labels(research_type=research_type).set(quality_score)

    def increment_active_connections(self):
        """Increment active connections."""
        ACTIVE_CONNECTIONS.inc()

    def decrement_active_connections(self):
        """Decrement active connections."""
        ACTIVE_CONNECTIONS.dec()

    def update_memory_usage(self, memory_type: str, bytes_used: int):
        """Update memory usage metrics."""
        MEMORY_USAGE.labels(type=memory_type).set(bytes_used)

    def update_active_sessions(self, count: int):
        """Update active user sessions."""
        USER_SESSIONS.set(count)

    def track_rate_limit_hit(self, endpoint: str, user_id: str):
        """Track rate limit violations."""
        API_RATE_LIMITS.labels(endpoint=endpoint, user_id=user_id).inc()


# Global telemetry manager instance
telemetry = TelemetryManager()


class MetricsCollector:
    """Enhanced metrics collector with actual Prometheus integration."""

    def __init__(self):
        self.telemetry = telemetry

    def get_request_count(self) -> int:
        """Get total request count from Prometheus metrics."""
        return int(sum([metric.samples[0].value for metric in REQUEST_COUNT.collect()]))

    def get_error_count(self) -> int:
        """Get total error count from Prometheus metrics."""
        return int(sum([metric.samples[0].value for metric in ERROR_COUNT.collect()]))

    def get_active_connections(self) -> int:
        """Get active connection count."""
        try:
            return int(next(ACTIVE_CONNECTIONS.collect()).samples[0].value)
        except (StopIteration, IndexError):
            return 0

    def record_request(
        self, method: str, endpoint: str, status_code: int, duration: float
    ) -> None:
        """Record request metrics with Prometheus."""
        self.telemetry.track_request(method, endpoint, status_code, duration)

    def record_chat_message(self, model: str, tokens: int, duration: float) -> None:
        """Record chat message metrics."""
        logger.info(
            "Chat message recorded", model=model, tokens=tokens, duration=duration
        )

    def record_research_operation(
        self, operation_type: str, duration: float, success: bool
    ):
        """Record deep research operation metrics."""
        RESEARCH_DURATION.labels(
            research_phase=operation_type, success=str(success).lower()
        ).observe(duration)

    def record_tool_toggle(self, tool: str, enabled: bool) -> None:
        """Record tool toggle events."""
        TOOL_TOGGLE_EVENTS.labels(
            tool=tool, state="enabled" if enabled else "disabled"
        ).inc()

    def record_tool_call_blocked(self, tool: str, reason: str) -> None:
        """Record blocked tool invocation attempts."""
        TOOL_CALL_BLOCKED.labels(tool=tool, reason=reason).inc()

    def record_planner_tool_suggested(self, tool: str) -> None:
        """Record planner tool suggestion events."""
        PLANNER_TOOL_SUGGESTED.labels(tool=tool).inc()


metrics_collector = MetricsCollector()


def setup_telemetry(settings) -> None:
    """Enhanced telemetry setup with Prometheus integration."""
    logger.info("Setting up advanced telemetry with Prometheus metrics")

    # Initialize metrics with default values
    ACTIVE_CONNECTIONS.set(0)
    USER_SESSIONS.set(0)

    logger.info("Advanced telemetry setup complete")


def instrument_fastapi(app) -> None:
    """Enhanced FastAPI instrumentation with request tracking."""
    import time

    from fastapi import Request

    @app.middleware("http")
    async def telemetry_middleware(request: Request, call_next):
        """Middleware to track all HTTP requests."""
        start_time = time.time()

        # Increment active connections
        telemetry.increment_active_connections()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Track successful request
            telemetry.track_request(
                method=request.method,
                endpoint=str(request.url.path),
                status_code=response.status_code,
                duration=duration,
            )

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Track failed request
            telemetry.track_request(
                method=request.method,
                endpoint=str(request.url.path),
                status_code=500,
                duration=duration,
            )

            ERROR_COUNT.labels(
                error_type=type(e).__name__,
                endpoint=str(request.url.path),
                severity="error",
            ).inc()

            raise

        finally:
            # Decrement active connections
            telemetry.decrement_active_connections()

    logger.info("FastAPI instrumentation with telemetry middleware enabled")


def shutdown_telemetry() -> None:
    """Enhanced telemetry shutdown."""
    logger.info("Shutting down advanced telemetry")
    # Reset metrics
    ACTIVE_CONNECTIONS.set(0)
    USER_SESSIONS.set(0)
    logger.info("Advanced telemetry shutdown complete")


def track_endpoint(operation_name: str = None):
    """Decorator to automatically track endpoint performance."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            async with telemetry.track_operation(op_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def track_external_call(service_name: str):
    """Decorator to track external API calls."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                telemetry.track_external_api_call(
                    service=service_name,
                    endpoint=func.__name__,
                    status="success",
                    duration=duration,
                )

                return result

            except Exception:
                duration = time.time() - start_time

                telemetry.track_external_api_call(
                    service=service_name,
                    endpoint=func.__name__,
                    status="error",
                    duration=duration,
                )
                raise

        return wrapper

    return decorator


def get_metrics() -> str:
    """Get all metrics in Prometheus format."""
    return generate_latest(CUSTOM_REGISTRY).decode("utf-8")


@asynccontextmanager
async def trace_span(
    operation_name: str, attributes: Optional[Dict[str, Any]] = None
) -> AsyncIterator[Any]:
    """Enhanced async context manager for operation tracing."""
    attributes = attributes or {}

    async with telemetry.track_operation(operation_name, attributes):
        yield telemetry
