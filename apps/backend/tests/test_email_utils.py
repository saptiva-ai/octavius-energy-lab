"""
Tests for email normalization and validation utilities.

These tests ensure that email handling is consistent across
registration, login, and user lookup operations.
"""

import pytest

from src.core.email_utils import (
    normalize_email,
    is_valid_email_format,
    sanitize_email_for_lookup,
    get_email_validation_error,
)


class TestNormalizeEmail:
    """Test email normalization function."""

    def test_basic_normalization(self):
        """Test basic email normalization."""
        assert normalize_email("user@example.com") == "user@example.com"

    def test_uppercase_to_lowercase(self):
        """Test uppercase letters are converted to lowercase."""
        assert normalize_email("USER@EXAMPLE.COM") == "user@example.com"
        assert normalize_email("User@Example.COM") == "user@example.com"

    def test_mixed_case_normalization(self):
        """Test mixed case email normalization - THE BUG WE'RE FIXING."""
        # This is the exact case reported: Test4@saptiva.com vs test4@saptiva.com
        assert normalize_email("Test4@saptiva.com") == "test4@saptiva.com"
        assert normalize_email("TEST4@SAPTIVA.COM") == "test4@saptiva.com"
        assert normalize_email("test4@saptiva.com") == "test4@saptiva.com"

    def test_whitespace_stripping(self):
        """Test whitespace is stripped from both ends."""
        assert normalize_email("  user@example.com  ") == "user@example.com"
        assert normalize_email("\tuser@example.com\n") == "user@example.com"
        assert normalize_email("   USER@EXAMPLE.COM   ") == "user@example.com"

    def test_consecutive_dots_removal(self):
        """Test consecutive dots in local part are normalized."""
        assert normalize_email("user..name@example.com") == "user.name@example.com"
        assert normalize_email("user...test@example.com") == "user.test@example.com"
        assert normalize_email("a....b@example.com") == "a.b@example.com"

    def test_complex_normalization(self):
        """Test complex normalization combining multiple rules."""
        assert normalize_email("  User..Test@Example.COM  ") == "user.test@example.com"
        assert normalize_email("\tTEST..USER@DOMAIN.ORG\n") == "test.user@domain.org"

    def test_subdomain_normalization(self):
        """Test emails with subdomains are normalized correctly."""
        assert normalize_email("user@mail.example.com") == "user@mail.example.com"
        assert normalize_email("USER@MAIL.EXAMPLE.COM") == "user@mail.example.com"

    def test_special_characters_preserved(self):
        """Test that valid special characters are preserved."""
        assert normalize_email("user+tag@example.com") == "user+tag@example.com"
        assert normalize_email("user_name@example.com") == "user_name@example.com"
        assert normalize_email("user-name@example.com") == "user-name@example.com"
        assert normalize_email("user.name@example.com") == "user.name@example.com"

    def test_invalid_email_missing_at(self):
        """Test that email without @ raises ValueError."""
        with pytest.raises(ValueError, match="missing @ symbol"):
            normalize_email("userexample.com")

    def test_invalid_email_empty_local(self):
        """Test that email with empty local part raises ValueError."""
        with pytest.raises(ValueError, match="empty local or domain part"):
            normalize_email("@example.com")

    def test_invalid_email_empty_domain(self):
        """Test that email with empty domain raises ValueError."""
        with pytest.raises(ValueError, match="empty local or domain part"):
            normalize_email("user@")

    def test_invalid_email_empty_string(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="non-empty string"):
            normalize_email("")

    def test_invalid_email_whitespace_only(self):
        """Test that whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="missing @ symbol"):
            normalize_email("   ")

    def test_invalid_email_none(self):
        """Test that None raises ValueError."""
        with pytest.raises(ValueError, match="non-empty string"):
            normalize_email(None)

    def test_invalid_email_multiple_at(self):
        """Test email with multiple @ is handled (uses rightmost @)."""
        # This is intentional - we use rsplit to handle edge cases gracefully
        result = normalize_email("user@test@example.com")
        assert result == "user@test@example.com"


class TestIsValidEmailFormat:
    """Test email format validation."""

    def test_valid_emails(self):
        """Test that valid email formats return True."""
        assert is_valid_email_format("user@example.com") is True
        assert is_valid_email_format("test@test.org") is True
        assert is_valid_email_format("user.name@example.co.uk") is True
        assert is_valid_email_format("user+tag@example.com") is True

    def test_invalid_emails(self):
        """Test that invalid email formats return False."""
        assert is_valid_email_format("invalid") is False
        assert is_valid_email_format("@example.com") is False
        assert is_valid_email_format("user@") is False
        assert is_valid_email_format("user") is False
        assert is_valid_email_format("") is False


class TestSanitizeEmailForLookup:
    """Test identifier sanitization for user lookup."""

    def test_email_sanitization(self):
        """Test that emails are normalized."""
        assert sanitize_email_for_lookup("Test4@Saptiva.COM") == "test4@saptiva.com"
        assert sanitize_email_for_lookup("  USER@EXAMPLE.COM  ") == "user@example.com"

    def test_username_sanitization(self):
        """Test that usernames are lowercased and stripped."""
        assert sanitize_email_for_lookup("JohnDoe123") == "johndoe123"
        assert sanitize_email_for_lookup("  AdminUser  ") == "adminuser"
        assert sanitize_email_for_lookup("TEST_USER") == "test_user"

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        assert sanitize_email_for_lookup("   username   ") == "username"
        assert sanitize_email_for_lookup("  email@test.com  ") == "email@test.com"

    def test_malformed_email_fallback(self):
        """Test that malformed emails fall back to lowercase."""
        # If normalization fails, it should just lowercase and strip
        result = sanitize_email_for_lookup("user@")
        assert result == "user@"  # Fallback behavior


class TestGetEmailValidationError:
    """Test email validation error messages."""

    def test_valid_email_returns_none(self):
        """Test that valid emails return None."""
        assert get_email_validation_error("user@example.com") is None
        assert get_email_validation_error("test@test.org") is None

    def test_empty_email(self):
        """Test error message for empty email."""
        error = get_email_validation_error("")
        assert "requerido" in error.lower()

    def test_missing_at_symbol(self):
        """Test error message for missing @ symbol."""
        error = get_email_validation_error("userexample.com")
        assert "@" in error

    def test_multiple_at_symbols(self):
        """Test error message for multiple @ symbols."""
        error = get_email_validation_error("user@@example.com")
        assert "@" in error

    def test_missing_local_part(self):
        """Test error message for missing local part."""
        error = get_email_validation_error("@example.com")
        assert "antes del @" in error.lower()

    def test_missing_domain(self):
        """Test error message for missing domain."""
        error = get_email_validation_error("user@")
        assert "dominio" in error.lower()

    def test_missing_domain_extension(self):
        """Test error message for missing domain extension."""
        error = get_email_validation_error("user@example")
        assert "punto" in error.lower()

    def test_consecutive_dots(self):
        """Test error message for consecutive dots."""
        error = get_email_validation_error("user..name@example.com")
        assert "consecutivos" in error.lower()


class TestRealWorldScenarios:
    """Test real-world authentication scenarios."""

    def test_registration_login_consistency(self):
        """
        Test that registration and login normalize emails identically.

        This is the critical test that validates our fix:
        - User registers with "Test4@Saptiva.COM"
        - System stores "test4@saptiva.com"
        - User logs in with "TEST4@saptiva.com"
        - System should find the user
        """
        # Simulate registration normalization
        registered_email = normalize_email("Test4@Saptiva.COM")

        # Simulate various login attempts
        login_attempts = [
            "test4@saptiva.com",
            "Test4@saptiva.com",
            "TEST4@SAPTIVA.COM",
            "  Test4@Saptiva.COM  ",
            "test4@SAPTIVA.com",
        ]

        for attempt in login_attempts:
            login_email = sanitize_email_for_lookup(attempt)
            assert login_email == registered_email, (
                f"Login attempt '{attempt}' normalized to '{login_email}' "
                f"but should match registered email '{registered_email}'"
            )

    def test_common_user_errors(self):
        """Test that common user input errors are handled."""
        # Leading/trailing spaces
        assert normalize_email("  user@test.com  ") == "user@test.com"

        # Mixed case (most common error)
        assert normalize_email("User@Test.Com") == "user@test.com"

        # Accidental double dots
        assert normalize_email("user..name@test.com") == "user.name@test.com"

        # Tab characters
        assert normalize_email("\tuser@test.com\t") == "user@test.com"

    def test_edge_cases_from_production(self):
        """Test edge cases that might occur in production."""
        # All uppercase
        assert normalize_email("ADMIN@COMPANY.COM") == "admin@company.com"

        # CamelCase
        assert normalize_email("JohnDoe@Company.Com") == "johndoe@company.com"

        # Numbers mixed with letters
        assert normalize_email("User123@Test456.Com") == "user123@test456.com"

        # Special characters preserved
        assert normalize_email("User+Tag@Example.Com") == "user+tag@example.com"
        assert normalize_email("User_Name@Example.Com") == "user_name@example.com"
