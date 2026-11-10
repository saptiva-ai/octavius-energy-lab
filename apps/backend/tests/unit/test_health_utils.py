"""
Unit tests for health check utility functions.
"""

import pytest

from src.utils.health import is_valid_status


class TestHealthUtils:
    """Test suite for health utility functions."""

    def test_ca_demo_01_function_returns_true_for_healthy(self):
        """CA-DEMO-01: Function returns True for 'healthy' status."""
        assert is_valid_status("healthy") is True

    def test_ca_demo_01_function_returns_true_for_degraded(self):
        """CA-DEMO-01: Function returns True for 'degraded' status."""
        assert is_valid_status("degraded") is True

    def test_ca_demo_01_function_returns_true_for_down(self):
        """CA-DEMO-01: Function returns True for 'down' status."""
        assert is_valid_status("down") is True

    def test_function_returns_false_for_invalid_status(self):
        """Function returns False for invalid status values."""
        assert is_valid_status("invalid") is False
        assert is_valid_status("unknown") is False
        assert is_valid_status("") is False

    def test_function_handles_case_sensitivity(self):
        """Function is case-sensitive and returns False for wrong case."""
        assert is_valid_status("HEALTHY") is False
        assert is_valid_status("Healthy") is False
        assert is_valid_status("DEGRADED") is False
        assert is_valid_status("DOWN") is False

    def test_function_returns_false_for_none(self):
        """Function returns False for None input."""
        assert is_valid_status(None) is False

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("healthy", True),
            ("degraded", True),
            ("down", True),
            ("invalid", False),
            ("", False),
            (None, False),
        ],
    )
    def test_valid_status_parametrized(self, status, expected):
        """Parametrized test for various status values."""
        assert is_valid_status(status) is expected
