"""
Unit tests for health schemas.

Tests Pydantic models for health check responses.
"""
import pytest
from datetime import datetime

from src.schemas.health import (
    ServiceStatus,
    HealthStatus,
    ServiceCheck,
    LivenessResponse,
    ReadinessResponse
)


@pytest.mark.unit
class TestHealthSchemas:
    """Test health check schema models"""

    def test_service_status_enum_values(self):
        """Test ServiceStatus enum has expected values"""
        assert ServiceStatus.HEALTHY == "healthy"
        assert ServiceStatus.DEGRADED == "degraded"
        assert ServiceStatus.UNHEALTHY == "unhealthy"

    def test_health_status_creation(self):
        """Test HealthStatus model creation"""
        now = datetime.utcnow()
        health = HealthStatus(
            status=ServiceStatus.HEALTHY,
            timestamp=now,
            version="1.0.0",
            uptime_seconds=100.5,
            checks={"database": {"status": "healthy"}}
        )

        assert health.status == ServiceStatus.HEALTHY
        assert health.timestamp == now
        assert health.version == "1.0.0"
        assert health.uptime_seconds == 100.5
        assert "database" in health.checks

    def test_service_check_creation(self):
        """Test ServiceCheck model creation"""
        check = ServiceCheck(
            status=ServiceStatus.HEALTHY,
            latency_ms=15.5,
            connected=True,
            error="",
            metadata={"host": "localhost"}
        )

        assert check.status == ServiceStatus.HEALTHY
        assert check.latency_ms == 15.5
        assert check.connected is True
        assert check.error == ""
        assert check.metadata["host"] == "localhost"

    def test_service_check_unhealthy(self):
        """Test ServiceCheck for unhealthy service"""
        check = ServiceCheck(
            status=ServiceStatus.UNHEALTHY,
            latency_ms=0.0,
            connected=False,
            error="Connection timeout"
        )

        assert check.status == ServiceStatus.UNHEALTHY
        assert check.connected is False
        assert "timeout" in check.error.lower()

    def test_liveness_response(self):
        """Test LivenessResponse model"""
        response = LivenessResponse(status="alive")
        assert response.status == "alive"

    def test_liveness_response_default(self):
        """Test LivenessResponse has default value"""
        response = LivenessResponse()
        assert response.status == "alive"

    def test_readiness_response(self):
        """Test ReadinessResponse model"""
        response = ReadinessResponse(status="ready")
        assert response.status == "ready"

    def test_readiness_response_default(self):
        """Test ReadinessResponse has default value"""
        response = ReadinessResponse()
        assert response.status == "ready"

    def test_health_status_degraded(self):
        """Test HealthStatus for degraded system"""
        now = datetime.utcnow()
        health = HealthStatus(
            status=ServiceStatus.DEGRADED,
            timestamp=now,
            version="1.0.0",
            uptime_seconds=50.0,
            checks={
                "database": {"status": "healthy"},
                "redis": {"status": "unhealthy"}
            }
        )

        assert health.status == ServiceStatus.DEGRADED
        assert len(health.checks) == 2

    def test_service_check_json_serialization(self):
        """Test ServiceCheck can be serialized to JSON"""
        check = ServiceCheck(
            status=ServiceStatus.HEALTHY,
            latency_ms=10.0,
            connected=True
        )

        json_data = check.model_dump()
        assert json_data["status"] == "healthy"
        assert json_data["latency_ms"] == 10.0
        assert json_data["connected"] is True

    def test_health_status_json_serialization(self):
        """Test HealthStatus can be serialized to JSON"""
        now = datetime.utcnow()
        health = HealthStatus(
            status=ServiceStatus.HEALTHY,
            timestamp=now,
            version="1.0.0",
            uptime_seconds=100.0,
            checks={"api": {"status": "healthy"}}
        )

        json_data = health.model_dump()
        assert json_data["status"] == "healthy"
        assert "timestamp" in json_data
        assert json_data["version"] == "1.0.0"
        assert len(json_data["checks"]) == 1

    def test_service_check_metadata_optional(self):
        """Test ServiceCheck metadata is optional"""
        check = ServiceCheck(
            status=ServiceStatus.HEALTHY,
            latency_ms=5.0,
            connected=True
        )

        assert check.metadata == {}

    def test_health_status_with_multiple_checks(self):
        """Test HealthStatus with multiple service checks"""
        now = datetime.utcnow()
        health = HealthStatus(
            status=ServiceStatus.HEALTHY,
            timestamp=now,
            version="1.0.0",
            uptime_seconds=200.0,
            checks={
                "database": {"status": "healthy", "latency_ms": 5.0},
                "redis": {"status": "healthy", "latency_ms": 2.0},
                "api": {"status": "healthy", "latency_ms": 1.0}
            }
        )

        assert len(health.checks) == 3
        assert all(check["status"] == "healthy" for check in health.checks.values())
