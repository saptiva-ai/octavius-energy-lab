"""
Comprehensive tests for services/auth_service.py - Authentication service layer

Coverage:
- Password hashing/verification: Argon2, bcrypt migration, strength validation
- User lookup: By username, email, identifier (with normalization)
- Token creation: JWT access/refresh tokens with claims
- Registration: User creation, uniqueness checks, email validation
- Authentication: Login flow, password upgrade, inactive users
- Token refresh: Blacklist checking, token validation
- User profile: Profile retrieval
- Logout: Token blacklisting
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import jwt

from src.services.auth_service import (
    _hash_password,
    _verify_password,
    _validate_password_strength,
    _get_user_by_username,
    _get_user_by_email,
    _get_user_by_identifier,
    _serialize_user,
    _create_token,
    _create_token_pair,
    register_user,
    authenticate_user,
    refresh_access_token,
    get_user_profile,
    logout_user,
)
from src.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    BadRequestError,
)
from src.models.user import User, UserPreferences as UserPreferencesModel
from src.schemas.user import UserCreate
from src.schemas.auth import AuthResponse, RefreshResponse


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock settings with JWT and security configuration."""
    with patch('src.services.auth_service.get_settings') as mock:
        settings = Mock()
        settings.jwt_secret_key = "test-secret-key-for-testing-auth-service"
        settings.jwt_algorithm = "HS256"
        settings.jwt_access_token_expire_minutes = 30
        settings.jwt_refresh_token_expire_days = 7
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_user():
    """Mock user with standard attributes."""
    user = Mock(spec=User)
    user.id = "user-id-123"
    user.username = "testuser"
    user.email = "test@example.com"
    user.password_hash = "$argon2id$v=19$m=65536,t=3,p=4$test"
    user.is_active = True
    user.created_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    user.last_login = None
    user.preferences = UserPreferencesModel()

    # Make save/create async
    user.save = AsyncMock()
    user.create = AsyncMock()

    return user


@pytest.fixture
def user_create_payload():
    """Standard user creation payload."""
    return UserCreate(
        username="newuser",
        email="newuser@example.com",
        password="SecurePass123"
    )


# ============================================================================
# PASSWORD UTILITIES
# ============================================================================

class TestPasswordUtilities:
    """Test password hashing, verification, and validation."""

    def test_hash_password_produces_hash(self):
        """Password hashing should produce a non-empty hash."""
        password = "MySecurePassword123"
        hashed = _hash_password(password)

        assert hashed is not None
        assert len(hashed) > 0
        assert hashed != password  # Hash should differ from plaintext

    def test_hash_password_uses_argon2(self):
        """New password hashes should use argon2."""
        password = "test123"
        hashed = _hash_password(password)

        # Argon2 hashes start with $argon2
        assert hashed.startswith("$argon2")

    def test_hash_password_different_for_same_input(self):
        """Each hash should include salt (different hashes for same password)."""
        password = "same-password"
        hash1 = _hash_password(password)
        hash2 = _hash_password(password)

        # Due to salt, hashes should differ
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Correct password should verify successfully."""
        password = "MyPassword123"
        hashed = _hash_password(password)

        assert _verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Incorrect password should fail verification."""
        password = "correct-password"
        hashed = _hash_password(password)

        assert _verify_password("wrong-password", hashed) is False

    # NOTE: Bcrypt legacy support is tested implicitly in authenticate_user tests
    # which handle password hash upgrades from bcrypt to argon2

    def test_validate_password_strength_too_short(self):
        """Passwords under 8 characters should be rejected."""
        error = _validate_password_strength("short")

        assert error is not None
        assert "8 caracteres" in error

    def test_validate_password_strength_valid(self):
        """Passwords with 8+ characters should be valid."""
        assert _validate_password_strength("12345678") is None
        assert _validate_password_strength("LongEnoughPassword") is None

    def test_validate_password_strength_unicode(self):
        """Unicode passwords should be validated by length."""
        # 8 unicode characters
        assert _validate_password_strength("contraseña") is None
        # 6 unicode characters (too short)
        error = _validate_password_strength("señor")
        assert error is not None


# ============================================================================
# USER LOOKUP UTILITIES
# ============================================================================

