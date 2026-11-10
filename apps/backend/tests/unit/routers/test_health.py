"""
Unit tests for health router.

Tests:
- Health check endpoint
- Liveness probe
- Readiness probe
- Feature flags endpoint
- Response models
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.routers.health import (
    DatabaseCheck,
    FeatureFlagsResponse,
    HealthResponse,
    get_feature_flags,
    health_check,
    liveness_probe,
    readiness_probe,
)

pytestmark = [pytest.mark.unit]


class TestHealthResponse:
    """Test HealthResponse model."""

    def test_create_healthy_response(self):
        """Test creating a healthy response."""
        response = HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow(),
            version="1.0.0",
            uptime_seconds=0.5,
            checks={"database": {"status": "healthy"}},
        )

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.uptime_seconds == 0.5
        assert "database" in response.checks

    def test_create_degraded_response(self):
        """Test creating a degraded response."""
        response = HealthResponse(
            status="degraded",
            timestamp=datetime.utcnow(),
            version="1.0.0",
            uptime_seconds=0.1,
            checks={
                "database": {
                    "status": "unhealthy",
                    "error": "Connection refused",
                }
            },
        )

        assert response.status == "degraded"
        assert response.checks["database"]["status"] == "unhealthy"


class TestDatabaseCheck:
    """Test DatabaseCheck model."""

    def test_create_healthy_check(self):
        """Test creating a healthy database check."""
        check = DatabaseCheck(
            status="healthy",
            latency_ms=5.5,
            connected=True,
        )

        assert check.status == "healthy"
        assert check.latency_ms == 5.5
        assert check.connected is True
        assert check.error == ""

    def test_create_unhealthy_check(self):
        """Test creating an unhealthy database check."""
        check = DatabaseCheck(
            status="unhealthy",
            latency_ms=0.0,
            connected=False,
            error="Connection timeout",
        )

        assert check.status == "unhealthy"
        assert check.connected is False
        assert check.error == "Connection timeout"


class TestFeatureFlagsResponse:
    """Test FeatureFlagsResponse model."""

    def test_create_response(self):
        """Test creating feature flags response."""
        response = FeatureFlagsResponse(
            deep_research_kill_switch=False,
            deep_research_enabled=True,
            deep_research_auto=True,
            deep_research_complexity_threshold=0.7,
            create_chat_optimistic=True,
        )

        assert response.deep_research_kill_switch is False
        assert response.deep_research_enabled is True
        assert response.deep_research_auto is True
        assert response.deep_research_complexity_threshold == 0.7
        assert response.create_chat_optimistic is True

    def test_default_optimistic(self):
        """Test default value for create_chat_optimistic."""
        response = FeatureFlagsResponse(
            deep_research_kill_switch=False,
            deep_research_enabled=True,
            deep_research_auto=False,
            deep_research_complexity_threshold=0.5,
        )

        assert response.create_chat_optimistic is True


class TestLivenessProbe:
    """Test liveness_probe endpoint."""

    @pytest.mark.asyncio
    async def test_returns_alive_status(self):
        """Test liveness probe returns alive."""
        result = await liveness_probe()

        assert result == {"status": "alive"}


class TestReadinessProbe:
    """Test readiness_probe endpoint."""

    @pytest.mark.asyncio
    async def test_returns_ready_when_db_connected(self):
        """Test readiness probe returns ready when database is connected."""
        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(return_value=None)

            result = await readiness_probe()

            assert result == {"status": "ready"}
            mock_db.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_503_when_db_unavailable(self):
        """Test readiness probe raises 503 when database is unavailable."""
        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(side_effect=Exception("Connection refused"))

            with pytest.raises(HTTPException) as exc_info:
                await readiness_probe()

            assert exc_info.value.status_code == 503
            assert "not ready" in exc_info.value.detail


class TestHealthCheck:
    """Test health_check endpoint."""

    @pytest.mark.asyncio
    async def test_healthy_when_db_connected(self):
        """Test health check returns healthy when database is connected."""
        mock_settings = MagicMock()
        mock_settings.app_version = "1.2.3"

        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(return_value=None)

            result = await health_check(settings=mock_settings)

            assert result.status == "healthy"
            assert result.version == "1.2.3"
            assert "database" in result.checks
            assert result.checks["database"]["status"] == "healthy"
            assert result.checks["database"]["connected"] is True

    @pytest.mark.asyncio
    async def test_degraded_when_db_fails(self):
        """Test health check returns degraded when database fails."""
        mock_settings = MagicMock()
        mock_settings.app_version = "1.0.0"

        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(side_effect=Exception("Database error"))

            result = await health_check(settings=mock_settings)

            assert result.status == "degraded"
            assert result.checks["database"]["status"] == "unhealthy"
            assert result.checks["database"]["connected"] is False
            assert "Database error" in result.checks["database"]["error"]

    @pytest.mark.asyncio
    async def test_includes_latency_measurement(self):
        """Test health check includes database latency."""
        mock_settings = MagicMock()
        mock_settings.app_version = "1.0.0"

        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(return_value=None)

            result = await health_check(settings=mock_settings)

            assert result.checks["database"]["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_includes_timestamp(self):
        """Test health check includes timestamp."""
        mock_settings = MagicMock()
        mock_settings.app_version = "1.0.0"

        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(return_value=None)

            result = await health_check(settings=mock_settings)

            assert result.timestamp is not None
            assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_includes_uptime_seconds(self):
        """Test health check includes uptime seconds."""
        mock_settings = MagicMock()
        mock_settings.app_version = "1.0.0"

        with patch("src.routers.health.Database") as mock_db:
            mock_db.ping = AsyncMock(return_value=None)

            result = await health_check(settings=mock_settings)

            assert result.uptime_seconds >= 0


class TestGetFeatureFlags:
    """Test get_feature_flags endpoint."""

    @pytest.mark.asyncio
    async def test_returns_feature_flags(self):
        """Test get_feature_flags returns correct flags."""
        mock_settings = MagicMock()
        mock_settings.deep_research_kill_switch = False
        mock_settings.deep_research_enabled = True
        mock_settings.deep_research_auto = True
        mock_settings.deep_research_complexity_threshold = 0.75
        mock_settings.create_chat_optimistic = True

        result = await get_feature_flags(settings=mock_settings)

        assert result.deep_research_kill_switch is False
        assert result.deep_research_enabled is True
        assert result.deep_research_auto is True
        assert result.deep_research_complexity_threshold == 0.75
        assert result.create_chat_optimistic is True

    @pytest.mark.asyncio
    async def test_returns_kill_switch_enabled(self):
        """Test get_feature_flags with kill switch enabled."""
        mock_settings = MagicMock()
        mock_settings.deep_research_kill_switch = True
        mock_settings.deep_research_enabled = True
        mock_settings.deep_research_auto = True
        mock_settings.deep_research_complexity_threshold = 0.5
        mock_settings.create_chat_optimistic = False

        result = await get_feature_flags(settings=mock_settings)

        assert result.deep_research_kill_switch is True
        assert result.create_chat_optimistic is False

    @pytest.mark.asyncio
    async def test_response_is_feature_flags_response(self):
        """Test result is FeatureFlagsResponse instance."""
        mock_settings = MagicMock()
        mock_settings.deep_research_kill_switch = False
        mock_settings.deep_research_enabled = False
        mock_settings.deep_research_auto = False
        mock_settings.deep_research_complexity_threshold = 0.0
        mock_settings.create_chat_optimistic = True

        result = await get_feature_flags(settings=mock_settings)

        assert isinstance(result, FeatureFlagsResponse)
