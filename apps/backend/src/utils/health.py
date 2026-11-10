"""
Health check utility functions.

This module provides utilities for validating health status values.
"""

from typing import Optional

VALID_STATUSES = {"healthy", "degraded", "down"}


def is_valid_status(status: Optional[str]) -> bool:
    """
    Check if a string is a valid health status.

    Valid statuses are: "healthy", "degraded", "down" (case-sensitive).

    Args:
        status: The status string to validate. Can be None.

    Returns:
        bool: True if the status is valid, False otherwise.

    Examples:
        >>> is_valid_status("healthy")
        True
        >>> is_valid_status("degraded")
        True
        >>> is_valid_status("down")
        True
        >>> is_valid_status("invalid")
        False
        >>> is_valid_status(None)
        False
    """
    if status is None:
        return False
    return status in VALID_STATUSES
