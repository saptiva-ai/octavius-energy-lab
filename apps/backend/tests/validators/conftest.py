"""
Conftest for validators tests - no database required.
"""
import pytest

# Override parent conftest fixtures to prevent DB connection
@pytest.fixture(scope="session", autouse=True)
def initialize_database():
    """Override to skip database initialization for validator tests."""
    yield
    pass
