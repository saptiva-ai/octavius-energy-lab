"""
Integration tests for authentication email normalization.

Tests the complete registration → login flow with various email formats
to ensure case-insensitive email handling works correctly.
"""

import pytest
import pytest_asyncio

from src.schemas.user import UserCreate
from src.services.auth_service import (
    register_user,
    authenticate_user,
    _get_user_by_email,
    _get_user_by_identifier,
)
from src.core.exceptions import ConflictError


@pytest.mark.asyncio
class TestAuthenticationEmailNormalization:
    """Test authentication with email normalization using real database."""

    async def test_register_with_mixed_case_email(self, clean_db):
        """
        Test that registration normalizes email to lowercase.

        Given: User registers with "Test4@Saptiva.COM"
        When: Email is stored in database
        Then: Email is normalized to "test4@saptiva.com"
        """
        # Register with mixed case email
        payload = UserCreate(
            username="testuser",
            email="Test4@Saptiva.COM",  # Mixed case
            password="SecurePass123"
        )

        response = await register_user(payload)

        # Verify email was normalized
        assert response.user.email == "test4@saptiva.com"

    async def test_login_with_different_case_succeeds(self, clean_db):
        """
        Test that login works regardless of email case - THE MAIN FIX.

        Given: User registered as "test4@saptiva.com"
        When: User logs in with various case variations
        Then: Login succeeds (email is normalized for lookup)
        """
        # Register user with specific email case
        register_payload = UserCreate(
            username="testuser",
            email="test4@saptiva.com",
            password="SecurePass123"
        )
        await register_user(register_payload)

        # Attempt login with different case variations
        login_attempts = [
            "Test4@Saptiva.COM",
            "TEST4@SAPTIVA.COM",
            "test4@saptiva.com",
            "  Test4@Saptiva.COM  ",  # With whitespace
        ]

        for email_attempt in login_attempts:
            response = await authenticate_user(email_attempt, "SecurePass123")
            assert response.access_token is not None
            assert response.user.email == "test4@saptiva.com"

    async def test_duplicate_email_detection_case_insensitive(self, clean_db):
        """
        Test that duplicate email detection works regardless of case.

        Given: User exists with "test4@saptiva.com"
        When: Someone tries to register with "Test4@Saptiva.COM"
        Then: Registration fails with conflict error
        """
        # Register first user
        payload1 = UserCreate(
            username="user1",
            email="test4@saptiva.com",
            password="SecurePass123"
        )
        await register_user(payload1)

        # Try to register with different case, different username
        payload2 = UserCreate(
            username="differentuser",
            email="Test4@Saptiva.COM",  # Same email, different case
            password="SecurePass123"
        )

        with pytest.raises(ConflictError, match="Ya existe una cuenta con ese correo"):
            await register_user(payload2)

    async def test_get_user_by_email_normalizes_input(self, clean_db):
        """Test that _get_user_by_email normalizes the input."""
        # Create a user
        payload = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePass123"
        )
        await register_user(payload)

        # Test with various formats
        test_cases = [
            "test@example.com",
            "Test@Example.Com",
            "TEST@EXAMPLE.COM",
            "  test@example.com  ",
        ]

        for email in test_cases:
            result = await _get_user_by_email(email)
            assert result is not None
            assert result.email == "test@example.com"

    async def test_get_user_by_identifier_handles_email(self, clean_db):
        """Test that _get_user_by_identifier normalizes email identifiers."""
        # Create a user
        payload = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePass123"
        )
        await register_user(payload)

        # Test with email identifier (case variations)
        result = await _get_user_by_identifier("Test@Example.Com")
        assert result is not None
        assert result.email == "test@example.com"

    async def test_get_user_by_identifier_handles_username(self, clean_db):
        """Test that _get_user_by_identifier handles usernames (no @)."""
        # Create a user
        payload = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePass123"
        )
        await register_user(payload)

        # Test with username identifier (no @)
        result = await _get_user_by_identifier("testuser")
        assert result is not None
        assert result.username == "testuser"


@pytest.mark.asyncio
class TestEdgeCasesAuthentication:
    """Test edge cases in authentication."""

    async def test_whitespace_in_email_register(self, clean_db):
        """Test that whitespace is stripped during registration."""
        payload = UserCreate(
            username="testuser",
            email="  test@example.com  ",  # Whitespace
            password="SecurePass123"
        )

        response = await register_user(payload)
        assert response.user.email == "test@example.com"

    async def test_whitespace_in_email_login(self, clean_db):
        """Test that whitespace is stripped during login."""
        # Register user
        payload = UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePass123"
        )
        await register_user(payload)

        # Login with whitespace
        response = await authenticate_user("  test@example.com  ", "SecurePass123")
        assert response.user.email == "test@example.com"


@pytest.mark.asyncio
class TestProductionScenarios:
    """Test real production scenarios reported by users."""

    async def test_scenario_test4_saptiva_bug(self, clean_db):
        """
        Test the exact bug scenario reported.

        Scenario:
        1. User registers with "Test4@saptiva.com"
        2. System stores "test4@saptiva.com"
        3. User tries to login with "Test4@saptiva.com"
        4. System should find user (previously failed)
        """
        # Register
        register_payload = UserCreate(
            username="test4",
            email="Test4@saptiva.com",
            password="MyPassword123"
        )
        register_response = await register_user(register_payload)

        # Verify normalized storage
        assert register_response.user.email == "test4@saptiva.com"

        # Login with original case
        login_response = await authenticate_user("Test4@saptiva.com", "MyPassword123")

        # Verify login succeeded
        assert login_response.access_token is not None
        assert login_response.user.email == "test4@saptiva.com"
        assert login_response.user.username == "test4"

    async def test_scenario_all_caps_email(self, clean_db):
        """Test user who types email in all caps."""
        # Register user
        register_payload = UserCreate(
            username="admin",
            email="admin@company.com",
            password="password"
        )
        await register_user(register_payload)

        # Login with ALL CAPS
        response = await authenticate_user("ADMIN@COMPANY.COM", "password")

        assert response.access_token is not None
        assert response.user.email == "admin@company.com"
