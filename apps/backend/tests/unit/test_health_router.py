"""
Unit tests for health check router.

Tests health endpoint responsiveness and status reporting.
"""

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from src.routers.health import router as health_router


@pytest.fixture
def app():
    """Create a test FastAPI app with health router."""
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test suite for health check endpoint."""

    def test_health_endpoint_returns_200(self, client):
        """Test that health endpoint returns 200 OK."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK

    def test_health_endpoint_returns_json(self, client):
        """Test that health endpoint returns JSON response."""
        response = client.get("/health")

        assert response.headers["content-type"] == "application/json"

    def test_health_endpoint_response_format(self, client):
        """Test that health endpoint returns expected response format."""
        response = client.get("/health")
        data = response.json()

        # Should have status field
        assert "status" in data
        assert data["status"] in ["healthy", "ok", "up"]

    def test_health_endpoint_includes_timestamp(self, client):
        """Test that health response may include timestamp."""
        response = client.get("/health")
        data = response.json()

        # Timestamp is optional but useful for monitoring
        # This test passes whether or not timestamp is included
        if "timestamp" in data:
            assert isinstance(data["timestamp"], str)

    def test_health_endpoint_no_authentication_required(self, client):
        """Test that health endpoint doesn't require authentication."""
        # Health check should be accessible without auth
        response = client.get("/health")

        # Should not return 401 Unauthorized
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_health_endpoint_responds_quickly(self, client):
        """Test that health endpoint responds in reasonable time."""
        import time

        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start

        assert response.status_code == status.HTTP_200_OK
        # Health check should respond in less than 1 second
        assert elapsed < 1.0

    def test_health_endpoint_idempotent(self, client):
        """Test that health endpoint is idempotent (multiple calls return same result)."""
        response1 = client.get("/health")
        response2 = client.get("/health")
        response3 = client.get("/health")

        # All should return 200
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
        assert response3.status_code == status.HTTP_200_OK

        # Status should be consistent
        assert response1.json()["status"] == response2.json()["status"]
        assert response2.json()["status"] == response3.json()["status"]

    def test_health_endpoint_different_http_methods(self, client):
        """Test that health endpoint only accepts GET requests."""
        # GET should work
        get_response = client.get("/health")
        assert get_response.status_code == status.HTTP_200_OK

        # POST should return 405 Method Not Allowed
        post_response = client.post("/health")
        assert post_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_health_endpoint_concurrent_requests(self, client):
        """Test that health endpoint can handle concurrent requests."""
        import concurrent.futures

        def make_request():
            return client.get("/health")

        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            responses = [future.result() for future in concurrent.futures.as_completed(futures)]

        # All should succeed
        assert all(r.status_code == status.HTTP_200_OK for r in responses)
        assert len(responses) == 10
