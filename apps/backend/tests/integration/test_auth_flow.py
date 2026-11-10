"""
Integration tests for complete authentication flows.

Tests the entire auth journey:
1. User registration → DB persistence
2. Login → JWT generation
3. Token refresh → New tokens
4. Protected endpoint access → Authorization
5. Logout → Token invalidation
"""
import pytest
from httpx import AsyncClient
from src.models.user import User


class TestRegistrationFlow:
    """Test complete user registration flow."""

    @pytest.mark.asyncio
    async def test_register_creates_user_in_database(self, client: AsyncClient, clean_db):
        """Should register user and persist to MongoDB."""
        # Register new user
        response = await client.post(
            "/api/auth/register",
            json={
                "username": "New User",
                "email": "newuser@example.com",
                "password": "SecurePass123"
            }
        )

        assert response.status_code == 201, f"Registration failed: {response.json()}"
        data = response.json()

        # Verify response structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["username"] == "New User"

        # Verify user exists in database
        user = await User.find_one(User.email == "newuser@example.com")
        assert user is not None
        assert user.is_active is True

    @pytest.mark.asyncio
    async def test_register_with_duplicate_email_fails(self, client: AsyncClient, test_user):
        """Should reject registration with existing email."""
        response = await client.post(
            "/api/auth/register",
            json={
                "username": "Duplicate User",
                "email": test_user["email"],  # Already exists
                "password": "AnotherPass123"
            }
        )

        assert response.status_code in [400, 409], "Should reject duplicate email"
        assert "email" in response.json()["detail"].lower() or "existe" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_with_weak_password_fails(self, client: AsyncClient, clean_db):
        """Should reject weak passwords."""
        response = await client.post(
            "/api/auth/register",
            json={
                "username": "Weak Password User",
                "email": "weak@example.com",
                "password": "weak"  # Too short, no uppercase, no digit
            }
        )

        # Should fail validation (422) or business logic (400)
        assert response.status_code in [400, 422], "Should reject weak password"


class TestLoginFlow:
    """Test login and token generation."""

    @pytest.mark.asyncio
    async def test_login_with_valid_credentials_returns_tokens(self, client: AsyncClient, test_user):
        """Should login successfully and return JWT tokens."""
        response = await client.post(
            "/api/auth/login",
            json={
                "identifier": test_user["email"],
                "password": test_user["password"]
            }
        )

        assert response.status_code == 200, f"Login failed: {response.json()}"
        data = response.json()

        # Verify tokens present
        assert "access_token" in data
        assert "refresh_token" in data
        assert len(data["access_token"]) > 50  # JWT is reasonably long
        assert len(data["refresh_token"]) > 50

        # Verify user data
        assert data["user"]["email"] == test_user["email"]
        assert data["user"]["username"] == test_user["username"]

    @pytest.mark.asyncio
    async def test_login_with_wrong_password_fails(self, client: AsyncClient, test_user):
        """Should reject login with incorrect password."""
        response = await client.post(
            "/api/auth/login",
            json={
                "identifier": test_user["email"],
                "password": "WrongPassword123"
            }
        )

        assert response.status_code == 401, "Should return 401 for wrong password"
        detail_lower = response.json()["detail"].lower()
        assert "credenciales" in detail_lower or "password" in detail_lower or "contraseña" in detail_lower or "incorrectos" in detail_lower

    @pytest.mark.asyncio
    async def test_login_with_nonexistent_email_fails(self, client: AsyncClient, clean_db):
        """Should reject login for non-existent user."""
        response = await client.post(
            "/api/auth/login",
            json={
                "identifier": "nonexistent@example.com",
                "password": "SomePass123"
            }
        )

        assert response.status_code == 401, "Should return 401 for non-existent user"


