"""
Unit tests for rate limiting middleware.

Tests the slowapi-based rate limiting implementation.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.middleware.rate_limit import (
    RateLimitMiddleware,
    limiter,
    get_user_id_or_ip,
    _rate_limit_exceeded_handler,
)


@pytest.fixture
def app_with_rate_limit():
    """Create a test FastAPI app with rate limiting enabled."""
    app = FastAPI()

    @app.get("/api/test")
    async def test_endpoint():
        return {"message": "success"}

    # Add rate limit middleware
    app.add_middleware(RateLimitMiddleware)

    return app


@pytest.fixture
def client_rate_limit(app_with_rate_limit):
    """Create a test client for rate-limited app."""
    return TestClient(app_with_rate_limit)


class TestRateLimitMiddleware:
    """Test suite for RateLimitMiddleware."""

    def test_middleware_allows_requests_within_limit(self, client_rate_limit):
        """Test that requests within rate limit are allowed."""
        # Make a single request (should be allowed)
        response = client_rate_limit.get("/api/test")

        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_middleware_is_pass_through(self, client_rate_limit):
        """Test that the middleware acts as pass-through (rate limiting is via decorators)."""
        # The RateLimitMiddleware is a placeholder - actual limiting is via @limiter.limit()
        # Multiple requests should all pass through the middleware
        for _ in range(5):
            response = client_rate_limit.get("/api/test")
            assert response.status_code == 200

    def test_middleware_dispatch_passes_request(self):
        """Test that middleware dispatch correctly passes requests."""
        middleware = RateLimitMiddleware(app=Mock())
        assert middleware is not None
        # Middleware should have dispatch method
        assert hasattr(middleware, 'dispatch')


class TestGetUserIdOrIp:
    """Test the key function for rate limiting."""

    def test_get_user_id_from_authenticated_user(self):
        """Test extracting user ID from authenticated request."""
        mock_request = Mock(spec=Request)
        mock_user = Mock()
        mock_user.id = "user-123"
        mock_request.state = Mock()
        mock_request.state.user = mock_user
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}

        result = get_user_id_or_ip(mock_request)

        assert result == "user:user-123"

    def test_get_ip_from_unauthenticated_request(self):
        """Test extracting IP from unauthenticated request."""
        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.user = None
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}

        result = get_user_id_or_ip(mock_request)

        assert result == "ip:192.168.1.100"

    def test_get_ip_when_no_state_user(self):
        """Test fallback to IP when user not in state."""
        mock_request = Mock(spec=Request)
        # No user attribute on state
        mock_request.state = Mock(spec=[])  # Empty spec, no 'user' attribute
        mock_request.client = Mock()
        mock_request.client.host = "10.0.0.1"
        mock_request.headers = {}

        result = get_user_id_or_ip(mock_request)

        assert result == "ip:10.0.0.1"


class TestRateLimitExceededHandler:
    """Test rate limit exceeded error handler."""

    @pytest.mark.asyncio
    async def test_handler_returns_429_response(self):
        """Test that handler returns proper 429 response."""
        from slowapi.errors import RateLimitExceeded

        mock_request = Mock(spec=Request)
        mock_exc = Mock(spec=RateLimitExceeded)
        mock_exc.retry_after = 60

        response = await _rate_limit_exceeded_handler(mock_request, mock_exc)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "60"

    @pytest.mark.asyncio
    async def test_handler_default_retry_after(self):
        """Test handler uses default retry_after when not set."""
        from slowapi.errors import RateLimitExceeded

        mock_request = Mock(spec=Request)
        mock_exc = Mock(spec=RateLimitExceeded)
        # Remove retry_after attribute to test default
        del mock_exc.retry_after

        response = await _rate_limit_exceeded_handler(mock_request, mock_exc)

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"  # Default value


class TestLimiterConfiguration:
    """Test limiter configuration."""

    def test_limiter_exists(self):
        """Test that limiter is properly initialized."""
        assert limiter is not None
        assert hasattr(limiter, 'limit')

    def test_limiter_has_key_func(self):
        """Test that limiter has custom key function."""
        # The limiter should use our custom key function
        assert limiter._key_func is not None


class TestRateLimitIntegration:
    """Integration tests for rate limiting with decorator."""

    def test_endpoint_with_limiter_decorator(self):
        """Test endpoint decorated with @limiter.limit works."""
        app = FastAPI()
        app.state.limiter = limiter

        @app.get("/api/limited")
        @limiter.limit("5/minute")
        async def limited_endpoint(request: Request):
            return {"message": "limited"}

        app.add_middleware(RateLimitMiddleware)

        client = TestClient(app)
        response = client.get("/api/limited")

        # First request should succeed
        assert response.status_code == 200

    def test_middleware_initializes_correctly(self):
        """Test that middleware can be instantiated."""
        app = FastAPI()
        middleware = RateLimitMiddleware(app)

        assert middleware is not None
        assert middleware.app == app
