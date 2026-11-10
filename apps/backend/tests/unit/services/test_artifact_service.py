"""
Unit tests for artifact_service module.

Tests:
- ArtifactService class
- create_chart_artifact method
- get_charts_by_session method
- get_latest_chart_in_session method
- get_artifact_by_id method
- get_artifacts_by_user method
- delete_artifact method
- to_response method
- get_artifact_service singleton
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.artifact_service import ArtifactService, get_artifact_service

pytestmark = [pytest.mark.unit]


class TestCreateChartArtifact:
    """Test create_chart_artifact method (generic, domain-agnostic)."""

    @pytest.mark.asyncio
    async def test_creates_artifact_successfully(self):
        """Test creates artifact successfully."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.id = "artifact_123"
        mock_artifact.insert = AsyncMock()

        with patch(
            "src.services.artifact_service.Artifact"
        ) as mock_artifact_class:
            mock_artifact_class.create_chart = MagicMock(return_value=mock_artifact)

            result = await service.create_chart_artifact(
                user_id="user_123",
                session_id="session_456",
                chart_data={"metric_name": "ventas", "series": [1, 2, 3]},
                title="Test Chart",
            )

            assert result is mock_artifact
            mock_artifact.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_chart_data_through(self):
        """Test chart_data is passed through unchanged (no domain enrichment)."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.insert = AsyncMock()

        chart_data = {"metric_name": "ventas", "metadata": {"source": "pos"}}

        with patch(
            "src.services.artifact_service.Artifact"
        ) as mock_artifact_class:
            mock_artifact_class.create_chart = MagicMock(return_value=mock_artifact)

            await service.create_chart_artifact(
                user_id="user_123",
                session_id="session_456",
                chart_data=chart_data,
                title="Test Chart",
            )

            call_kwargs = mock_artifact_class.create_chart.call_args.kwargs
            assert call_kwargs["chart_data"] == chart_data

    @pytest.mark.asyncio
    async def test_logs_creation(self):
        """Test logs artifact creation."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.id = "artifact_123"
        mock_artifact.insert = AsyncMock()

        with patch(
            "src.services.artifact_service.Artifact"
        ) as mock_artifact_class, patch(
            "src.services.artifact_service.logger"
        ) as mock_logger:
            mock_artifact_class.create_chart = MagicMock(return_value=mock_artifact)

            await service.create_chart_artifact(
                user_id="user_123",
                session_id="session_456",
                chart_data={"metric_name": "ventas"},
                title="Test Chart",
            )

            mock_logger.info.assert_called_once()


class TestGetChartsBySession:
    """Test get_charts_by_session method."""

    @pytest.mark.asyncio
    async def test_returns_charts_for_session(self):
        """Test returns charts for a session."""
        service = ArtifactService()

        mock_charts = [MagicMock(), MagicMock()]
        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=mock_charts)

        with patch("src.services.artifact_service.Artifact") as mock_artifact:
            mock_artifact.find = MagicMock(return_value=mock_query)

            result = await service.get_charts_by_session("session_123")

            assert result == mock_charts
            mock_query.sort.assert_called_once_with("-created_at")

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Test respects limit parameter."""
        service = ArtifactService()

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[])

        with patch("src.services.artifact_service.Artifact") as mock_artifact:
            mock_artifact.find = MagicMock(return_value=mock_query)

            await service.get_charts_by_session("session_123", limit=5)

            mock_query.limit.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_default_limit_is_10(self):
        """Test default limit is 10."""
        service = ArtifactService()

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[])

        with patch("src.services.artifact_service.Artifact") as mock_artifact:
            mock_artifact.find = MagicMock(return_value=mock_query)

            await service.get_charts_by_session("session_123")

            mock_query.limit.assert_called_once_with(10)


class TestGetLatestChartInSession:
    """Test get_latest_chart_in_session method."""

    @pytest.mark.asyncio
    async def test_returns_latest_chart(self):
        """Test returns the latest chart."""
        service = ArtifactService()
        mock_chart = MagicMock()

        with patch.object(
            service, "get_charts_by_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = [mock_chart]

            result = await service.get_latest_chart_in_session("session_123")

            assert result is mock_chart
            mock_get.assert_called_once_with("session_123", limit=1)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_charts(self):
        """Test returns None when no charts exist."""
        service = ArtifactService()

        with patch.object(
            service, "get_charts_by_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = []

            result = await service.get_latest_chart_in_session("session_123")

            assert result is None


class TestGetArtifactById:
    """Test get_artifact_by_id method."""

    @pytest.mark.asyncio
    async def test_returns_artifact_when_found(self):
        """Test returns artifact when found."""
        service = ArtifactService()
        mock_artifact = MagicMock()
        mock_artifact.type = "chart"

        with patch("src.services.artifact_service.Artifact") as mock_artifact_class:
            mock_artifact_class.get = AsyncMock(return_value=mock_artifact)

            result = await service.get_artifact_by_id("artifact_123")

            assert result is mock_artifact

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Test returns None when artifact not found."""
        service = ArtifactService()

        with patch("src.services.artifact_service.Artifact") as mock_artifact_class:
            mock_artifact_class.get = AsyncMock(return_value=None)

            result = await service.get_artifact_by_id("artifact_123")

            assert result is None

    @pytest.mark.asyncio
    async def test_logs_warning_when_not_found(self):
        """Test logs warning when artifact not found."""
        service = ArtifactService()

        with patch(
            "src.services.artifact_service.Artifact"
        ) as mock_artifact_class, patch(
            "src.services.artifact_service.logger"
        ) as mock_logger:
            mock_artifact_class.get = AsyncMock(return_value=None)

            await service.get_artifact_by_id("artifact_123")

            mock_logger.warning.assert_called_once()