class TestTokenRefreshFlow:
    """Test token refresh mechanism."""

    @pytest.mark.asyncio
    async def test_refresh_token_generates_new_access_token(self, client: AsyncClient, test_user):
        """Should generate new access token using refresh token."""
        # First login
        login_response = await client.post(
            "/api/auth/login",
            json={
                "identifier": test_user["email"],
                "password": test_user["password"]
            }
        )
        assert login_response.status_code == 200
        initial_tokens = login_response.json()
        initial_access_token = initial_tokens["access_token"]
        refresh_token = initial_tokens["refresh_token"]

        # Wait 1 second to ensure new token has different timestamp
        import asyncio
        await asyncio.sleep(1)

        # Refresh tokens
        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert refresh_response.status_code == 200, f"Refresh failed: {refresh_response.json()}"
        new_tokens = refresh_response.json()

        # Verify new access token
        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != initial_access_token, "Should generate NEW token"

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token_fails(self, client: AsyncClient, clean_db):
        """Should reject invalid refresh tokens."""
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid.token.here"}
        )

        assert response.status_code == 401, "Should reject invalid refresh token"


class TestProtectedEndpointAccess:
    """Test accessing protected endpoints with authentication."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_requires_authentication(self, client: AsyncClient, clean_db):
        """Should reject requests without authentication."""
        # Try to access /auth/me without token
        response = await client.get("/api/auth/me")

        assert response.status_code == 401, "Should require authentication"

    @pytest.mark.asyncio
    async def test_protected_endpoint_accepts_valid_token(self, client: AsyncClient, test_user):
        """Should allow access with valid JWT."""
        # Login to get token
        login_response = await client.post(
            "/api/auth/login",
            json={
                "identifier": test_user["email"],
                "password": test_user["password"]
            }
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        # Access protected endpoint
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200, f"Should allow access: {response.json()}"
        user_data = response.json()
        assert user_data["email"] == test_user["email"]

    @pytest.mark.asyncio
    async def test_protected_endpoint_rejects_expired_token(self, client: AsyncClient, clean_db):
        """Should reject expired JWT tokens."""
        # Create an expired token (you might need a helper to forge this)
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6MTYwMDAwMDAwMH0.invalid"

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

        assert response.status_code == 401, "Should reject expired token"


class TestLogoutFlow:
    """Test logout and token invalidation."""

    @pytest.mark.asyncio
    async def test_logout_invalidates_refresh_token(self, client: AsyncClient, test_user):
        """Should invalidate refresh token on logout."""
        # Login
        login_response = await client.post(
            "/api/auth/login",
            json={
                "identifier": test_user["email"],
                "password": test_user["password"]
            }
        )
        assert login_response.status_code == 200
        tokens = login_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]

        # Logout
        logout_response = await client.post(
            "/api/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert logout_response.status_code in [200, 204], f"Logout failed with status {logout_response.status_code}"

        # Try to refresh with invalidated token
        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert refresh_response.status_code == 401, "Should reject invalidated refresh token"


class TestCompleteAuthJourney:
    """Test end-to-end auth lifecycle."""

    @pytest.mark.asyncio
    async def test_full_user_lifecycle(self, client: AsyncClient, clean_db):
        """Test complete flow: register → login → refresh → protected access → logout."""
        # 1. Register
        register_response = await client.post(
            "/api/auth/register",
            json={
                "username": "Lifecycle User",
                "email": "lifecycle@example.com",
                "password": "LifeCycle123"
            }
        )
        assert register_response.status_code == 201, "Registration failed"
        initial_tokens = register_response.json()

        # 2. Login with new account
        login_response = await client.post(
            "/api/auth/login",
            json={
                "identifier": "lifecycle@example.com",
                "password": "LifeCycle123"
            }
        )
        assert login_response.status_code == 200, "Login failed"
        login_tokens = login_response.json()

        # 3. Refresh token
        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == 200, "Refresh failed"
        new_access_token = refresh_response.json()["access_token"]

        # 4. Access protected endpoint
        me_response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert me_response.status_code == 200, "Protected access failed"
        assert me_response.json()["email"] == "lifecycle@example.com"

        # 5. Logout
        logout_response = await client.post(
            "/api/auth/logout",
            json={"refresh_token": login_tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {new_access_token}"}
        )
        assert logout_response.status_code in [200, 204], f"Logout failed with status {logout_response.status_code}"

        # 6. Verify token invalidated
        refresh_again = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_again.status_code == 401, "Token should be invalidated"
