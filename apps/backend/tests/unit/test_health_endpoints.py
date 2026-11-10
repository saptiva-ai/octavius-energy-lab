"""
Unit tests for health check endpoints.

Tests coverage for:
- /health endpoint with database checks
- /health/live liveness probe
- /health/ready readiness probe
- /feature-flags endpoint
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from fastapi.testclient import TestClient

from src.main import app
from src.core.database import Database


client = TestClient(app)


@pytest.mark.unit
class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_liveness_probe(self):
        """Test liveness probe returns alive status"""
        response = client.get("/api/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_readiness_probe_success(self):
        """Test readiness probe when database is available"""
        with patch.object(Database, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = True
            response = client.get("/api/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_readiness_probe_failure(self):
        """Test readiness probe when database is unavailable"""
        with patch.object(Database, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = Exception("Database connection failed")
            response = client.get("/api/health/ready")
            assert response.status_code == 503
            data = response.json()
            assert "not ready" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test comprehensive health check with healthy database"""
        with patch.object(Database, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.return_value = True
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert "version" in data
            assert "uptime_seconds" in data
            assert "checks" in data

            # Check database health check
            assert "database" in data["checks"]
            db_check = data["checks"]["database"]
            assert db_check["status"] == "healthy"
            assert db_check["connected"] is True
            assert db_check["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_health_check_degraded(self):
        """Test comprehensive health check with database failure"""
        with patch.object(Database, 'ping', new_callable=AsyncMock) as mock_ping:
            mock_ping.side_effect = Exception("Connection timeout")
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()

            # Service is degraded but still returns 200
            assert data["status"] == "degraded"

            # Check database is marked unhealthy
            assert "database" in data["checks"]
            db_check = data["checks"]["database"]
            assert db_check["status"] == "unhealthy"
            assert db_check["connected"] is False
            assert "error" in db_check

    def test_feature_flags_endpoint(self):
        """Test feature flags endpoint returns expected structure"""
        response = client.get("/api/feature-flags")
        assert response.status_code == 200
        data = response.json()

        # Check all expected flags are present
        expected_flags = [
            "deep_research_kill_switch",
            "deep_research_enabled",
            "deep_research_auto",
            "deep_research_complexity_threshold",
            "create_chat_optimistic"
        ]

        for flag in expected_flags:
            assert flag in data

        # Check types
        assert isinstance(data["deep_research_kill_switch"], bool)
        assert isinstance(data["deep_research_enabled"], bool)
        assert isinstance(data["deep_research_auto"], bool)
        assert isinstance(data["deep_research_complexity_threshold"], (int, float))
        assert isinstance(data["create_chat_optimistic"], bool)
