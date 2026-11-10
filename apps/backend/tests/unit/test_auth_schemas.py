"""
Unit tests for auth schemas.

Tests Pydantic models for authentication.
"""
import pytest
from datetime import datetime
from uuid import uuid4
from pydantic import ValidationError

from src.schemas.auth import (
    AuthRequest,
    TokenRefresh,
    AuthResponse,
    TokenVerify,
    RefreshResponse
)
from src.schemas.user import User


@pytest.mark.unit
class TestAuthSchemas:
    """Test authentication schema models"""

    def test_auth_request_valid(self):
        """Test AuthRequest with valid data"""
        auth = AuthRequest(
            identifier="testuser",
            password="TestPass123"
        )

        assert auth.identifier == "testuser"
        assert auth.password == "TestPass123"

    def test_auth_request_validation_short_identifier(self):
        """Test AuthRequest rejects empty identifier"""
        with pytest.raises(ValidationError):
            AuthRequest(identifier="", password="password123")

    def test_auth_request_validation_short_password(self):
        """Test AuthRequest requires min 8 char password"""
        with pytest.raises(ValidationError):
            AuthRequest(identifier="user", password="short")

    def test_auth_request_validation_long_identifier(self):
        """Test AuthRequest rejects too long identifier"""
        with pytest.raises(ValidationError):
            AuthRequest(identifier="a" * 256, password="password123")

    def test_token_refresh_valid(self):
        """Test TokenRefresh with valid token"""
        refresh = TokenRefresh(
            refresh_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        )

        assert refresh.refresh_token.startswith("eyJ")

    def test_token_refresh_validation(self):
        """Test TokenRefresh requires token"""
        with pytest.raises(ValidationError):
            TokenRefresh()

    def test_auth_response_creation(self):
        """Test AuthResponse model"""
        user = User(
            id=str(uuid4()),  # User schema expects string id
            username="testuser",
            email="test@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),  # Required field
            is_active=True
        )

        response = AuthResponse(
            access_token="access_token_here",
            refresh_token="refresh_token_here",
            token_type="bearer",
            expires_in=3600,
            user=user
        )

        assert response.access_token == "access_token_here"
        assert response.refresh_token == "refresh_token_here"
        assert response.token_type == "bearer"
        assert response.expires_in == 3600
        assert response.user.username == "testuser"

    def test_token_verify_valid(self):
        """Test TokenVerify for valid token"""
        user_id = uuid4()
        verify = TokenVerify(
            valid=True,
            user_id=user_id,
            expires_at=datetime.utcnow()
        )

        assert verify.valid is True
        assert verify.user_id == user_id
        assert verify.expires_at is not None

    def test_token_verify_invalid(self):
        """Test TokenVerify for invalid token"""
        verify = TokenVerify(
            valid=False
        )

        assert verify.valid is False
        assert verify.user_id is None
        assert verify.expires_at is None

    def test_refresh_response_creation(self):
        """Test RefreshResponse model"""
        response = RefreshResponse(
            access_token="new_access_token",
            token_type="bearer",
            expires_in=3600
        )

        assert response.access_token == "new_access_token"
        assert response.token_type == "bearer"
        assert response.expires_in == 3600

    def test_refresh_response_default_token_type(self):
        """Test RefreshResponse has default token_type"""
        response = RefreshResponse(
            access_token="token",
            expires_in=3600
        )

        assert response.token_type == "bearer"

    def test_auth_response_json_serialization(self):
        """Test AuthResponse can be serialized"""
        user = User(
            id=str(uuid4()),  # User schema expects string id
            username="user",
            email="user@example.com",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),  # Required field
            is_active=True
        )

        response = AuthResponse(
            access_token="token",
            refresh_token="refresh",
            expires_in=3600,
            user=user
        )

        json_data = response.model_dump()
        assert json_data["access_token"] == "token"
        assert "user" in json_data
        assert isinstance(json_data, dict)

    def test_auth_request_field_constraints(self):
        """Test AuthRequest field constraints"""
        # Min password length is 8
        with pytest.raises(ValidationError):
            AuthRequest(identifier="user", password="1234567")

        # Valid 8-char password should work
        auth = AuthRequest(identifier="user", password="12345678")
        assert auth.password == "12345678"

    def test_token_verify_partial_data(self):
        """Test TokenVerify with partial data"""
        verify = TokenVerify(valid=True, user_id=uuid4())
        assert verify.valid is True
        assert verify.user_id is not None
        assert verify.expires_at is None