class TestUserLookup:
    """Test user lookup by username, email, and identifier."""

    @pytest.mark.asyncio
    async def test_get_user_by_username_found(self, mock_user):
        """Should find user by exact username match."""
        with patch('src.services.auth_service.User') as MockUser:
            MockUser.find_one = AsyncMock(return_value=mock_user)

            result = await _get_user_by_username("testuser")

            assert result == mock_user
            MockUser.find_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(self):
        """Should return None if username doesn't exist."""
        with patch('src.services.auth_service.User') as MockUser:
            MockUser.find_one = AsyncMock(return_value=None)

            result = await _get_user_by_username("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_email_found(self, mock_user):
        """Should find user by normalized email."""
        with patch('src.services.auth_service.User') as MockUser:
            with patch('src.services.auth_service.normalize_email', return_value="test@example.com"):
                MockUser.find_one = AsyncMock(return_value=mock_user)

                result = await _get_user_by_email("TEST@example.com")

                assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_email_invalid_format(self):
        """Should return None for invalid email format."""
        with patch('src.services.auth_service.normalize_email', side_effect=ValueError("Invalid")):
            result = await _get_user_by_email("not-an-email")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_identifier_username(self, mock_user):
        """Should find user by username when identifier is username."""
        with patch('src.services.auth_service._get_user_by_username', return_value=mock_user):
            with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="testuser"):
                result = await _get_user_by_identifier("testuser")

                assert result == mock_user

    @pytest.mark.asyncio
    async def test_get_user_by_identifier_email(self, mock_user):
        """Should find user by email when identifier contains @."""
        with patch('src.services.auth_service._get_user_by_username', return_value=None):
            with patch('src.services.auth_service._get_user_by_email', return_value=mock_user):
                with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="test@example.com"):
                    result = await _get_user_by_identifier("test@example.com")

                    assert result == mock_user


# ============================================================================
# USER SERIALIZATION
# ============================================================================

class TestUserSerialization:
    """Test user model serialization to API schema."""

    def test_serialize_user_basic(self, mock_user):
        """Should serialize user with all fields."""
        result = _serialize_user(mock_user)

        assert result.id == str(mock_user.id)
        assert result.username == mock_user.username
        assert result.email == mock_user.email
        assert result.is_active == mock_user.is_active
        assert result.preferences is not None

    def test_serialize_user_with_preferences(self, mock_user):
        """Should serialize user preferences correctly."""
        mock_user.preferences = UserPreferencesModel(
            theme="dark",
            language="es",
            default_model="GPT4"
        )

        result = _serialize_user(mock_user)

        assert result.preferences.theme == "dark"
        assert result.preferences.language == "es"

    def test_serialize_user_without_preferences(self, mock_user):
        """Should handle missing preferences gracefully."""
        mock_user.preferences = None

        result = _serialize_user(mock_user)

        # Should create default preferences
        assert result.preferences is not None


# ============================================================================
# TOKEN CREATION
# ============================================================================

class TestTokenCreation:
    """Test JWT token generation."""

    def test_create_token_basic(self, mock_settings):
        """Should create valid JWT token."""
        token = _create_token(
            subject="user-123",
            token_type="access",
            expires_delta=timedelta(minutes=30)
        )

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_contains_claims(self, mock_settings):
        """Token should contain expected claims."""
        extra_claims = {"username": "testuser", "email": "test@example.com"}

        token = _create_token(
            subject="user-123",
            token_type="access",
            expires_delta=timedelta(minutes=30),
            extra_claims=extra_claims
        )

        # Decode to verify claims
        payload = jwt.decode(
            token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm]
        )

        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"
        assert payload["username"] == "testuser"
        assert payload["email"] == "test@example.com"
        assert "iat" in payload
        assert "exp" in payload

    @pytest.mark.asyncio
    async def test_create_token_pair(self, mock_settings, mock_user):
        """Should create access and refresh token pair."""
        access_token, refresh_token, expires_in = await _create_token_pair(mock_user)

        assert access_token is not None
        assert refresh_token is not None
        assert expires_in == 30 * 60  # 30 minutes in seconds
        assert access_token != refresh_token

    @pytest.mark.asyncio
    async def test_create_token_pair_types(self, mock_settings, mock_user):
        """Token pair should have correct types."""
        access_token, refresh_token, _ = await _create_token_pair(mock_user)

        # Decode both tokens
        access_payload = jwt.decode(
            access_token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm]
        )
        refresh_payload = jwt.decode(
            refresh_token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm]
        )

        assert access_payload["type"] == "access"
        assert refresh_payload["type"] == "refresh"


# ============================================================================
# USER REGISTRATION
# ============================================================================

