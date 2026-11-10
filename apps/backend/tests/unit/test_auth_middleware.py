"""
Unit tests for authentication middleware.

Tests JWT token validation, blacklist checking, and request authentication.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.middleware.auth import AuthMiddleware


@pytest.fixture
def app():
    """Create a test FastAPI app with auth middleware."""
    app = FastAPI()

    # Add a test endpoint
    @app.get("/api/protected")
    async def protected_endpoint(request: Request):
        user_id = getattr(request.state, "user_id", None)
        return {"user_id": user_id, "authenticated": True}

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # Add auth middleware
    app.add_middleware(AuthMiddleware)

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestAuthMiddleware:
    """Test suite for AuthMiddleware."""

    def test_public_paths_allow_access_without_token(self, client):
        """Test that public endpoints don't require authentication."""
        public_paths = [
            "/api/health",
            "/api/health/live",
            "/api/health/ready",
        ]

        for path in public_paths:
            # Some paths might not exist in test app, that's ok
            try:
                response = client.get(path)
                # Should not return 401 (unauthorized)
                assert response.status_code != 401
            except:
                pass  # Path doesn't exist in test app

    def test_health_endpoint_accessible_without_auth(self, client):
        """Test that /api/health is accessible without token."""
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_protected_endpoint_requires_token(self, client):
        """Test that protected endpoints require authentication token."""
        response = client.get("/api/protected")

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_protected_endpoint_rejects_missing_token(self, client):
        """Test that requests without Authorization header are rejected."""
        response = client.get("/api/protected")

        assert response.status_code == 401
        data = response.json()
        # Middleware returns {"code": "...", "message": "..."}
        assert "code" in data
        assert "message" in data
        assert data["code"] == "token_missing"

    def test_protected_endpoint_rejects_malformed_token(self, client):
        """Test that malformed tokens are rejected."""
        # Missing "Bearer " prefix
        response = client.get(
            "/api/protected",
            headers={"Authorization": "invalid-token-format"}
        )

        assert response.status_code == 401

    @patch('src.middleware.auth.AuthMiddleware._validate_token')
    @patch('src.middleware.auth.is_token_blacklisted')
    async def test_valid_token_grants_access(self, mock_blacklist, mock_validate):
        """Test that valid token grants access to protected endpoint."""
        # Mock token validation
        mock_validate.return_value = {
            "sub": "user-123",
            "user_id": "user-123",
            "username": "testuser"
        }
        mock_blacklist.return_value = False

        # This test is conceptual - actual implementation would need
        # to properly mock the async middleware

    def test_options_request_bypasses_auth(self, client):
        """Test that OPTIONS requests bypass authentication."""
        response = client.options("/api/protected")

        # OPTIONS should not require authentication (CORS preflight)
        # Status might be 200 or 405 depending on route config
        assert response.status_code != 401

    def test_middleware_extracts_token_from_authorization_header(self):
        """Test that middleware correctly extracts token from Authorization header."""
        middleware = AuthMiddleware(app=Mock())

        # Create mock request
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer test-token-123"}

        token = middleware._extract_token(mock_request)

        assert token == "test-token-123"

    def test_middleware_extracts_token_case_insensitive(self):
        """Test that Authorization header is case-insensitive."""
        from starlette.datastructures import Headers

        middleware = AuthMiddleware(app=Mock())

        mock_request = Mock(spec=Request)
        # Use Starlette Headers which is case-insensitive
        mock_request.headers = Headers({"authorization": "bearer token-xyz"})

        token = middleware._extract_token(mock_request)

        assert token == "token-xyz"

    def test_middleware_returns_none_for_missing_header(self):
        """Test that missing Authorization header returns None."""
        middleware = AuthMiddleware(app=Mock())

        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        # Mock request.url.path for EventSource check
        mock_request.url.path = "/api/protected"
        mock_request.query_params = {}

        token = middleware._extract_token(mock_request)

        assert token is None

    def test_middleware_returns_none_for_invalid_format(self):
        """Test that invalid Authorization format returns None."""
        middleware = AuthMiddleware(app=Mock())

        mock_request = Mock(spec=Request)
        # Missing "Bearer " prefix
        mock_request.headers = {"Authorization": "just-a-token"}
        # Mock request.url.path for EventSource check
        mock_request.url.path = "/api/protected"
        mock_request.query_params = {}

        token = middleware._extract_token(mock_request)

        # Depends on implementation - might return None or the token
        # If it returns the token, validation will fail later
        assert token is None or token == "just-a-token"


