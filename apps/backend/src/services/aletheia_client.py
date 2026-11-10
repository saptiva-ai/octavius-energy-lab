"""
Aletheia HTTP client with retry logic and circuit breaker.
"""

import asyncio
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

import httpx
import structlog
from pydantic import BaseModel

from ..core.config import get_settings

logger = structlog.get_logger(__name__)


class CircuitBreakerState(str, Enum):
    """Circuit breaker states"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AletheiaRequest(BaseModel):
    """Base request to Aletheia"""

    query: str
    task_id: str
    user_id: str
    params: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class AletheiaResponse(BaseModel):
    """Base response from Aletheia"""

    task_id: str
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker implementation for external API calls"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED

    def __call__(self, func):
        """Decorator to wrap functions with circuit breaker"""

        async def wrapper(*args, **kwargs):
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                else:
                    raise Exception(
                        f"Circuit breaker is OPEN. Last failure: {self.last_failure_time}"
                    )

            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise e

        return wrapper

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True

        return datetime.utcnow() - self.last_failure_time > timedelta(
            seconds=self.recovery_timeout
        )

    def _on_success(self):
        """Reset circuit breaker on successful call"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        logger.info("Circuit breaker reset to CLOSED state")

    def _on_failure(self):
        """Handle failure and potentially open circuit"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                "Circuit breaker opened due to failures",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )


class AletheiaClient:
    """HTTP client for Aletheia orchestrator with resilience patterns"""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.aletheia_base_url.rstrip("/")
        self.timeout = self.settings.aletheia_timeout
        self.max_retries = self.settings.aletheia_max_retries

        # Circuit breaker for API calls
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=30, expected_exception=httpx.HTTPError
        )

        # Métricas para observabilidad
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_latency": 0.0,
            "availability": 1.0,
            "last_health_check": None,
        }

        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            headers={
                "User-Agent": "Copilot-OS/0.1.0",
                "Content-Type": "application/json",
            },
        )

        # Add API key if configured
        if self.settings.aletheia_api_key:
            self.client.headers["Authorization"] = (
                f"Bearer {self.settings.aletheia_api_key}"
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    @CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic and metrics collection"""

        url = f"{self.base_url}{endpoint}"
        retry_count = 0
        start_time = time.time()

        # Actualizar métricas
        self.metrics["total_requests"] += 1

        while retry_count <= self.max_retries:
            try:
                logger.debug(
                    "Making request to Aletheia",
                    method=method,
                    url=url,
                    retry_count=retry_count,
                    data=data,
                    params=params,
                )

                response = await self.client.request(
                    method=method, url=url, json=data, params=params
                )

                response.raise_for_status()
                result = response.json()

                # Métricas de éxito
                latency = time.time() - start_time
                self.metrics["successful_requests"] += 1
                self.metrics["total_latency"] += latency
                self._update_availability()

                logger.info(
                    "Aletheia request successful",
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                    retry_count=retry_count,
                    latency_ms=round(latency * 1000, 2),
                )

                return result

            except httpx.HTTPError as e:
                retry_count += 1

                if retry_count > self.max_retries:
                    # Métricas de fallo
                    self.metrics["failed_requests"] += 1
                    self._update_availability()

                    logger.error(
                        "Aletheia request failed after max retries",
                        method=method,
                        url=url,
                        error=str(e),
                        max_retries=self.max_retries,
                        total_latency_ms=round((time.time() - start_time) * 1000, 2),
                    )
                    raise

                # Exponential backoff
                wait_time = min(2**retry_count, 30)  # Max 30 seconds
                logger.warning(
                    "Aletheia request failed, retrying",
                    method=method,
                    url=url,
                    error=str(e),
                    retry_count=retry_count,
                    wait_time=wait_time,
                )

                await asyncio.sleep(wait_time)

    def _update_availability(self):
        """Update availability metric based on success/failure ratio"""
        total = self.metrics["total_requests"]
        if total > 0:
            success_rate = self.metrics["successful_requests"] / total
            self.metrics["availability"] = success_rate
        else:
            self.metrics["availability"] = 1.0

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics for monitoring"""
        metrics = self.metrics.copy()

        # Calculate average latency
        if self.metrics["successful_requests"] > 0:
            metrics["average_latency_ms"] = round(
                (self.metrics["total_latency"] / self.metrics["successful_requests"])
                * 1000,
                2,
            )
        else:
            metrics["average_latency_ms"] = 0.0

        # Add computed metrics
        metrics["success_rate"] = round(self.metrics["availability"] * 100, 2)
        metrics["failure_rate"] = round((1 - self.metrics["availability"]) * 100, 2)

        return metrics

    async def start_research(
        self,
        query: str,
        task_id: str,
        user_id: str,
        params: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AletheiaResponse:
        """Start a research task in Aletheia"""

        request_data = AletheiaRequest(
            query=query,
            task_id=task_id,
            user_id=user_id,
            params=params or {},
            context=context or {},
        ).model_dump()

        try:
            response_data = await self._make_request(
                method="POST", endpoint="/research", data=request_data
            )

            return AletheiaResponse(**response_data)

        except Exception as e:
            logger.error("Failed to start research task", error=str(e), task_id=task_id)
            return AletheiaResponse(
                task_id=task_id,
                status="error",
                message="Failed to start research task",
                error=str(e),
            )

    async def start_deep_research(
        self,
        query: str,
        task_id: str,
        user_id: str,
        params: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AletheiaResponse:
        """Start a deep research task in Aletheia"""

        request_data = AletheiaRequest(
            query=query,
            task_id=task_id,
            user_id=user_id,
            params=params or {},
            context=context or {},
        ).model_dump()

        try:
            response_data = await self._make_request(
                method="POST", endpoint="/deep-research", data=request_data
            )

            return AletheiaResponse(**response_data)

        except Exception as e:
            logger.error(
                "Failed to start deep research task", error=str(e), task_id=task_id
            )
            return AletheiaResponse(
                task_id=task_id,
                status="error",
                message="Failed to start deep research task",
                error=str(e),
            )

    async def get_task_status(self, task_id: str) -> AletheiaResponse:
        """Get status of a research task"""

        try:
            response_data = await self._make_request(
                method="GET", endpoint=f"/task/{task_id}"
            )

            return AletheiaResponse(**response_data)

        except Exception as e:
            logger.error("Failed to get task status", error=str(e), task_id=task_id)
            return AletheiaResponse(
                task_id=task_id,
                status="error",
                message="Failed to get task status",
                error=str(e),
            )

    async def cancel_task(
        self, task_id: str, reason: Optional[str] = None
    ) -> AletheiaResponse:
        """Cancel a research task"""

        data = {"task_id": task_id}
        if reason:
            data["reason"] = reason

        try:
            response_data = await self._make_request(
                method="POST", endpoint=f"/task/{task_id}/cancel", data=data
            )

            return AletheiaResponse(**response_data)

        except Exception as e:
            logger.error("Failed to cancel task", error=str(e), task_id=task_id)
            return AletheiaResponse(
                task_id=task_id,
                status="error",
                message="Failed to cancel task",
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if Aletheia is healthy"""

        try:
            await self._make_request(method="GET", endpoint="/health")
            self.metrics["last_health_check"] = datetime.utcnow().isoformat()
            return True
        except Exception as e:
            logger.warning("Aletheia health check failed", error=str(e))
            self.metrics["last_health_check"] = datetime.utcnow().isoformat()
            return False

    async def get_events_stream_url(self, task_id: str) -> str:
        """Get the URL for events.ndjson stream for a task"""
        # In production, this would be the actual Aletheia artifacts URL
        return f"{self.base_url}/runs/{task_id}/events.ndjson"

    async def get_report_artifacts(self, task_id: str) -> Dict[str, str]:
        """Get URLs for task artifacts (report, sources, etc.)"""

        try:
            response_data = await self._make_request(
                method="GET", endpoint=f"/task/{task_id}/artifacts"
            )

            return response_data.get("artifacts", {})

        except Exception as e:
            logger.error("Failed to get task artifacts", error=str(e), task_id=task_id)
            return {}


# Singleton instance
_aletheia_client: Optional[AletheiaClient] = None


async def get_aletheia_client() -> AletheiaClient:
    """Get singleton Aletheia client instance"""
    global _aletheia_client

    if _aletheia_client is None:
        _aletheia_client = AletheiaClient()

    return _aletheia_client


async def close_aletheia_client():
    """Close Aletheia client connection"""
    global _aletheia_client

    if _aletheia_client:
        await _aletheia_client.close()
        _aletheia_client = None
