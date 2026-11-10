"""
Unit tests for schemas/settings module.

Tests:
- SaptivaKeyStatus model
- SaptivaKeyUpdateRequest model
- SaptivaKeyUpdateResponse model
- SaptivaKeyDeleteResponse model
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.schemas.settings import (
    SaptivaKeyDeleteResponse,
    SaptivaKeyStatus,
    SaptivaKeyUpdateRequest,
    SaptivaKeyUpdateResponse,
)

pytestmark = [pytest.mark.unit]


class TestSaptivaKeyStatus:
    """Test SaptivaKeyStatus model."""

    def test_create_minimal(self):
        """Test creating with required fields only."""
        status = SaptivaKeyStatus(
            configured=True,
            mode="live",
            source="environment",
        )

        assert status.configured is True
        assert status.mode == "live"
        assert status.source == "environment"
        assert status.hint is None
        assert status.status_message is None

    def test_create_full(self):
        """Test creating with all fields."""
        now = datetime.utcnow()
        status = SaptivaKeyStatus(
            configured=True,
            mode="live",
            source="database",
            hint="sk-...abc",
            status_message="Key is valid",
            last_validated_at=now,
            updated_at=now,
            updated_by="user_123",
        )

        assert status.configured is True
        assert status.mode == "live"
        assert status.source == "database"
        assert status.hint == "sk-...abc"
        assert status.status_message == "Key is valid"
        assert status.last_validated_at == now
        assert status.updated_at == now
        assert status.updated_by == "user_123"

    def test_demo_mode(self):
        """Test demo mode."""
        status = SaptivaKeyStatus(
            configured=False,
            mode="demo",
            source="unset",
        )

        assert status.mode == "demo"
        assert status.configured is False

    @pytest.mark.parametrize("mode", ["demo", "live"])
    def test_valid_modes(self, mode):
        """Test all valid modes are accepted."""
        status = SaptivaKeyStatus(
            configured=True,
            mode=mode,
            source="environment",
        )
        assert status.mode == mode

    @pytest.mark.parametrize("source", ["unset", "environment", "database"])
    def test_valid_sources(self, source):
        """Test all valid sources are accepted."""
        status = SaptivaKeyStatus(
            configured=True,
            mode="live",
            source=source,
        )
        assert status.source == source

    def test_invalid_mode_rejected(self):
        """Test invalid mode is rejected."""
        with pytest.raises(ValidationError):
            SaptivaKeyStatus(
                configured=True,
                mode="invalid",
                source="environment",
            )

    def test_invalid_source_rejected(self):
        """Test invalid source is rejected."""
        with pytest.raises(ValidationError):
            SaptivaKeyStatus(
                configured=True,
                mode="live",
                source="invalid",
            )


class TestSaptivaKeyUpdateRequest:
    """Test SaptivaKeyUpdateRequest model."""

    def test_create_minimal(self):
        """Test creating with required fields only."""
        request = SaptivaKeyUpdateRequest(api_key="sk-test-key-12345")

        assert request.api_key == "sk-test-key-12345"
        assert request.validate_key is True  # Default

    def test_create_with_validation_disabled(self):
        """Test creating with validation disabled."""
        request = SaptivaKeyUpdateRequest(
            api_key="sk-test-key-12345",
            validate_key=False,
        )

        assert request.validate_key is False

    def test_api_key_min_length(self):
        """Test API key minimum length (12 chars)."""
        with pytest.raises(ValidationError) as exc_info:
            SaptivaKeyUpdateRequest(api_key="short")

        assert "min_length" in str(exc_info.value) or "at least 12" in str(
            exc_info.value
        )

    def test_api_key_max_length(self):
        """Test API key maximum length (256 chars)."""
        with pytest.raises(ValidationError) as exc_info:
            SaptivaKeyUpdateRequest(api_key="x" * 257)

        assert "max_length" in str(exc_info.value) or "at most 256" in str(
            exc_info.value
        )

    def test_api_key_exact_min_length(self):
        """Test API key at exact min length is valid."""
        request = SaptivaKeyUpdateRequest(api_key="x" * 12)
        assert len(request.api_key) == 12

    def test_api_key_exact_max_length(self):
        """Test API key at exact max length is valid."""
        request = SaptivaKeyUpdateRequest(api_key="x" * 256)
        assert len(request.api_key) == 256


class TestSaptivaKeyUpdateResponse:
    """Test SaptivaKeyUpdateResponse model."""

    def test_inherits_from_status(self):
        """Test SaptivaKeyUpdateResponse inherits from SaptivaKeyStatus."""
        assert issubclass(SaptivaKeyUpdateResponse, SaptivaKeyStatus)

    def test_create_response(self):
        """Test creating update response."""
        response = SaptivaKeyUpdateResponse(
            configured=True,
            mode="live",
            source="database",
        )

        assert response.configured is True
        assert response.mode == "live"


class TestSaptivaKeyDeleteResponse:
    """Test SaptivaKeyDeleteResponse model."""

    def test_inherits_from_status(self):
        """Test SaptivaKeyDeleteResponse inherits from SaptivaKeyStatus."""
        assert issubclass(SaptivaKeyDeleteResponse, SaptivaKeyStatus)

    def test_create_response(self):
        """Test creating delete response."""
        response = SaptivaKeyDeleteResponse(
            configured=False,
            mode="demo",
            source="unset",
        )

        assert response.configured is False
        assert response.mode == "demo"
        assert response.source == "unset"