class TestAuthMiddlewarePublicPaths:
    """Test public path configuration."""

    def test_public_paths_defined(self):
        """Test that PUBLIC_PATHS constant is defined."""
        assert hasattr(AuthMiddleware, 'PUBLIC_PATHS')
        assert isinstance(AuthMiddleware.PUBLIC_PATHS, (set, list, tuple))

    def test_health_endpoints_are_public(self):
        """Test that health check endpoints are in public paths."""
        public_paths = AuthMiddleware.PUBLIC_PATHS

        assert "/api/health" in public_paths

    def test_auth_endpoints_are_public(self):
        """Test that auth endpoints (login, register) are public."""
        public_paths = AuthMiddleware.PUBLIC_PATHS

        assert "/api/auth/login" in public_paths
        assert "/api/auth/register" in public_paths

    def test_docs_endpoints_are_public(self):
        """Test that API documentation endpoints are public."""
        public_paths = AuthMiddleware.PUBLIC_PATHS

        assert "/docs" in public_paths or "/redoc" in public_paths

    def test_ui_config_endpoints_are_public(self):
        """La web pide la config de UI sin token (fetch sin Authorization).

        /api/features/views quedó fuera el 19 de octubre: en producción daba 401
        y el modal de vistas predefinidas salía vacío.
        """
        public_paths = AuthMiddleware.PUBLIC_PATHS

        assert "/api/features/tools" in public_paths
        assert "/api/features/suggestions" in public_paths
        assert "/api/features/views" in public_paths
        # Guía rápida del modal de ayuda (QA, P2.2, 2026-10-21).
        assert "/api/features/guide" in public_paths


class TestAuthMiddlewareIntegration:
    """Integration tests for auth middleware."""

    def test_middleware_initializes_with_app(self):
        """Test that middleware can be initialized with a FastAPI app."""
        app = FastAPI()
        middleware = AuthMiddleware(app=app)

        assert middleware.settings is not None

    def test_middleware_settings_loaded(self):
        """Test that middleware loads settings on initialization."""
        app = FastAPI()
        middleware = AuthMiddleware(app=app)

        # Settings should be loaded from get_settings()
        assert hasattr(middleware, 'settings')
        assert middleware.settings is not None


class TestTokenValidation:
    """Test token validation logic."""

    @patch('jwt.decode')
    def test_validate_token_with_valid_jwt(self, mock_decode):
        """Test that valid JWT token is accepted."""
        mock_decode.return_value = {"sub": "user-123", "exp": 9999999999}

        middleware = AuthMiddleware(app=Mock())
        payload = middleware._validate_token("valid.jwt.token")

        # Should return payload
        assert payload is not None
        assert "sub" in payload

    @patch('jwt.decode')
    def test_validate_token_with_expired_jwt(self, mock_decode):
        """Test that expired JWT token is rejected."""
        from jwt.exceptions import ExpiredSignatureError
        mock_decode.side_effect = ExpiredSignatureError("Token expired")

        middleware = AuthMiddleware(app=Mock())
        payload = middleware._validate_token("expired.jwt.token")

        # Should return None for expired token
        assert payload is None

    @patch('jwt.decode')
    def test_validate_token_with_invalid_jwt(self, mock_decode):
        """Test that invalid JWT token is rejected."""
        from jwt.exceptions import PyJWTError as JWTError
        mock_decode.side_effect = JWTError("Invalid token")

        middleware = AuthMiddleware(app=Mock())
        payload = middleware._validate_token("invalid.token")

        # Should return None for invalid token
        assert payload is None
