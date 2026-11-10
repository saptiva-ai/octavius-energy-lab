"""
Health check API schemas
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    """Service status enumeration"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthStatus(BaseModel):
    """Health status schema"""

    status: ServiceStatus = Field(..., description="Overall service status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    version: str = Field(..., description="Service version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    checks: Dict[str, Any] = Field(..., description="Individual health checks")


class ServiceCheck(BaseModel):
    """Individual service health check"""

    status: ServiceStatus = Field(..., description="Service status")
    latency_ms: float = Field(..., description="Response latency in milliseconds")
    connected: bool = Field(..., description="Connection status")
    error: str = Field(default="", description="Error message if unhealthy")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class LivenessResponse(BaseModel):
    """Kubernetes liveness probe response"""

    status: str = Field(default="alive", description="Liveness status")


class ReadinessResponse(BaseModel):
    """Kubernetes readiness probe response"""

    status: str = Field(default="ready", description="Readiness status")
