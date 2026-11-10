"""
Unit tests for Stateless Password Reset flow (JWT).
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import jwt
from fastapi import FastAPI, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from beanie import init_beanie
import mongomock_motor

from src.models.user import User
from src.core.security import create_password_reset_token, RESET_TOKEN_TYPE
from src.core.config import get_settings
from src.core.exceptions import APIError
from src.routers.auth import router as auth_router
from fastapi import HTTPException

# Mock settings used in auth logic
settings = get_settings()

@pytest_asyncio.fixture(scope="function")
async def init_test_db():
    """Initialize Beanie with mongomock for testing."""
    client = mongomock_motor.AsyncMongoMockClient()
    await init_beanie(
        database=client.test_db,
        document_models=[User]
    )
    yield
    # Cleanup (mongomock client.close() is not async)
    client.close()

@pytest.fixture
def app():
    """Create a minimal FastAPI app for testing without middleware."""
    test_app = FastAPI()

    # Register exception handlers
    @test_app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    @test_app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )

    test_app.include_router(auth_router)
    return test_app

@pytest.fixture
def client(app):
    """FastAPI test client."""
    return TestClient(app)

@pytest.fixture
def mock_email_service():
    with patch("src.services.email_service.get_email_service") as mock_get:
        service_instance = Mock()
        service_instance.send_password_reset_email = AsyncMock(return_value=True)
        mock_get.return_value = service_instance
        yield service_instance

@pytest.fixture
def mock_user():
    user = Mock(spec=User)
    user.id = "user123"
    user.email = "test@example.com"
    user.username = "testuser"
    user.password_hash = "oldhash"
    # Mock save method
    user.save = AsyncMock()
    return user

@pytest.mark.asyncio
async def test_forgot_password_success(init_test_db, client, mock_user, mock_email_service):
    """
    Test requesting a password reset for an existing user.
    Should send an email and return 200.
    """
    with patch("src.models.user.User.find_one", new=AsyncMock(return_value=mock_user)):
        response = client.post(
            "/auth/forgot-password",
            json={"email": "test@example.com"}
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "recibirás un enlace" in data["message"]
    
    # Verify email service was called
    # Note: BackgroundTasks run after the response in real app, 
    # but TestClient usually executes them synchronously or we can mock BackgroundTasks.
    # In unit tests with mocks, we check if the task was added or the service called.
    # Since we are mocking the router logic execution flow, verify the call.
    # However, BackgroundTasks might need explicit execution in tests if not using TestClient context manager properly,
    # OR we rely on the fact that we patched the service.
    
    # Wait a tiny bit for background tasks if async
    mock_email_service.send_password_reset_email.assert_called_once()
    call_args = mock_email_service.send_password_reset_email.call_args
    assert call_args[1]["to_email"] == "test@example.com"
    assert "reset-password?token=" in call_args[1]["reset_link"]

@pytest.mark.asyncio
async def test_forgot_password_user_not_found(init_test_db, client, mock_email_service):
    """
    Test requesting password reset for non-existent user.
    Should return 200 (security) but NOT send email.
    """
    with patch("src.models.user.User.find_one", new=AsyncMock(return_value=None)):
        response = client.post(
            "/auth/forgot-password",
            json={"email": "unknown@example.com"}
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "recibirás un enlace" in data["message"]
    
    # Email should NOT be sent
    mock_email_service.send_password_reset_email.assert_not_called()

@pytest.mark.asyncio
async def test_reset_password_success(init_test_db, client, mock_user):
    """
    Test resetting password with a valid token.
    """
    # Generate valid token
    token = create_password_reset_token(mock_user.email)

    # Mock finding user by email (extracted from token)
    with patch("src.models.user.User.find_one", new=AsyncMock(return_value=mock_user)):
        response = client.post(
            "/auth/reset-password",
            json={
                "token": token,
                "new_password": "NewSecurePassword123!"
            }
        )

    assert response.status_code == status.HTTP_200_OK
    assert "actualizada exitosamente" in response.json()["message"]

    # Verify password was hashed and saved
    assert mock_user.save.called
    assert mock_user.password_hash != "oldhash"
    # We assume argon2 hashing happened, tough to check exact value without passlib dependency in test

@pytest.mark.asyncio
async def test_reset_password_invalid_token(client):
    """
    Test reset with garbage token.
    """
    response = client.post(
        "/auth/reset-password",
        json={
            "token": "invalid.token.structure",
            "new_password": "NewPassword123"
        }
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "inválido" in response.json()["detail"]

@pytest.mark.asyncio
async def test_reset_password_expired_token(client):
    """
    Test reset with an expired token.
    """
    # Manually create expired token
    expire = datetime.utcnow() - timedelta(minutes=1)
    to_encode = {
        "exp": expire,
        "sub": "test@example.com",
        "type": RESET_TOKEN_TYPE
    }
    expired_token = jwt.encode(
        to_encode, 
        settings.secret_key, 
        algorithm=settings.jwt_algorithm
    )
    
    response = client.post(
        "/auth/reset-password",
        json={
            "token": expired_token,
            "new_password": "NewPassword123"
        }
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "expirado" in response.json()["detail"]

@pytest.mark.asyncio
async def test_reset_password_wrong_token_type(client):
    """
    Test reset with a valid JWT but wrong 'type' (e.g. access token).
    """
    to_encode = {
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "sub": "test@example.com",
        "type": "access" # Wrong type
    }
    wrong_type_token = jwt.encode(
        to_encode, 
        settings.secret_key, 
        algorithm=settings.jwt_algorithm
    )
    
    response = client.post(
        "/auth/reset-password",
        json={
            "token": wrong_type_token,
            "new_password": "NewPassword123"
        }
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "inválido" in response.json()["detail"]
