"""
Unit tests for models endpoint.

Tests coverage for:
- /models endpoint returning available models
- Configuration parsing
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)


@pytest.mark.unit
class TestModelsEndpoint:
    """Test models endpoint"""

    def test_get_models_default(self):
        """Test getting models with default configuration"""
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "default_model" in data
        assert "allowed_models" in data

        # Check types
        assert isinstance(data["default_model"], str)
        assert isinstance(data["allowed_models"], list)

        # Check that default model is in allowed models
        if data["allowed_models"]:
            assert len(data["allowed_models"]) > 0

    def test_get_models_custom_config(self, monkeypatch):
        """Test getting models with custom configuration"""
        # Clear the lru_cache to allow new settings to be loaded
        from src.core.config import get_settings
        get_settings.cache_clear()

        # Set environment variables for custom configuration
        monkeypatch.setenv("CHAT_DEFAULT_MODEL", "Saptiva Turbo")
        monkeypatch.setenv("CHAT_ALLOWED_MODELS", "Saptiva Turbo,Saptiva Cortex,Saptiva Ops")

        # Create new settings instance with updated env vars
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()

        # Check configured values
        assert data["default_model"] == "Saptiva Turbo"
        assert len(data["allowed_models"]) == 3
        assert "Saptiva Turbo" in data["allowed_models"]
        assert "Saptiva Cortex" in data["allowed_models"]
        assert "Saptiva Ops" in data["allowed_models"]

        # Clear cache again for next test
        get_settings.cache_clear()

    def test_get_models_with_whitespace(self, monkeypatch):
        """Test getting models with whitespace in configuration"""
        from src.core.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("CHAT_DEFAULT_MODEL", "Saptiva Turbo")
        monkeypatch.setenv("CHAT_ALLOWED_MODELS", " Saptiva Turbo , Saptiva Cortex , Saptiva Ops ")

        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()

        # Check that whitespace is stripped
        for model in data["allowed_models"]:
            assert model == model.strip()
            assert len(model) > 0

        get_settings.cache_clear()

    def test_get_models_empty_config(self, monkeypatch):
        """Test getting models with empty configuration"""
        from src.core.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("CHAT_DEFAULT_MODEL", "Saptiva Turbo")
        monkeypatch.setenv("CHAT_ALLOWED_MODELS", "")

        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()

        # Check that empty config results in empty list
        assert data["allowed_models"] == []

        get_settings.cache_clear()
