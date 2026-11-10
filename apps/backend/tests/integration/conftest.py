"""
Pytest configuration for integration tests.

Provides fixtures for:
- AsyncClient with real app instance
- Test database setup/teardown
- Test user creation
- Authentication helpers
"""
import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Dict
from httpx import AsyncClient
from dotenv import load_dotenv

# Load environment variables for tests
# .env is located in project root envs/ directory
import pathlib
env_path = pathlib.Path(__file__).parent.parent.parent.parent.parent / "envs" / ".env"
load_dotenv(env_path)

# Check if running inside Docker container
def is_running_in_docker():
    """Check if code is running inside a Docker container."""
    return os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')

# Override connection URLs ONLY if running on host (not inside Docker)
# and the env var is not already set (CI provides its own REDIS_URL/MONGODB_URL).
# Docker maps: mongodb:27017 -> localhost:27018, redis:6379 -> localhost:6380
if not is_running_in_docker():
    # Running on host - use port-forwarded addresses (local dev compose)
    if "MONGODB_URL" not in os.environ:
        if "MONGODB_USER" in os.environ and "MONGODB_PASSWORD" in os.environ:
            mongo_user = os.environ["MONGODB_USER"]
            mongo_pass = os.environ["MONGODB_PASSWORD"]
            mongo_db = os.environ.get("MONGODB_DATABASE", "copilotos")
            os.environ["MONGODB_URL"] = f"mongodb://{mongo_user}:{mongo_pass}@localhost:27018/{mongo_db}?authSource=admin"

    # Set REDIS_URL with password, pointing to host-mapped port
    if "REDIS_URL" not in os.environ:
        redis_pass = os.environ.get("REDIS_PASSWORD", "")
        if redis_pass:
            os.environ["REDIS_URL"] = f"redis://:{redis_pass}@localhost:6380"
        else:
            os.environ["REDIS_URL"] = "redis://localhost:6380"
# If running inside Docker, use the environment variables as-is (mongodb:27017, redis:6379)

from src.main import app
from src.models.user import User
from src.core.database import Database


@pytest_asyncio.fixture(scope="function", autouse=True)
async def initialize_db():
    """Initialize database connection for each test.

    This fixture runs once per test to ensure Beanie is initialized in the same event loop.
    Changed from session to function scope to avoid event loop conflicts.
    """
    # Check if already initialized to avoid re-initialization
    try:
        await Database.connect_to_mongo()
    except Exception:
        pass  # Already connected

    yield

    # Don't close connection between tests to maintain session
    # Only close at the very end


@pytest_asyncio.fixture
async def clean_db():
    """Clean database and Redis before each test.

    Note: TestClient will initialize Beanie automatically via lifespan.
    """
    from src.models.user import User
    from src.services.cache_service import get_redis_client

    # Clean all User documents before test
    await User.delete_all()

    # Clean Redis blacklist keys
    try:
        redis_client = await get_redis_client()
        if redis_client:
            # Delete all blacklist keys (pattern: blacklist:*)
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match="blacklist:*", count=100)
                if keys:
                    await redis_client.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        # Redis cleanup is optional - tests can still run without it
        pass

    yield

    # Cleanup after test
    await User.delete_all()

    # Clean Redis again after test
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


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client for integration tests.

    Uses httpx.AsyncClient with ASGITransport to test FastAPI app.
    """
    import httpx
    async with AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(clean_db) -> Dict[str, str]:
    """
    Create a test user and return credentials.

    Returns:
        dict with 'email', 'password', 'user_id', 'username'
    """
    from src.services.auth_service import register_user
    from src.schemas.user import UserCreate

    username = "Test User"
    email = "test@example.com"
    password = "TestPass123"

    # Register user - register_user returns AuthResponse with user field
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
    """
    AsyncClient with authentication headers set.

    Returns:
        tuple of (client, auth_data) where auth_data contains access_token, user_id, etc.
    """
    # Login to get token
    response = await client.post(
        "/api/auth/login",
        json={
            "identifier": test_user["email"],  # Use identifier (email or username)
            "password": test_user["password"]
        }
    )

    assert response.status_code == 200, f"Login failed: {response.json()}"
    auth_data = response.json()

    # Set authorization header
    client.headers.update({
        "Authorization": f"Bearer {auth_data['access_token']}"
    })

    return client, {
        **auth_data,
        **test_user
    }


@pytest.fixture
def mock_saptiva_response():
    """Mock response from SAPTIVA API for testing."""
    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "saptiva-turbo",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from SAPTIVA."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18
        }
    }
