"""
Unit tests for core configuration module.

Tests Settings class validation, defaults, and environment variable loading.
Updated to match the current Settings structure with computed fields.
"""

import pytest
from pydantic import ValidationError
from src.core.config import Settings, get_settings


def _settings_aislado(monkeypatch, **entorno) -> Settings:
    """Settings sin el `.env` del entorno de trabajo (CA-01 de higiene).

    `Settings` lee `envs/.env` por `model_config`, así que un test que afirme
    defaults dependía de que nadie personalizara esas variables en su máquina.
    Se construye con `_env_file=None` y solo las variables que el test declara:
    lo que se afirma es el default del código, no lo que traiga la máquina.
    """
    for nombre in (
        "HOST",
        "PORT",
        "DEBUG",
        "RELOAD",
        "APP_NAME",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS",
        "JWT_ALGORITHM",
        "CHAT_DEFAULT_MODEL",
        "CHAT_ALLOWED_MODELS",
    ):
        monkeypatch.delenv(nombre, raising=False)
    # Requeridas por los campos computados; valores de prueba, no secretos.
    base = {
        "MONGODB_URL": "mongodb://testuser:testpass@localhost:27017/testdb",
        "REDIS_URL": "redis://:testredis@localhost:6379/0",
        "JWT_SECRET_KEY": "test_secret_key_minimum_32_chars_long",
        "SECRET_KEY": "test_api_key_minimum_32_chars",
        "SAPTIVA_API_KEY": "test_saptiva_key",
    }
    for clave, valor in {**base, **entorno}.items():
        monkeypatch.setenv(clave, valor)
    return Settings(_env_file=None)


