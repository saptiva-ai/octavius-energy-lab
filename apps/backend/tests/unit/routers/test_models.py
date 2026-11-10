"""
Unit tests for models router.

Tests:
- Get models endpoint
- Model list parsing
- Default model configuration
"""

from unittest.mock import MagicMock

import pytest

from src.routers.models import get_models

pytestmark = [pytest.mark.unit]


class TestGetModels:
    """Test get_models endpoint."""

    @pytest.mark.asyncio
    async def test_returns_default_model(self):
        """Test returns default model from settings."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = "saptiva-turbo,saptiva-cortex"

        result = await get_models(settings=mock_settings)

        assert result["default_model"] == "saptiva-turbo"

    @pytest.mark.asyncio
    async def test_returns_allowed_models_list(self):
        """Test returns list of allowed models."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = "saptiva-turbo,saptiva-cortex,saptiva-ops"

        result = await get_models(settings=mock_settings)

        assert result["allowed_models"] == [
            "saptiva-turbo",
            "saptiva-cortex",
            "saptiva-ops",
        ]

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_models(self):
        """Test whitespace is stripped from model names."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = " saptiva-turbo , saptiva-cortex "

        result = await get_models(settings=mock_settings)

        assert result["allowed_models"] == ["saptiva-turbo", "saptiva-cortex"]

    @pytest.mark.asyncio
    async def test_filters_empty_models(self):
        """Test empty model names are filtered out."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = "saptiva-turbo,,saptiva-cortex,"

        result = await get_models(settings=mock_settings)

        assert result["allowed_models"] == ["saptiva-turbo", "saptiva-cortex"]

    @pytest.mark.asyncio
    async def test_single_model(self):
        """Test with single model in list."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = "saptiva-turbo"

        result = await get_models(settings=mock_settings)

        assert result["allowed_models"] == ["saptiva-turbo"]

    @pytest.mark.asyncio
    async def test_empty_allowed_models(self):
        """Test with empty allowed models string."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = ""

        result = await get_models(settings=mock_settings)

        assert result["allowed_models"] == []

    @pytest.mark.asyncio
    async def test_result_structure(self):
        """Test result has expected structure."""
        mock_settings = MagicMock()
        mock_settings.chat_default_model = "saptiva-turbo"
        mock_settings.chat_allowed_models = "saptiva-turbo"

        result = await get_models(settings=mock_settings)

        assert "default_model" in result
        assert "allowed_models" in result
        assert isinstance(result["allowed_models"], list)
