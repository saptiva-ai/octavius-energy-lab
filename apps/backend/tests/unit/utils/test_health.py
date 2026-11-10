"""
Unit tests for utils/health module.

Tests:
- is_valid_status function
- VALID_STATUSES constant
"""

import pytest

from src.utils.health import VALID_STATUSES, is_valid_status

pytestmark = [pytest.mark.unit]


class TestValidStatuses:
    """Test VALID_STATUSES constant."""

    def test_contains_healthy(self):
        """Test VALID_STATUSES contains 'healthy'."""
        assert "healthy" in VALID_STATUSES

    def test_contains_degraded(self):
        """Test VALID_STATUSES contains 'degraded'."""
        assert "degraded" in VALID_STATUSES

    def test_contains_down(self):
        """Test VALID_STATUSES contains 'down'."""
        assert "down" in VALID_STATUSES

    def test_only_three_statuses(self):
        """Test VALID_STATUSES contains exactly 3 statuses."""
        assert len(VALID_STATUSES) == 3


class TestIsValidStatus:
    """Test is_valid_status function."""

    def test_healthy_is_valid(self):
        """Test 'healthy' is a valid status."""
        assert is_valid_status("healthy") is True

    def test_degraded_is_valid(self):
        """Test 'degraded' is a valid status."""
        assert is_valid_status("degraded") is True

    def test_down_is_valid(self):
        """Test 'down' is a valid status."""
        assert is_valid_status("down") is True

    def test_none_is_invalid(self):
        """Test None is an invalid status."""
        assert is_valid_status(None) is False

    def test_empty_string_is_invalid(self):
        """Test empty string is an invalid status."""
        assert is_valid_status("") is False

    def test_invalid_string_is_invalid(self):
        """Test arbitrary string is an invalid status."""
        assert is_valid_status("invalid") is False

    def test_case_sensitive_upper(self):
        """Test status check is case sensitive (HEALTHY)."""
        assert is_valid_status("HEALTHY") is False

    def test_case_sensitive_mixed(self):
        """Test status check is case sensitive (Degraded)."""
        assert is_valid_status("Degraded") is False

    def test_whitespace_is_invalid(self):
        """Test whitespace string is invalid."""
        assert is_valid_status(" ") is False

    def test_similar_word_is_invalid(self):
        """Test similar but incorrect word is invalid."""
        assert is_valid_status("unhealthy") is False
        assert is_valid_status("up") is False

    @pytest.mark.parametrize("status", list(VALID_STATUSES))
    def test_all_valid_statuses(self, status):
        """Test all valid statuses are accepted."""
        assert is_valid_status(status) is True
