import os
import pytest
from unittest.mock import MagicMock, patch

# Check if tidewave is available
try:
    import tidewave
    TIDEWAVE_AVAILABLE = True
except ImportError:
    TIDEWAVE_AVAILABLE = False


@pytest.mark.skipif(not TIDEWAVE_AVAILABLE, reason="tidewave module not installed")
class TestTidewaveConfig:
    """Test suite for Tidewave configuration logic."""

    @patch.dict(os.environ, {"TIDEWAVE_ENABLED": "true"})
    @patch("tidewave.fastapi.Tidewave")
    def test_tidewave_initialization_with_remote_access(self, mock_tidewave_class):
        """
        TC-U1: Verify Tidewave is initialized with allow_remote_access=True
        when TIDEWAVE_ENABLED is set.
        """
        from src.main import create_app

        # Setup mock instance
        mock_instance = MagicMock()
        mock_tidewave_class.return_value = mock_instance

        # Act
        create_app()

        # Assert
        # Verify constructor was called with config dict
        mock_tidewave_class.assert_called_once()
        call_args = mock_tidewave_class.call_args

        assert "config" in call_args.kwargs
        assert call_args.kwargs["config"].get("allow_remote_access") is True

        # Verify install was called
        mock_instance.install.assert_called_once()

    @patch.dict(os.environ, {"TIDEWAVE_ENABLED": "false"})
    @patch("tidewave.fastapi.Tidewave")
    def test_tidewave_disabled(self, mock_tidewave_class):
        """TC-U2: Verify Tidewave is NOT initialized when disabled."""
        from src.main import create_app

        create_app()
        # Should not even be imported/called
        mock_tidewave_class.assert_not_called()
