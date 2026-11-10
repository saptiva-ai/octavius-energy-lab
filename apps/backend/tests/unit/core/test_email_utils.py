"""
Unit tests for core/email_utils module.

Tests:
- normalize_email function
- is_valid_email_format function
- sanitize_email_for_lookup function
- get_email_validation_error function
"""

import pytest

from src.core.email_utils import (
    get_email_validation_error,
    is_valid_email_format,
    normalize_email,
    sanitize_email_for_lookup,
)

pytestmark = [pytest.mark.unit]


class TestNormalizeEmail:
    """Test normalize_email function."""

    def test_strips_whitespace(self):
        """Test strips leading and trailing whitespace."""
        result = normalize_email("  test@example.com  ")
        assert result == "test@example.com"

    def test_converts_to_lowercase(self):
        """Test converts email to lowercase."""
        result = normalize_email("Test@EXAMPLE.COM")
        assert result == "test@example.com"

    def test_removes_consecutive_dots(self):
        """Test removes consecutive dots in local part."""
        result = normalize_email("user..name@example.com")
        assert result == "user.name@example.com"

    def test_removes_multiple_consecutive_dots(self):
        """Test removes multiple consecutive dots."""
        result = normalize_email("user...name@example.com")
        assert result == "user.name@example.com"

    def test_combined_normalization(self):
        """Test combined normalization."""
        result = normalize_email("  Test4@Saptiva.COM  ")
        assert result == "test4@saptiva.com"

    def test_raises_on_empty_string(self):
        """Test raises ValueError on empty string."""
        with pytest.raises(ValueError, match="non-empty string"):
            normalize_email("")

    def test_raises_on_none(self):
        """Test raises ValueError on None."""
        with pytest.raises(ValueError, match="non-empty string"):
            normalize_email(None)

    def test_raises_on_missing_at_symbol(self):
        """Test raises ValueError on missing @ symbol."""
        with pytest.raises(ValueError, match="missing @ symbol"):
            normalize_email("invalidemail")

    def test_raises_on_empty_local_part(self):
        """Test raises ValueError on empty local part."""
        with pytest.raises(ValueError, match="empty local or domain part"):
            normalize_email("@example.com")

    def test_raises_on_empty_domain(self):
        """Test raises ValueError on empty domain."""
        with pytest.raises(ValueError, match="empty local or domain part"):
            normalize_email("user@")

    def test_handles_plus_addressing(self):
        """Test handles plus addressing correctly."""
        result = normalize_email("user+tag@example.com")
        assert result == "user+tag@example.com"

    def test_handles_dots_in_domain(self):
        """Test handles dots in domain correctly."""
        result = normalize_email("user@sub.domain.example.com")
        assert result == "user@sub.domain.example.com"


class TestIsValidEmailFormat:
    """Test is_valid_email_format function."""

    def test_valid_email_returns_true(self):
        """Test valid email returns True."""
        assert is_valid_email_format("user@example.com") is True

    def test_email_without_at_returns_false(self):
        """Test email without @ returns False."""
        assert is_valid_email_format("invalid.email") is False

    def test_email_without_domain_returns_false(self):
        """Test email without domain returns False."""
        assert is_valid_email_format("user@") is False

    def test_email_without_tld_returns_false(self):
        """Test email without TLD returns False."""
        assert is_valid_email_format("user@example") is False

    def test_valid_email_with_subdomain(self):
        """Test valid email with subdomain."""
        assert is_valid_email_format("user@mail.example.com") is True

    def test_valid_email_with_plus_addressing(self):
        """Test valid email with plus addressing."""
        assert is_valid_email_format("user+tag@example.com") is True

    def test_valid_email_with_numbers(self):
        """Test valid email with numbers."""
        assert is_valid_email_format("user123@example123.com") is True

    def test_valid_email_with_dots(self):
        """Test valid email with dots in local part."""
        assert is_valid_email_format("first.last@example.com") is True


class TestSanitizeEmailForLookup:
    """Test sanitize_email_for_lookup function."""

    def test_normalizes_email(self):
        """Test normalizes email address."""
        result = sanitize_email_for_lookup("  Test@Example.COM  ")
        assert result == "test@example.com"

    def test_lowercases_username(self):
        """Test lowercases username without @."""
        result = sanitize_email_for_lookup("JohnDoe123")
        assert result == "johndoe123"

    def test_strips_whitespace_from_username(self):
        """Test strips whitespace from username."""
        result = sanitize_email_for_lookup("  username  ")
        assert result == "username"

    def test_handles_email_normalization_failure(self):
        """Test handles email normalization failure gracefully."""
        # Email with @ but invalid format
        result = sanitize_email_for_lookup("@invalid")
        # Should return lowercased version as fallback
        assert result == "@invalid"

    def test_complex_email(self):
        """Test complex email with plus and dots."""
        result = sanitize_email_for_lookup("User..Name+Tag@EXAMPLE.COM")
        assert result == "user.name+tag@example.com"


class TestGetEmailValidationError:
    """Test get_email_validation_error function."""

    def test_valid_email_returns_none(self):
        """Test valid email returns None."""
        assert get_email_validation_error("user@example.com") is None

    def test_empty_string_returns_error(self):
        """Test empty string returns error message."""
        error = get_email_validation_error("")
        assert error is not None
        assert "requerido" in error.lower()

    def test_none_returns_error(self):
        """Test None returns error message."""
        error = get_email_validation_error(None)
        assert error is not None
        assert "requerido" in error.lower()

    def test_whitespace_only_returns_error(self):
        """Test whitespace-only returns error message."""
        error = get_email_validation_error("   ")
        assert error is not None
        assert "requerido" in error.lower()

    def test_missing_at_returns_error(self):
        """Test missing @ returns error message."""
        error = get_email_validation_error("invalidemail")
        assert error is not None
        assert "@" in error

    def test_multiple_at_returns_error(self):
        """Test multiple @ returns error message."""
        error = get_email_validation_error("user@middle@example.com")
        assert error is not None
        assert "un símbolo @" in error

    def test_empty_local_part_returns_error(self):
        """Test empty local part returns error message."""
        error = get_email_validation_error("@example.com")
        assert error is not None
        assert "antes del @" in error

    def test_empty_domain_returns_error(self):
        """Test empty domain returns error message."""
        error = get_email_validation_error("user@")
        assert error is not None
        assert "después del @" in error

    def test_domain_without_dot_returns_error(self):
        """Test domain without dot returns error message."""
        error = get_email_validation_error("user@example")
        assert error is not None
        assert "punto" in error.lower()

    def test_domain_starting_with_dot_returns_error(self):
        """Test domain starting with dot returns error message."""
        error = get_email_validation_error("user@.example.com")
        assert error is not None
        assert "punto" in error.lower()

    def test_domain_ending_with_dot_returns_error(self):
        """Test domain ending with dot returns error message."""
        error = get_email_validation_error("user@example.com.")
        assert error is not None
        assert "punto" in error.lower()

    def test_consecutive_dots_returns_error(self):
        """Test consecutive dots returns error message."""
        error = get_email_validation_error("user..name@example.com")
        assert error is not None
        assert "consecutivos" in error.lower()

    def test_invalid_characters_returns_error(self):
        """Test invalid characters returns error message."""
        error = get_email_validation_error("user<>@example.com")
        assert error is not None
        assert "caracteres" in error.lower()

    def test_valid_complex_email(self):
        """Test valid complex email returns None."""
        assert get_email_validation_error("user.name+tag@sub.example.com") is None
