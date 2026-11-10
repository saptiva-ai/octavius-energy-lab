"""
Unit tests for user schemas.

Tests Pydantic models for user management.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from src.schemas.user import (
    UserPreferences,
    UserCreate,
    UserUpdate,
    User
)


@pytest.mark.unit
class TestUserSchemas:
    """Test user schema models"""

    def test_user_preferences_defaults(self, monkeypatch):
        """Test UserPreferences with default values"""
        # default_model usa default_chat_model() -> get_settings() (cacheado),
        # que refleja CHAT_DEFAULT_MODEL del entorno; fijar el default real.
        from types import SimpleNamespace

        monkeypatch.setattr(
            "src.core.config.get_settings",
            lambda: SimpleNamespace(chat_default_model="Saptiva Turbo"),
        )
        prefs = UserPreferences()

        assert prefs.theme == "auto"
        assert prefs.language == "en"
        assert prefs.default_model == "Saptiva Turbo"
        assert prefs.chat_settings == {}

    def test_user_preferences_custom(self):
        """Test UserPreferences with custom values"""
        prefs = UserPreferences(
            theme="dark",
            language="es",
            default_model="SAPTIVA_TURBO",
            chat_settings={"temperature": 0.7, "max_tokens": 1000}
        )

        assert prefs.theme == "dark"
        assert prefs.language == "es"
        assert prefs.default_model == "SAPTIVA_TURBO"
        assert prefs.chat_settings["temperature"] == 0.7

    def test_user_create_minimal(self):
        """Test UserCreate with minimal required fields"""
        user = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePass123"
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.password == "SecurePass123"
        assert user.preferences is None

    def test_user_create_with_preferences(self):
        """Test UserCreate with preferences"""
        prefs = UserPreferences(theme="light", language="fr")
        user = UserCreate(
            username="frenchuser",
            email="user@example.fr",
            password="Password123",
            preferences=prefs
        )

        assert user.preferences is not None
        assert user.preferences.theme == "light"
        assert user.preferences.language == "fr"

    def test_user_create_validation_short_username(self):
        """Test UserCreate rejects username < 2 characters"""
        with pytest.raises(ValidationError):
            UserCreate(
                username="a",
                email="test@example.com",
                password="Password123"
            )

    def test_user_create_validation_long_username(self):
        """Test UserCreate rejects username > 60 characters"""
        with pytest.raises(ValidationError):
            UserCreate(
                username="a" * 61,
                email="test@example.com",
                password="Password123"
            )

    def test_user_create_validation_short_password(self):
        """Test UserCreate requires password >= 8 characters"""
        with pytest.raises(ValidationError):
            UserCreate(
                username="user",
                email="test@example.com",
                password="short"
            )

    def test_user_create_validation_invalid_email(self):
        """Test UserCreate rejects invalid email"""
        with pytest.raises(ValidationError):
            UserCreate(
                username="user",
                email="not-an-email",
                password="Password123"
            )

    def test_user_create_unicode_username(self):
        """Test UserCreate accepts Unicode characters"""
        user = UserCreate(
            username="José María",
            email="jose@example.com",
            password="Password123"
        )

        assert user.username == "José María"

    def test_user_create_special_chars_username(self):
        """Test UserCreate accepts special characters in username"""
        user = UserCreate(
            username="jean.o'connor-smith",
            email="jean@example.com",
            password="Password123"
        )

        assert user.username == "jean.o'connor-smith"

    def test_user_update_optional_fields(self):
        """Test UserUpdate with optional fields"""
        update = UserUpdate()

        assert update.email is None
        assert update.preferences is None

    def test_user_update_email_only(self):
        """Test UserUpdate updating only email"""
        update = UserUpdate(email="newemail@example.com")

        assert update.email == "newemail@example.com"
        assert update.preferences is None

    def test_user_update_preferences_only(self):
        """Test UserUpdate updating only preferences"""
        prefs = UserPreferences(theme="dark")
        update = UserUpdate(preferences=prefs)

        assert update.email is None
        assert update.preferences is not None
        assert update.preferences.theme == "dark"

    def test_user_schema_creation(self):
        """Test User schema model"""
        now = datetime.utcnow()
        user = User(
            id="user-123",
            created_at=now,
            updated_at=now,
            username="testuser",
            email="test@example.com",
            is_active=True,
            preferences=UserPreferences()
        )

        assert user.id == "user-123"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.last_login is None

    def test_user_schema_with_last_login(self):
        """Test User schema with last_login"""
        now = datetime.utcnow()
        user = User(
            id="user-456",
            created_at=now,
            updated_at=now,
            username="activeuser",
            email="active@example.com",
            is_active=True,
            last_login=now
        )

        assert user.last_login is not None
        assert user.last_login == now

    def test_user_schema_inactive(self):
        """Test User schema for inactive user"""
        now = datetime.utcnow()
        user = User(
            id="user-789",
            created_at=now,
            updated_at=now,
            username="inactive",
            email="inactive@example.com",
            is_active=False
        )

        assert user.is_active is False

    def test_user_schema_json_serialization(self):
        """Test User schema can be serialized"""
        now = datetime.utcnow()
        user = User(
            id="user-1",
            created_at=now,
            updated_at=now,
            username="user",
            email="user@example.com",
            is_active=True
        )

        json_data = user.model_dump()
        assert json_data["id"] == "user-1"
        assert json_data["username"] == "user"
        assert "created_at" in json_data
        assert isinstance(json_data, dict)

    def test_user_preferences_json_schema(self):
        """Test UserPreferences generates valid JSON schema"""
        schema = UserPreferences.model_json_schema()
        assert "properties" in schema
        assert "theme" in schema["properties"]
        assert "language" in schema["properties"]
        assert "default_model" in schema["properties"]