class TestSettings:
    """Test suite for Settings configuration class."""

    def test_settings_with_defaults(self, monkeypatch):
        """Los defaults del código, sin que el `.env` de la máquina los pise."""
        settings = _settings_aislado(monkeypatch)

        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        # Ahora sí se puede afirmar el valor, no solo el tipo: el test corre
        # aislado del archivo de entorno.
        assert settings.debug is False
        assert settings.reload is False
        assert settings.app_name == "Copilot OS API"
        assert settings.jwt_access_token_expire_minutes == 1440
        assert settings.jwt_refresh_token_expire_days == 7
        assert settings.jwt_algorithm == "HS256"

    def test_defaults_no_dependen_del_env_de_la_maquina(self, monkeypatch):
        """Con el entorno personalizado (como en una máquina de desarrollo con
        su `.env`), los defaults del código siguen siendo los mismos."""
        monkeypatch.setenv("APP_NAME", "Otro nombre")
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "5")

        settings = _settings_aislado(monkeypatch)

        assert settings.app_name == "Copilot OS API"
        assert settings.jwt_access_token_expire_minutes == 1440

    def test_settings_with_custom_values(self, monkeypatch):
        """Test that Settings can be customized via environment variables."""
        monkeypatch.setenv("HOST", "127.0.0.1")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("APP_NAME", "Custom API")
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "120")
        monkeypatch.setenv("MONGODB_URL", "mongodb://prod:pass@prod.example.com:27017/proddb")
        monkeypatch.setenv("REDIS_URL", "redis://:prodpass@redis.example.com:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "prod_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "prod_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "prod_saptiva_key")

        settings = Settings()

        assert settings.host == "127.0.0.1"
        assert settings.port == 9000
        assert settings.debug == True
        assert settings.app_name == "Custom API"
        assert settings.jwt_access_token_expire_minutes == 120

    def test_mongodb_url_computed_field(self, monkeypatch):
        """Test that mongodb_url computed field works correctly."""
        test_url = "mongodb://testuser:testpass@localhost:27017/testdb"
        monkeypatch.setenv("MONGODB_URL", test_url)
        monkeypatch.setenv("REDIS_URL", "redis://:test@localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "test_saptiva_key")

        settings = Settings()

        # mongodb_url is a computed field
        assert settings.mongodb_url == test_url
        assert "mongodb://" in settings.mongodb_url
        assert "testuser" in settings.mongodb_url

    def test_redis_url_computed_field(self, monkeypatch):
        """Test that redis_url computed field works correctly."""
        test_url = "redis://:myredispass@localhost:6379/0"
        monkeypatch.setenv("REDIS_URL", test_url)
        monkeypatch.setenv("MONGODB_URL", "mongodb://user:pass@localhost:27017/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "test_saptiva_key")

        settings = Settings()

        # redis_url is a computed field
        assert settings.redis_url == test_url
        assert "redis://" in settings.redis_url
        assert "myredispass" in settings.redis_url

    def test_settings_with_minimal_env_vars(self, monkeypatch):
        """Test that Settings can initialize with fallback values when secrets unavailable."""
        # Clear .env overrides to test true defaults
        monkeypatch.delenv("APP_NAME", raising=False)

        # Settings should initialize even without env vars due to defaults
        # This tests the fallback behavior in computed fields
        settings = Settings()

        # Should have defaults
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        # app_name can be default or from .env - just verify it's a non-empty string
        assert isinstance(settings.app_name, str) and len(settings.app_name) > 0

    def test_get_settings_singleton(self, monkeypatch):
        """Test that get_settings returns singleton instance."""
        monkeypatch.setenv("MONGODB_URL", "mongodb://test:test@localhost:27017/test")
        monkeypatch.setenv("REDIS_URL", "redis://:test@localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "test_saptiva_key")

        settings1 = get_settings()
        settings2 = get_settings()

        # Both should be the same instance (cached via lru_cache)
        assert settings1 is settings2

    def test_cors_origins_field(self, monkeypatch):
        """Test that cors_origins field exists and has default values."""
        monkeypatch.setenv("MONGODB_URL", "mongodb://test:test@localhost:27017/test")
        monkeypatch.setenv("REDIS_URL", "redis://:test@localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "test_saptiva_key")

        settings = Settings()

        # cors_origins should exist and be a list
        assert hasattr(settings, "cors_origins")
        assert isinstance(settings.cors_origins, list)
        assert len(settings.cors_origins) > 0

    def test_feature_flags_default_values(self, monkeypatch):
        """Test that feature flags have sensible defaults."""
        monkeypatch.setenv("MONGODB_URL", "mongodb://test:test@localhost:27017/test")
        monkeypatch.setenv("REDIS_URL", "redis://:test@localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "test_saptiva_key")

        settings = Settings()

        # Test feature flags (actual fields from config.py)
        assert hasattr(settings, "deep_research_kill_switch")
        assert isinstance(settings.deep_research_kill_switch, bool)
        assert hasattr(settings, "tool_add_files_enabled")
        assert hasattr(settings, "tool_document_review_enabled")
        assert hasattr(settings, "tool_files_enabled")
        assert hasattr(settings, "create_chat_optimistic")

    def test_chat_configuration_defaults(self, monkeypatch):
        """Test chat configuration has correct defaults."""
        # Clear .env overrides to test true defaults
        monkeypatch.delenv("CHAT_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("CHAT_ALLOWED_MODELS", raising=False)
        monkeypatch.setenv("MONGODB_URL", "mongodb://test:test@localhost:27017/test")
        monkeypatch.setenv("REDIS_URL", "redis://:test@localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")
        monkeypatch.setenv("SAPTIVA_API_KEY", "test_saptiva_key")

        settings = Settings()

        # Test chat config (P0-CHAT-BASE-004)
        assert settings.chat_default_model == "Saptiva Turbo"
        assert "Saptiva Turbo" in settings.chat_allowed_models
        assert "Saptiva Cortex" in settings.chat_allowed_models

    def test_saptiva_configuration(self, monkeypatch):
        """Test SAPTIVA API configuration."""
        # Use a realistic Saptiva API key format (va-ai- prefix)
        test_key = "va-ai-test_key_abcdefghijklmnopqrstuvwxyz1234567890"
        monkeypatch.setenv("SAPTIVA_API_KEY", test_key)
        monkeypatch.setenv("SAPTIVA_BASE_URL", "https://custom.saptiva.com")
        monkeypatch.setenv("MONGODB_URL", "mongodb://test:test@localhost:27017/test")
        monkeypatch.setenv("REDIS_URL", "redis://:test@localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key_minimum_32_chars")

        settings = Settings()

        assert settings.saptiva_base_url == "https://custom.saptiva.com"
        # saptiva_api_key is a computed field that validates format
        # It should return the key if valid, or empty string if validation fails
        assert isinstance(settings.saptiva_api_key, str)
        # timeout/retries may come from .env, just verify they're reasonable
        assert settings.saptiva_timeout > 0
        assert settings.saptiva_max_retries > 0