class TestGetArtifactsByUser:
    """Test get_artifacts_by_user method."""

    @pytest.mark.asyncio
    async def test_returns_all_user_artifacts(self):
        """Test returns all artifacts for user."""
        service = ArtifactService()
        mock_artifacts = [MagicMock(), MagicMock()]

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=mock_artifacts)

        with patch("src.services.artifact_service.Artifact") as mock_artifact:
            mock_artifact.find = MagicMock(return_value=mock_query)

            result = await service.get_artifacts_by_user("user_123")

            assert result == mock_artifacts

    @pytest.mark.asyncio
    async def test_filters_by_artifact_type(self):
        """Test filters by artifact type when provided."""
        service = ArtifactService()

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[])

        from src.models.artifact import ArtifactType

        with patch("src.services.artifact_service.Artifact") as mock_artifact:
            mock_artifact.find = MagicMock(return_value=mock_query)

            await service.get_artifacts_by_user(
                "user_123", artifact_type=ArtifactType.CHART
            )

            # Verify find was called with type filter
            call_args = mock_artifact.find.call_args[0][0]
            assert "type" in call_args

    @pytest.mark.asyncio
    async def test_default_limit_is_20(self):
        """Test default limit is 20."""
        service = ArtifactService()

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[])

        with patch("src.services.artifact_service.Artifact") as mock_artifact:
            mock_artifact.find = MagicMock(return_value=mock_query)

            await service.get_artifacts_by_user("user_123")

            mock_query.limit.assert_called_once_with(20)


class TestDeleteArtifact:
    """Test delete_artifact method."""

    @pytest.mark.asyncio
    async def test_deletes_artifact_successfully(self):
        """Test deletes artifact successfully."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.user_id = "user_123"
        mock_artifact.type = "chart"
        mock_artifact.delete = AsyncMock()

        with patch("src.services.artifact_service.Artifact") as mock_artifact_class:
            mock_artifact_class.get = AsyncMock(return_value=mock_artifact)

            result = await service.delete_artifact("artifact_123", "user_123")

            assert result is True
            mock_artifact.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_artifact_not_found(self):
        """Test returns False when artifact not found."""
        service = ArtifactService()

        with patch("src.services.artifact_service.Artifact") as mock_artifact_class:
            mock_artifact_class.get = AsyncMock(return_value=None)

            result = await service.delete_artifact("artifact_123", "user_123")

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_unauthorized(self):
        """Test returns False when user doesn't own artifact."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.user_id = "other_user"

        with patch("src.services.artifact_service.Artifact") as mock_artifact_class:
            mock_artifact_class.get = AsyncMock(return_value=mock_artifact)

            result = await service.delete_artifact("artifact_123", "user_123")

            assert result is False

    @pytest.mark.asyncio
    async def test_logs_unauthorized_delete_attempt(self):
        """Test logs unauthorized delete attempt."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.user_id = "other_user"

        with patch(
            "src.services.artifact_service.Artifact"
        ) as mock_artifact_class, patch(
            "src.services.artifact_service.logger"
        ) as mock_logger:
            mock_artifact_class.get = AsyncMock(return_value=mock_artifact)

            await service.delete_artifact("artifact_123", "user_123")

            mock_logger.warning.assert_called()


class TestToResponse:
    """Test to_response method."""

    def test_converts_artifact_to_response(self):
        """Test converts artifact to a lightweight response dict."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.id = "artifact_123"
        mock_artifact.title = "Test Chart"
        mock_artifact.type = MagicMock()
        mock_artifact.type.value = "chart"
        mock_artifact.created_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_artifact.chat_session_id = "session_456"

        result = service.to_response(mock_artifact)

        assert result["artifact_id"] == "artifact_123"
        assert result["title"] == "Test Chart"
        assert result["type"] == "chart"
        assert result["session_id"] == "session_456"

    def test_handles_none_session_id(self):
        """Test handles None session_id."""
        service = ArtifactService()

        mock_artifact = MagicMock()
        mock_artifact.id = "artifact_123"
        mock_artifact.title = "Test Chart"
        mock_artifact.type = MagicMock()
        mock_artifact.type.value = "chart"
        mock_artifact.created_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_artifact.chat_session_id = None

        result = service.to_response(mock_artifact)

        assert result["session_id"] == ""


class TestGetArtifactService:
    """Test get_artifact_service singleton."""

    def test_returns_artifact_service(self):
        """Test returns ArtifactService instance."""
        import src.services.artifact_service as module

        # Reset singleton
        module._artifact_service_instance = None

        service = get_artifact_service()
        assert isinstance(service, ArtifactService)

    def test_returns_same_instance(self):
        """Test returns same singleton instance."""
        import src.services.artifact_service as module

        # Reset singleton
        module._artifact_service_instance = None

        service1 = get_artifact_service()
        service2 = get_artifact_service()
        assert service1 is service2
