"""
Pytest configuration for regression tests.

Provides fixtures for full-stack testing with real services.
Regression tests require MongoDB and Redis to be running.

Tests are split into:
- Unit regression tests: No external dependencies, always run
- Integration regression tests: Require MongoDB/Redis, skip if unavailable
"""
import os

# Set TEST_MODE early to prevent MinIO connection attempts during import
# This must happen BEFORE any src imports that trigger minio_service singleton
os.environ.setdefault("TEST_MODE", "true")

import pytest
import pytest_asyncio
from typing import AsyncGenerator, Dict
from httpx import AsyncClient
from dotenv import load_dotenv
import pathlib

# Load environment variables
env_path = pathlib.Path(__file__).parent.parent.parent.parent.parent / "envs" / ".env"
load_dotenv(env_path)

# Check if services are available
def _check_mongodb_available() -> bool:
    """Check if MongoDB is reachable on common ports."""
    import socket
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

# Marker for tests that require database
requires_db = pytest.mark.skipif(
    not MONGODB_AVAILABLE,
    reason="MongoDB not available (run with docker-compose up)"
)


def is_running_in_docker():
    """Check if code is running inside a Docker container."""
    return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')


def is_ci_environment():
    """Check if running in CI environment (GitHub Actions, etc.)."""
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


# Override connection URLs if running on host (not inside Docker or CI)
# CI already has correct URLs set via workflow environment variables
if not is_running_in_docker() and not is_ci_environment():
    if "MONGODB_USER" in os.environ and "MONGODB_PASSWORD" in os.environ:
        mongo_user = os.environ["MONGODB_USER"]
        mongo_pass = os.environ["MONGODB_PASSWORD"]
        mongo_db = os.environ.get("MONGODB_DATABASE", "copilotos")
        os.environ["MONGODB_URL"] = f"mongodb://{mongo_user}:{mongo_pass}@localhost:27018/{mongo_db}?authSource=admin"

    redis_pass = os.environ.get("REDIS_PASSWORD", "")
    if redis_pass:
        os.environ["REDIS_URL"] = f"redis://:{redis_pass}@localhost:6380"
    else:
        os.environ["REDIS_URL"] = "redis://localhost:6380"


def pytest_configure(config):
    """Register custom markers for regression tests."""
    config.addinivalue_line(
        "markers", "regression: Critical path tests that must pass before deploy"
    )


@pytest_asyncio.fixture(scope="function")
async def initialize_db():
    """Initialize database connection for each test."""
    from src.core.database import Database
    try:
        await Database.connect_to_mongo()
    except Exception:
        pass  # Already connected
    yield


@pytest_asyncio.fixture
async def clean_db(initialize_db):
    """Clean database and Redis before each test."""
    from src.models.user import User
    from src.services.cache_service import get_redis_client

    # Clean all User documents before test
    await User.delete_all()

    # Clean Redis blacklist keys
    try:
        redis_client = await get_redis_client()
        if redis_client:
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match="blacklist:*", count=100)
                if keys:
                    await redis_client.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        pass

    yield

    # Cleanup after test
    await User.delete_all()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for regression tests (no DB required)."""
    from src.main import app
    import httpx

    async with AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_client(initialize_db) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for tests that require database."""
    from src.main import app
    import httpx

    async with AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(clean_db) -> Dict[str, str]:
    """Create a test user and return credentials."""
    from src.services.auth_service import register_user
    from src.schemas.user import UserCreate

    username = "Regression Test User"
    email = "regression-test@example.com"
    password = "TestPass123!"

    auth_response = await register_user(
        UserCreate(
            username=username,
            email=email,
            password=password
        )
    )

    return {
        "username": username,
        "email": email,
        "password": password,
        "user_id": auth_response.user.id
    }


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, test_user: Dict[str, str]) -> tuple[AsyncClient, Dict]:
    """AsyncClient with authentication headers set."""
    response = await client.post(
        "/api/auth/login",
        json={
            "identifier": test_user["email"],
            "password": test_user["password"]
        }
    )

    assert response.status_code == 200, f"Login failed: {response.json()}"
    auth_data = response.json()

    client.headers.update({
        "Authorization": f"Bearer {auth_data['access_token']}"
    })

    return client, {
        **auth_data,
        **test_user
    }