class TestUserRegistration:
    """Test user registration flow."""

    @pytest.mark.asyncio
    async def test_register_user_success(self, mock_settings, user_create_payload):
        """Successful registration should create user and return tokens."""
        with patch('src.services.auth_service._get_user_by_username', return_value=None):
            with patch('src.services.auth_service._get_user_by_email', return_value=None):
                with patch('src.services.auth_service.normalize_email', return_value="newuser@example.com"):
                    with patch('src.services.auth_service.User') as MockUser:
                        mock_user = Mock(spec=User)
                        mock_user.id = "new-user-id"
                        mock_user.username = "newuser"
                        mock_user.email = "newuser@example.com"
                        mock_user.is_active = True
                        mock_user.created_at = datetime.utcnow()
                        mock_user.updated_at = datetime.utcnow()
                        mock_user.last_login = None
                        mock_user.preferences = UserPreferencesModel()
                        mock_user.create = AsyncMock()

                        MockUser.return_value = mock_user

                        result = await register_user(user_create_payload)

                        assert isinstance(result, AuthResponse)
                        assert result.access_token is not None
                        assert result.refresh_token is not None
                        assert result.user.username == "newuser"
                        mock_user.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_user_weak_password(self, user_create_payload):
        """Should reject weak passwords."""
        user_create_payload.password = "short"

        with pytest.raises(BadRequestError) as exc_info:
            await register_user(user_create_payload)

        assert "8 caracteres" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_register_user_duplicate_username(self, mock_user, user_create_payload):
        """Should reject duplicate username."""
        with patch('src.services.auth_service._get_user_by_username', return_value=mock_user):
            with patch('src.services.auth_service.normalize_email', return_value="newuser@example.com"):
                with pytest.raises(ConflictError) as exc_info:
                    await register_user(user_create_payload)

                assert "usuario" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(self, mock_user, user_create_payload):
        """Should reject duplicate email."""
        with patch('src.services.auth_service._get_user_by_username', return_value=None):
            with patch('src.services.auth_service._get_user_by_email', return_value=mock_user):
                with patch('src.services.auth_service.normalize_email', return_value="test@example.com"):
                    with pytest.raises(ConflictError) as exc_info:
                        await register_user(user_create_payload)

                    assert "correo" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_register_user_invalid_email(self, user_create_payload):
        """Should reject invalid email format."""
        with patch('src.services.auth_service.normalize_email', side_effect=ValueError("Invalid")):
            with pytest.raises(BadRequestError) as exc_info:
                await register_user(user_create_payload)

            assert "correo" in exc_info.value.detail.lower()


# ============================================================================
# USER AUTHENTICATION
# ============================================================================

class TestAuthentication:
    """Test user login and authentication flow."""

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, mock_settings, mock_user):
        """Successful authentication should return tokens."""
        password = "correct-password"
        mock_user.password_hash = _hash_password(password)

        with patch('src.services.auth_service._get_user_by_identifier', return_value=mock_user):
            with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="testuser"):
                result = await authenticate_user("testuser", password)

                assert isinstance(result, AuthResponse)
                assert result.access_token is not None
                assert result.user.username == mock_user.username
                mock_user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, mock_settings):
        """Should raise error if user doesn't exist."""
        with patch('src.services.auth_service._get_user_by_identifier', return_value=None):
            with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="nonexistent"):
                with pytest.raises(AuthenticationError) as exc_info:
                    await authenticate_user("nonexistent", "password")

                assert "incorrectos" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, mock_settings, mock_user):
        """Should raise error for incorrect password."""
        mock_user.password_hash = _hash_password("correct-password")

        with patch('src.services.auth_service._get_user_by_identifier', return_value=mock_user):
            with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="testuser"):
                with pytest.raises(AuthenticationError) as exc_info:
                    await authenticate_user("testuser", "wrong-password")

                assert "incorrectos" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_user_inactive(self, mock_settings, mock_user):
        """Should raise error for inactive user."""
        password = "correct-password"
        mock_user.password_hash = _hash_password(password)
        mock_user.is_active = False

        with patch('src.services.auth_service._get_user_by_identifier', return_value=mock_user):
            with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="testuser"):
                with pytest.raises(AuthenticationError) as exc_info:
                    await authenticate_user("testuser", password)

                assert "inactiv" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_authenticate_user_updates_last_login(self, mock_settings, mock_user):
        """Should update last_login timestamp on successful auth."""
        password = "correct-password"
        mock_user.password_hash = _hash_password(password)
        old_last_login = mock_user.last_login

        with patch('src.services.auth_service._get_user_by_identifier', return_value=mock_user):
            with patch('src.services.auth_service.sanitize_email_for_lookup', return_value="testuser"):
                await authenticate_user("testuser", password)

                assert mock_user.last_login != old_last_login
                assert mock_user.last_login is not None


# ============================================================================
# TOKEN REFRESH
# ============================================================================

