"""
Telemetry middleware for request tracking and metrics.
"""

import time
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..core.telemetry import metrics_collector

logger = structlog.get_logger(__name__)


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting telemetry data."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with telemetry tracking."""
        start_time = time.time()
        method = request.method
        path_template = request.url.path

        try:
            # Process request without telemetry span for now to avoid the compatibility issue
            response = await call_next(request)
            status_code = response.status_code

            # Record metrics
            duration = time.time() - start_time
            metrics_collector.record_request(
                method=method,
                endpoint=path_template,
                status_code=status_code,
                duration=duration,
            )

            # Log request
            logger.info(
                "Request completed",
                method=method,
                path=path_template,
                status_code=status_code,
                duration_ms=duration * 1000,
                user_agent=request.headers.get("user-agent", ""),
                remote_addr=request.client.host if request.client else "",
            )

            return response

        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            metrics_collector.record_request(
                method=method,
                endpoint=path_template,
                status_code=500,
                duration=duration,
            )

            logger.error(
                "Request failed",
                method=method,
                path=path_template,
                error=str(e),
                duration_ms=duration * 1000,
            )

            raise
