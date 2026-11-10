"""
Unit tests for settings router.

Tests:
- get_saptiva_key endpoint
- set_saptiva_key endpoint
- delete_saptiva_key endpoint
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.routers.settings import delete_saptiva_key, get_saptiva_key, set_saptiva_key
from src.schemas.settings import (
    SaptivaKeyDeleteResponse,
    SaptivaKeyStatus,
    SaptivaKeyUpdateRequest,
    SaptivaKeyUpdateResponse,
)

pytestmark = [pytest.mark.unit]


class TestGetSaptivaKey:
    """Test get_saptiva_key endpoint."""

    @pytest.mark.asyncio
    async def test_returns_status(self):
        """Test returns SaptivaKeyStatus."""
        with patch("src.routers.settings.get_saptiva_key_status") as mock_get:
            mock_get.return_value = {
                "configured": True,
                "mode": "live",
                "source": "database",
                "hint": "sk-...abc",
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            result = await get_saptiva_key()

            assert isinstance(result, SaptivaKeyStatus)
            assert result.configured is True
            assert result.mode == "live"
            assert result.source == "database"

    @pytest.mark.asyncio
    async def test_returns_demo_mode(self):
        """Test returns demo mode when not configured."""
        with patch("src.routers.settings.get_saptiva_key_status") as mock_get:
            mock_get.return_value = {
                "configured": False,
                "mode": "demo",
                "source": "unset",
                "hint": None,
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            result = await get_saptiva_key()

            assert result.configured is False
            assert result.mode == "demo"


class TestSetSaptivaKey:
    """Test set_saptiva_key endpoint."""

    @pytest.mark.asyncio
    async def test_sets_key_successfully(self):
        """Test setting key successfully."""
        with patch("src.routers.settings.validate_saptiva_api_key") as mock_validate, \
             patch("src.routers.settings.update_saptiva_api_key") as mock_update, \
             patch("src.routers.settings.get_saptiva_key_status") as mock_get:

            mock_validate.return_value = (True, "Key is valid")
            mock_update.return_value = None
            mock_get.return_value = {
                "configured": True,
                "mode": "live",
                "source": "database",
                "hint": "sk-...xyz",
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            request = MagicMock()
            request.state.user_id = "user_123"
            payload = SaptivaKeyUpdateRequest(
                api_key="sk-test-key-12345",
                validate_key=True,
            )

            result = await set_saptiva_key(payload=payload, request=request)

            assert isinstance(result, SaptivaKeyUpdateResponse)
            assert result.configured is True
            mock_validate.assert_called_once()
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_empty_key(self):
        """Test rejects empty API key after stripping."""
        request = MagicMock()
        request.state.user_id = "user_123"
        payload = SaptivaKeyUpdateRequest(
            api_key="            ",  # Whitespace only
            validate_key=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            await set_saptiva_key(payload=payload, request=request)

        assert exc_info.value.status_code == 400
        assert "vacía" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_invalid_key(self):
        """Test rejects invalid API key after validation."""
        with patch("src.routers.settings.validate_saptiva_api_key") as mock_validate:
            mock_validate.return_value = (False, "Invalid API key")

            request = MagicMock()
            request.state.user_id = "user_123"
            payload = SaptivaKeyUpdateRequest(
                api_key="YOUR_INVALID_KEY_HERE",
                validate_key=True,
            )

            with pytest.raises(HTTPException) as exc_info:
                await set_saptiva_key(payload=payload, request=request)

            assert exc_info.value.status_code == 400
            assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_skips_validation_when_disabled(self):
        """Test skips validation when validate_key is False."""
        with patch("src.routers.settings.validate_saptiva_api_key") as mock_validate, \
             patch("src.routers.settings.update_saptiva_api_key") as mock_update, \
             patch("src.routers.settings.get_saptiva_key_status") as mock_get:

            mock_update.return_value = None
            mock_get.return_value = {
                "configured": True,
                "mode": "live",
                "source": "database",
                "hint": "sk-...xyz",
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            request = MagicMock()
            request.state.user_id = "user_123"
            payload = SaptivaKeyUpdateRequest(
                api_key="sk-test-key-12345",
                validate_key=False,
            )

            result = await set_saptiva_key(payload=payload, request=request)

            mock_validate.assert_not_called()
            assert isinstance(result, SaptivaKeyUpdateResponse)

    @pytest.mark.asyncio
    async def test_passes_user_id_to_update(self):
        """Test passes user_id to update function."""
        with patch("src.routers.settings.validate_saptiva_api_key") as mock_validate, \
             patch("src.routers.settings.update_saptiva_api_key") as mock_update, \
             patch("src.routers.settings.get_saptiva_key_status") as mock_get:

            mock_validate.return_value = (True, "Valid")
            mock_update.return_value = None
            mock_get.return_value = {
                "configured": True,
                "mode": "live",
                "source": "database",
                "hint": None,
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            request = MagicMock()
            request.state.user_id = "user_456"
            payload = SaptivaKeyUpdateRequest(
                api_key="sk-test-key-12345",
                validate_key=True,
            )

            await set_saptiva_key(payload=payload, request=request)

            mock_update.assert_called_once_with(
                "sk-test-key-12345",
                "user_456",
                "Valid",
            )

    @pytest.mark.asyncio
    async def test_handles_missing_user_id(self):
        """Test handles missing user_id gracefully."""
        with patch("src.routers.settings.validate_saptiva_api_key") as mock_validate, \
             patch("src.routers.settings.update_saptiva_api_key") as mock_update, \
             patch("src.routers.settings.get_saptiva_key_status") as mock_get:

            mock_validate.return_value = (True, "Valid")
            mock_update.return_value = None
            mock_get.return_value = {
                "configured": True,
                "mode": "live",
                "source": "database",
                "hint": None,
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            # Mock request with state but no user_id attribute on state
            request = MagicMock()
            request.state = MagicMock(spec=[])  # State object without user_id

            payload = SaptivaKeyUpdateRequest(
                api_key="sk-test-key-12345",
                validate_key=True,
            )

            await set_saptiva_key(payload=payload, request=request)

            # user_id should be None when not present
            mock_update.assert_called_once_with(
                "sk-test-key-12345",
                None,
                "Valid",
            )


class TestDeleteSaptivaKey:
    """Test delete_saptiva_key endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_key_successfully(self):
        """Test deleting key successfully."""
        with patch("src.routers.settings.clear_saptiva_api_key") as mock_clear, \
             patch("src.routers.settings.get_saptiva_key_status") as mock_get:

            mock_clear.return_value = None
            mock_get.return_value = {
                "configured": False,
                "mode": "demo",
                "source": "unset",
                "hint": None,
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            request = MagicMock()
            request.state.user_id = "user_123"

            result = await delete_saptiva_key(request=request)

            assert isinstance(result, SaptivaKeyDeleteResponse)
            assert result.configured is False
            assert result.mode == "demo"
            mock_clear.assert_called_once_with("user_123")

    @pytest.mark.asyncio
    async def test_handles_missing_user_id(self):
        """Test handles missing user_id gracefully."""
        with patch("src.routers.settings.clear_saptiva_api_key") as mock_clear, \
             patch("src.routers.settings.get_saptiva_key_status") as mock_get:

            mock_clear.return_value = None
            mock_get.return_value = {
                "configured": False,
                "mode": "demo",
                "source": "unset",
                "hint": None,
                "status_message": None,
                "last_validated_at": None,
                "updated_at": None,
                "updated_by": None,
            }

            # Mock request with state but no user_id attribute on state
            request = MagicMock()
            request.state = MagicMock(spec=[])  # State object without user_id

            await delete_saptiva_key(request=request)

            mock_clear.assert_called_once_with(None)
