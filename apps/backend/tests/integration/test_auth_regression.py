import pytest
from fastapi.testclient import TestClient
from src.main import create_app

class TestAuthRobustness:
    """
    Ensures that while Tidewave is whitelisted, other sensitive 
    endpoints remain strictly protected.
    """

    @pytest.fixture
    def client(self):
        return TestClient(create_app())

    def test_tidewave_paths_are_public(self, client):
        """TC-S1: Verify Tidewave endpoints are accessible without token (as configured)."""
        # GET /tidewave/mcp usually returns 405 or 200 depending on method, 
        # but NOT 401 Unauthorized.
        response = client.get("/tidewave/mcp")
        assert response.status_code != 401

    def test_sensitive_endpoints_are_protected(self, client):
        """TC-S2: Verify that standard API endpoints STILL require a token."""
        # /api/chat is NOT in the whitelist
        response = client.post("/api/chat", json={"content": "test"})
        assert response.status_code == 401
        assert response.json()["code"] == "token_missing"

    def test_auth_whitelist_integrity(self, client):
        """TC-S3: Ensure no accidental expansion of the whitelist."""
        # /api/users or similar management paths
        response = client.get("/api/users/me")
        assert response.status_code == 401
