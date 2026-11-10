"""
Conftest for unit tests - disable database fixtures.

Unit tests should not require database connections.
"""

import pytest


# Override the global initialize_database fixture to do nothing
@pytest.fixture(scope="session", autouse=True)
async def initialize_database():
    """
    Override global database fixture for unit tests.
    Unit tests should not require real database connections.
    """
    # Do nothing - unit tests don't need DB
    yield