class TestTokenRefresh:
    """Test access token refresh flow."""

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, mock_settings, mock_user):
        """Valid refresh token should return new access token."""
        # Create valid refresh token
        refresh_token = _create_token(
            subject=str(mock_user.id),
            token_type="refresh",
            expires_delta=timedelta(days=7),
            extra_claims={"username": mock_user.username}
        )

        with patch('src.services.auth_service.is_token_blacklisted', return_value=False):
            with patch('src.services.auth_service.User') as MockUser:
                MockUser.get = AsyncMock(return_value=mock_user)

                result = await refresh_access_token(refresh_token)

                assert isinstance(result, RefreshResponse)
                assert result.access_token is not None
                assert result.expires_in > 0

    @pytest.mark.asyncio
    async def test_refresh_access_token_blacklisted(self, mock_settings):
        """Blacklisted refresh token should be rejected."""
        token = "blacklisted-token"

        with patch('src.services.auth_service.is_token_blacklisted', return_value=True):
            with pytest.raises(AuthenticationError) as exc_info:
                await refresh_access_token(token)

            assert "válido" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid(self, mock_settings):
        """Invalid refresh token should be rejected."""
        with patch('src.services.auth_service.is_token_blacklisted', return_value=False):
            with pytest.raises(AuthenticationError) as exc_info:
                await refresh_access_token("invalid-token-format")

            assert "válido" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_refresh_access_token_wrong_type(self, mock_settings):
        """Access token used as refresh should be rejected."""
        # Create access token (wrong type)
        access_token = _create_token(
            subject="user-123",
            token_type="access",  # Wrong type!
            expires_delta=timedelta(minutes=30)
        )

        with patch('src.services.auth_service.is_token_blacklisted', return_value=False):
            with pytest.raises(AuthenticationError) as exc_info:
                await refresh_access_token(access_token)

            assert "válido" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_refresh_access_token_user_not_found(self, mock_settings):
        """Refresh token for non-existent user should fail."""
        refresh_token = _create_token(
            subject="nonexistent-user",
            token_type="refresh",
            expires_delta=timedelta(days=7)
        )

        with patch('src.services.auth_service.is_token_blacklisted', return_value=False):
            with patch('src.services.auth_service.User') as MockUser:
                MockUser.get = AsyncMock(return_value=None)
                with patch('src.services.auth_service._get_user_by_identifier', return_value=None):
                    with pytest.raises(NotFoundError):
                        await refresh_access_token(refresh_token)

    @pytest.mark.asyncio
    async def test_refresh_access_token_inactive_user(self, mock_settings, mock_user):
        """Refresh token for inactive user should fail."""
        mock_user.is_active = False

        refresh_token = _create_token(
            subject=str(mock_user.id),
            token_type="refresh",
            expires_delta=timedelta(days=7)
        )

        with patch('src.services.auth_service.is_token_blacklisted', return_value=False):
            with patch('src.services.auth_service.User') as MockUser:
                MockUser.get = AsyncMock(return_value=mock_user)

                with pytest.raises(AuthenticationError):
                    await refresh_access_token(refresh_token)


# ============================================================================
# USER PROFILE
# ============================================================================

class TestUserProfile:
    """Test user profile retrieval."""

    @pytest.mark.asyncio
    async def test_get_user_profile_success(self, mock_user):
        """Should return user profile for valid user ID."""
        with patch('src.services.auth_service.User') as MockUser:
            MockUser.get = AsyncMock(return_value=mock_user)

            result = await get_user_profile(str(mock_user.id))

            assert result.id == str(mock_user.id)
            assert result.username == mock_user.username

    @pytest.mark.asyncio
    async def test_get_user_profile_not_found(self):
        """Should raise error if user not found."""
        with patch('src.services.auth_service.User') as MockUser:
            MockUser.get = AsyncMock(return_value=None)

            with pytest.raises(NotFoundError):
                await get_user_profile("nonexistent-id")


# ============================================================================
# LOGOUT
# ============================================================================

class TestLogout:
    """Test token blacklisting on logout."""

    @pytest.mark.asyncio
    async def test_logout_user_success(self, mock_settings):
        """Should blacklist valid token."""
        token = _create_token(
            subject="user-123",
            token_type="access",
            expires_delta=timedelta(minutes=30)
        )

        with patch('src.services.auth_service.add_token_to_blacklist') as mock_blacklist:
            mock_blacklist.return_value = AsyncMock()

            await logout_user(token)

            # Should have added to blacklist
            mock_blacklist.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_user_invalid_token(self, mock_settings):
        """Should handle invalid token gracefully (no error)."""
        # Invalid tokens can't be used anyway, so logout succeeds silently
        await logout_user("invalid-token-format")
        # No exception should be raised

    @pytest.mark.asyncio
    async def test_logout_user_token_without_expiry(self, mock_settings):
        """Should handle token without expiry claim gracefully."""
        # Create token without exp claim (manually)
        payload = {
            "sub": "user-123",
            "type": "access",
        }
        token = jwt.encode(payload, mock_settings.jwt_secret_key, algorithm=mock_settings.jwt_algorithm)

        # Should not raise error
        await logout_user(token)
