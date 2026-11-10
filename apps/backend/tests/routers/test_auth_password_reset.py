"Comprehensive tests for Stateless Password Reset endpoints in routers/auth.py"

import sys
import types

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from jwt.exceptions import ExpiredSignatureError, PyJWTError as JWTError
from fastapi import HTTPException

# Stub fastapi_mail before any import of email_service triggers it
if "fastapi_mail" not in sys.modules:
    _fm = types.ModuleType("fastapi_mail")
    _fm.ConnectionConfig = Mock()
    _fm.FastMail = Mock()
    _fm.MessageSchema = Mock()
    _fm.MessageType = Mock()
    sys.modules["fastapi_mail"] = _fm

from src.routers.auth import router as auth_router
from src.core.config import get_settings
from src.core.exceptions import APIError
from src.models.user import User

@pytest.fixture
def app(mock_settings):
    """Create a minimal FastAPI app for testing without middleware."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    test_app = FastAPI()

    # Register exception handlers
    @test_app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    @test_app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    test_app.include_router(auth_router)
    test_app.dependency_overrides[get_settings] = lambda: mock_settings
    return test_app

@pytest.fixture
def client(app):
    """FastAPI test client."""
    return TestClient(app)

@pytest.fixture
def mock_user():
    """Mock user for testing."""
    user = Mock(spec=User)
    user.id = "user-123"
    user.username = "testuser"
    user.email = "test@example.com"
    user.password_hash = "hashed_old_password"
    user.save = AsyncMock()
    return user

@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = Mock()
    settings.password_reset_url_base = "http://localhost:3000"
    settings.smtp_user = "test@smtp.example.com"
    settings.smtp_password = "smtp-secret"
    return settings

class TestForgotPasswordEndpoint:
    def test_forgot_password_success(self, client, mock_user):
        """Test successful forgot password request."""
        payload = {"email": "test@example.com"}

        with patch('src.models.user.User') as MockUser, \
             patch('src.routers.auth.create_password_reset_token') as mock_create_token, \
             patch('src.services.email_service.get_email_service') as mock_get_email_service:

            MockUser.find_one = AsyncMock(return_value=mock_user)
            mock_create_token.return_value = "valid_token"

            mock_email_service = Mock()
            mock_email_service.send_password_reset_email = AsyncMock(return_value=True)
            mock_get_email_service.return_value = mock_email_service

            response = client.post("/auth/forgot-password", json=payload)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["email"] == "test@example.com"
            assert "recibirás un enlace" in data["message"]

            mock_email_service.send_password_reset_email.assert_called_once()
            # Verify token is in the link
            call_args = mock_email_service.send_password_reset_email.call_args
            assert "token=valid_token" in call_args.kwargs['reset_link']

    def test_forgot_password_user_not_found(self, client):
        """Test forgot password with non-existent email (should still return 200)."""
        payload = {"email": "unknown@example.com"}

        with patch('src.models.user.User') as MockUser, \
             patch('src.routers.auth.create_password_reset_token') as mock_create_token:

            MockUser.find_one = AsyncMock(return_value=None)

            response = client.post("/auth/forgot-password", json=payload)

            assert response.status_code == status.HTTP_200_OK
            assert "recibirás un enlace" in response.json()["message"]

            # Should NOT create token
            mock_create_token.assert_not_called()

class TestResetPasswordEndpoint:
    def test_reset_password_success(self, client, mock_user):
        """Test successful password reset."""
        payload = {
            "token": "valid_token",
            "new_password": "NewPassword123!"
        }

        with patch('src.routers.auth.verify_password_reset_token') as mock_verify, \
             patch('src.models.user.User') as MockUser, \
             patch('passlib.hash.argon2.hash') as mock_hash:

            mock_verify.return_value = "test@example.com"
            MockUser.find_one = AsyncMock(return_value=mock_user)
            mock_hash.return_value = "new_hashed_password"

            response = client.post("/auth/reset-password", json=payload)

            assert response.status_code == status.HTTP_200_OK
            assert "actualizada exitosamente" in response.json()["message"]

            # Verify password update
            assert mock_user.password_hash == "new_hashed_password"
            mock_user.save.assert_called_once()

    def test_reset_password_invalid_token(self, client):
        """Test reset with invalid token."""
        payload = {
            "token": "invalid_token",
            "new_password": "NewPassword123!"
        }

        with patch('src.routers.auth.verify_password_reset_token') as mock_verify:
            # Simulate invalid token exception from security module
            mock_verify.side_effect = HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enlace de recuperación inválido"
            )

            response = client.post("/auth/reset-password", json=payload)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Enlace de recuperación inválido" in response.json()["detail"]

    def test_reset_password_expired_token(self, client):
        """Test reset with expired token."""
        payload = {
            "token": "expired_token",
            "new_password": "NewPassword123!"
        }

        with patch('src.routers.auth.verify_password_reset_token') as mock_verify:
            mock_verify.side_effect = HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El enlace de recuperación ha expirado"
            )

            response = client.post("/auth/reset-password", json=payload)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "El enlace de recuperación ha expirado" in response.json()["detail"]

    def test_reset_password_user_not_found(self, client):
        """Test reset where token is valid but user is gone."""
        payload = {
            "token": "valid_token",
            "new_password": "NewPassword123!"
        }

        with patch('src.routers.auth.verify_password_reset_token') as mock_verify, \
             patch('src.models.user.User') as MockUser:

            mock_verify.return_value = "deleted@example.com"
            MockUser.find_one = AsyncMock(return_value=None)

            response = client.post("/auth/reset-password", json=payload)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Usuario no encontrado" in response.json()["detail"]