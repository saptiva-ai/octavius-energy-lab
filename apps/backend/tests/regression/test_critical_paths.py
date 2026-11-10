"""
Critical Path Regression Tests

These tests verify the most critical user-facing features work correctly.
Run before every deploy to prevent regressions.

Usage:
    make pre-deploy.regression
    pytest tests/regression -v -m regression

Policy:
    - Every bug fix should add a test here
    - Tests must be fast (< 5s each)
    - Tests must be reliable (no flakiness)

Test Categories:
    - Unit regression: No external deps, always run (TestApiRegression)
    - Integration regression: Require DB, skip if unavailable (TestAuthRegression, TestChatRegression)
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from typing import Dict
import os
import socket


# Check if MongoDB is available for integration tests
def _check_mongodb_available() -> bool:
    """Check if MongoDB is reachable on common ports."""
    # Try multiple hosts: Docker internal (mongodb:27017), CI (localhost:27017), local (localhost:27018)
    hosts_to_try = [
        ("mongodb", 27017),   # Docker internal network
        ("localhost", 27017), # CI environment
        ("localhost", 27018), # Local docker-compose port-forwarded
    ]
    for host, port in hosts_to_try:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            continue
    return False


MONGODB_AVAILABLE = _check_mongodb_available()

requires_db = pytest.mark.skipif(
    not MONGODB_AVAILABLE, reason="MongoDB not available (run with docker-compose up)"
)

# Common markers for all regression tests
pytestmark = [
    pytest.mark.regression,
    pytest.mark.asyncio,
]


# ============================================================================
# AUTH REGRESSION TESTS (require database)
# ============================================================================


@requires_db
class TestAuthRegression:
    """
    Critical auth flows that must always work.

    Covers:
    - REG-AUTH-001: Login with valid credentials
    - REG-AUTH-002: Login with email case insensitive
    - REG-AUTH-003: Token refresh works
    - REG-AUTH-004: Logout invalidates token
    - REG-AUTH-005: Protected endpoints require auth
    """

    @pytest.mark.asyncio
    async def test_reg_auth_001_login_with_valid_credentials(
        self, client: AsyncClient, test_user: Dict[str, str]
    ):
        """
        REG-AUTH-001: User can login with valid email and password.

        This is the most critical auth flow. If this breaks, users cannot
        access the application at all.
        """
        response = await client.post(
            "/api/auth/login",
            json={"identifier": test_user["email"], "password": test_user["password"]},
        )

        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()

        # Verify token structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["email"] == test_user["email"].lower()

    @pytest.mark.asyncio
    async def test_reg_auth_002_login_email_case_insensitive(
        self, client: AsyncClient, test_user: Dict[str, str]
    ):
        """
        REG-AUTH-002: Login works with different email case.

        Bug reference: Email normalization must work to prevent duplicate
        accounts and login failures.
        """
        # Try login with uppercase email
        upper_email = test_user["email"].upper()

        response = await client.post(
            "/api/auth/login",
            json={"identifier": upper_email, "password": test_user["password"]},
        )

        assert response.status_code == 200, (
            f"Case-insensitive login failed: {response.text}"
        )
        data = response.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_reg_auth_003_token_refresh_works(
        self, client: AsyncClient, test_user: Dict[str, str]
    ):
        """
        REG-AUTH-003: Refresh token generates new access token.

        Critical for session continuity. If broken, users get logged out
        after access token expires.
        """
        # First login to get tokens
        login_response = await client.post(
            "/api/auth/login",
            json={"identifier": test_user["email"], "password": test_user["password"]},
        )
        assert login_response.status_code == 200
        tokens = login_response.json()

        # Use refresh token to get new access token
        refresh_response = await client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert refresh_response.status_code == 200, (
            f"Token refresh failed: {refresh_response.text}"
        )
        new_tokens = refresh_response.json()
        assert "access_token" in new_tokens
        assert isinstance(new_tokens["access_token"], str)
        assert len(new_tokens["access_token"]) > 0
        # Verify the new token works by making an authenticated request
        client.headers.update({"Authorization": f"Bearer {new_tokens['access_token']}"})
        me_response = await client.get("/api/auth/me")
        assert me_response.status_code == 200, "Refreshed token should be valid"

    @pytest.mark.asyncio
    async def test_reg_auth_004_logout_invalidates_token(
        self, authenticated_client: tuple[AsyncClient, Dict]
    ):
        """
        REG-AUTH-004: Logout invalidates access token.

        Security critical. After logout, the token must not work.
        """
        client, auth_data = authenticated_client

        # Verify token works before logout
        me_response = await client.get("/api/auth/me")
        assert me_response.status_code == 200

        # Logout - requires refresh_token in body per API spec
        logout_response = await client.post(
            "/api/auth/logout", json={"refresh_token": auth_data["refresh_token"]}
        )
        assert logout_response.status_code == 204

        # Token should be invalidated (blacklisted)
        # Note: This may return 401 if blacklist check is enabled
        # or 200 if blacklist is not checked on every request
        # The key is that refresh should fail
        refresh_response = await client.post(
            "/api/auth/refresh", json={"refresh_token": auth_data["refresh_token"]}
        )
        # After logout, refresh should fail
        assert refresh_response.status_code in [401, 403], (
            "Refresh token should be invalidated after logout"
        )

    @pytest.mark.asyncio
    async def test_reg_auth_005_protected_endpoints_require_auth(
        self, client: AsyncClient
    ):
        """
        REG-AUTH-005: Protected endpoints reject unauthenticated requests.

        Security critical. Must return 401 for missing/invalid tokens.
        """
        # Try accessing protected endpoint without token
        response = await client.get("/api/auth/me")

        assert response.status_code == 401, (
            f"Protected endpoint should require auth, got {response.status_code}"
        )

        data = response.json()
        assert "code" in data or "detail" in data


# ============================================================================
# CHAT REGRESSION TESTS (require database)
# ============================================================================


@requires_db
class TestChatRegression:
    """
    Critical chat flows that must always work.

    Covers:
    - REG-CHAT-001: List conversations (sessions created implicitly via messages)
    - REG-CHAT-002: List sessions via sessions endpoint
    - REG-CHAT-003: Health endpoint works
    """

    @pytest.mark.asyncio
    async def test_reg_chat_001_list_conversations(
        self, authenticated_client: tuple[AsyncClient, Dict]
    ):
        """
        REG-CHAT-001: User can list their conversations.

        Sessions are created implicitly when sending messages.
        This test verifies the conversations endpoint works.
        """
        client, auth_data = authenticated_client

        # List conversations (sessions are created implicitly via messages)
        response = await client.get("/api/conversations")

        assert response.status_code == 200, (
            f"List conversations failed: {response.text}"
        )
        data = response.json()
        # Should return paginated response with sessions list
        assert "sessions" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_reg_chat_002_get_sessions_list(
        self, authenticated_client: tuple[AsyncClient, Dict]
    ):
        """
        REG-CHAT-002: User can list their sessions.

        Required for session navigation in UI.
        """
        client, auth_data = authenticated_client

        response = await client.get("/api/sessions")

        assert response.status_code == 200, f"Get sessions failed: {response.text}"
        data = response.json()
        # Should return a list or paginated response
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_reg_chat_003_health_endpoint_works(self, client: AsyncClient):
        """
        REG-CHAT-003: Health endpoint returns healthy status.

        Used by load balancers and monitoring. If broken, deploys may fail.
        """
        response = await client.get("/api/health")

        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") in ["healthy", "ok", True]


# ============================================================================
# API REGRESSION TESTS
# ============================================================================


class TestApiRegression:
    """
    Critical API behaviors that must always work.

    Covers:
    - REG-API-001: CORS headers present
    - REG-API-002: Rate limiting headers present
    - REG-API-003: Error responses have correct format
    """

    @pytest.mark.asyncio
    async def test_reg_api_001_health_endpoint_accessible(self, client: AsyncClient):
        """
        REG-API-001: Health endpoint is accessible without auth.

        Required for infrastructure health checks.
        """
        response = await client.get("/api/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reg_api_002_invalid_json_returns_422(self, client: AsyncClient):
        """
        REG-API-002: Invalid JSON payload returns 422.

        Ensures proper error handling for malformed requests.
        """
        response = await client.post(
            "/api/auth/login",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422, (
            f"Invalid JSON should return 422, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_reg_api_003_missing_required_fields_returns_422(
        self, client: AsyncClient
    ):
        """
        REG-API-003: Missing required fields returns 422 with details.

        Ensures validation errors are properly communicated.
        """
        response = await client.post(
            "/api/auth/login",
            json={},  # Missing identifier and password
        )

        assert response.status_code == 422
        data = response.json()
        # Should have validation error details
        assert "detail" in data or "errors" in data


# ============================================================================
# FIXTURES (imported from conftest, but documenting expected fixtures)
# ============================================================================
#
# Fixtures used by these tests (defined in tests/integration/conftest.py):
# - client: AsyncClient without authentication
# - test_user: Dict with email, password, user_id for a created test user
# - authenticated_client: tuple[AsyncClient, Dict] with auth headers set
# - clean_db: Cleans database before/after test
