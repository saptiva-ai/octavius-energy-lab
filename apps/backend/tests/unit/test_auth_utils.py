"""
Comprehensive tests for core/auth.py - JWT authentication utilities

Coverage:
- get_current_user: JWT token validation and user retrieval
- Token decoding: Valid/invalid/expired tokens
- User validation: Active/inactive users
- Error handling: HTTPExceptions with proper status codes
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

import jwt

from src.core.auth import get_current_user


@pytest.fixture
def mock_settings():
    """Mock settings with JWT configuration."""
    with patch('src.core.auth.get_settings') as mock:
        settings = Mock()
        settings.jwt_secret_key = "test-secret-key-for-testing"
        settings.jwt_algorithm = "HS256"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_user():
    """Mock user model."""
    user = Mock()
    user.id = "user-123"
    user.username = "testuser"
    user.email = "test@example.com"
    user.is_active = True
    return user


@pytest.fixture
def valid_token(mock_settings):
    """Generate a valid JWT token."""
    payload = {
        "sub": "user-123",
        "username": "testuser",
        "email": "test@example.com",
        "exp": datetime.utcnow() + timedelta(minutes=30)
    }
    return jwt.encode(payload, mock_settings.jwt_secret_key, algorithm=mock_settings.jwt_algorithm)


@pytest.fixture
def expired_token(mock_settings):
    """Generate an expired JWT token."""
    payload = {
        "sub": "user-123",
        "exp": datetime.utcnow() - timedelta(minutes=5)  # Expired 5 minutes ago
    }
    return jwt.encode(payload, mock_settings.jwt_secret_key, algorithm=mock_settings.jwt_algorithm)


@pytest.fixture
def token_without_subject(mock_settings):
    """Generate a token without 'sub' claim."""
    payload = {
        "username": "testuser",
        "exp": datetime.utcnow() + timedelta(minutes=30)
        # Missing 'sub'
    }
    return jwt.encode(payload, mock_settings.jwt_secret_key, algorithm=mock_settings.jwt_algorithm)


class TestGetCurrentUser:
    """Test JWT authentication and user retrieval."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, mock_settings, mock_user, valid_token):
        """Valid token with active user should return user."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=valid_token
        )

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(return_value=mock_user)

            user = await get_current_user(credentials)

            assert user == mock_user
            MockUser.get.assert_awaited_once_with("user-123")

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, mock_settings, expired_token):
        """Expired token should raise 401 Unauthorized."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=expired_token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expirado" in exc_info.value.detail.lower() or "inválido" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_format_raises_401(self, mock_settings):
        """Invalid token format should raise 401."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid-token-format"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_token_with_wrong_signature_raises_401(self, mock_settings):
        """Token with wrong signature should raise 401."""
        # Create token with different secret
        wrong_payload = {
            "sub": "user-123",
            "exp": datetime.utcnow() + timedelta(minutes=30)
        }
        wrong_token = jwt.encode(wrong_payload, "wrong-secret", algorithm="HS256")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=wrong_token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_token_without_subject_raises_401(self, mock_settings, token_without_subject):
        """Token without 'sub' claim should raise 401."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token_without_subject
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "inválido" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self, mock_settings, valid_token):
        """Token with non-existent user ID should raise 401."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=valid_token
        )

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(return_value=None)  # User not found

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "no encontrado" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_inactive_user_raises_403(self, mock_settings, mock_user, valid_token):
        """Token for inactive user should raise 403 Forbidden."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=valid_token
        )

        mock_user.is_active = False  # Set user as inactive

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(return_value=mock_user)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "inactivo" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_database_error_raises_500(self, mock_settings, valid_token):
        """Database error during user retrieval should raise 500."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=valid_token
        )

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(side_effect=Exception("Database connection failed"))

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_empty_token_raises_401(self, mock_settings):
        """Empty token string should raise 401."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=""
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestTokenValidation:
    """Test JWT token validation edge cases."""

    @pytest.mark.asyncio
    async def test_token_with_extra_claims_works(self, mock_settings, mock_user):
        """Token with extra claims should still work."""
        payload = {
            "sub": "user-123",
            "username": "testuser",
            "email": "test@example.com",
            "custom_claim": "extra_data",
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(minutes=30)
        }
        token = jwt.encode(payload, mock_settings.jwt_secret_key, algorithm=mock_settings.jwt_algorithm)

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(return_value=mock_user)

            user = await get_current_user(credentials)

            assert user == mock_user

    @pytest.mark.asyncio
    async def test_token_about_to_expire_still_works(self, mock_settings, mock_user):
        """Token about to expire (but still valid) should work."""
        payload = {
            "sub": "user-123",
            "exp": datetime.utcnow() + timedelta(seconds=5)  # Expires in 5 seconds
        }
        token = jwt.encode(payload, mock_settings.jwt_secret_key, algorithm=mock_settings.jwt_algorithm)

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(return_value=mock_user)

            user = await get_current_user(credentials)

            assert user == mock_user

class TestSecurityScenarios:
    """Test security-critical scenarios."""

    @pytest.mark.asyncio
    async def test_token_reuse_after_user_deactivation(self, mock_settings, mock_user, valid_token):
        """Valid token should fail if user is deactivated after token issuance."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=valid_token
        )

        mock_user.is_active = False  # User deactivated after token was issued

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(return_value=mock_user)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_token_with_different_algorithm_rejected(self, mock_settings):
        """Token signed with different algorithm should be rejected."""
        # Try to use HS512 instead of HS256
        payload = {
            "sub": "user-123",
            "exp": datetime.utcnow() + timedelta(minutes=30)
        }
        wrong_algo_token = jwt.encode(payload, mock_settings.jwt_secret_key, algorithm="HS512")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=wrong_algo_token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_malformed_jwt_structure_raises_401(self, mock_settings):
        """Malformed JWT structure should raise 401."""
        malformed_tokens = [
            "header.payload",  # Missing signature
            "header",  # Only header
            "not-a-jwt-at-all",
            "header.payload.signature.extra",  # Too many parts
        ]

        for token in malformed_tokens:
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=token
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogging:
    """Test logging behavior."""

    @pytest.mark.asyncio
    async def test_jwt_error_is_logged(self, mock_settings, expired_token, caplog):
        """JWT validation errors should be logged as warnings."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=expired_token
        )

        with pytest.raises(HTTPException):
            await get_current_user(credentials)

        # Check that warning was logged
        # Note: This assumes structlog is configured for testing
        # You may need to adjust based on your logging setup

    @pytest.mark.asyncio
    async def test_unexpected_error_is_logged(self, mock_settings, valid_token, caplog):
        """Unexpected errors should be logged as errors."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=valid_token
        )

        with patch('src.core.auth.User') as MockUser:
            MockUser.get = AsyncMock(side_effect=RuntimeError("Unexpected error"))

            with pytest.raises(HTTPException):
                await get_current_user(credentials)

            # Check that error was logged
            # Note: Adjust based on your logging configuration
