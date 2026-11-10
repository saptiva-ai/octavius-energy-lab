"""
Unit tests for email_service module.

Tests:
- EmailService class initialization
- send_email method
- send_password_reset_email method
- get_email_service singleton
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _create_mock_settings(
    smtp_user: str = "user@example.com",
    smtp_secret: str = "test_secret_123",
):
    """Create mock settings for testing."""
    mock = MagicMock()
    mock.smtp_user = smtp_user
    mock.smtp_password = smtp_secret  # Maps to settings attribute
    mock.smtp_from_email = "noreply@example.com"
    mock.smtp_port = 587
    mock.smtp_host = "smtp.gmail.com"
    mock.mail_from_name = "Test App"
    return mock


class TestEmailServiceInit:
    """Test EmailService initialization."""

    def test_init_with_credentials(self):
        """Test initialization with SMTP credentials."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch("src.services.email_service.ConnectionConfig"):
            from src.services.email_service import EmailService

            service = EmailService()

            assert service.settings == mock_settings
            assert service.conf is not None

    def test_init_without_credentials_logs_warning(self):
        """Test initialization without SMTP credentials logs warning."""
        mock_settings = _create_mock_settings(
            smtp_user="",
            smtp_secret="",
        )

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.logger"
        ) as mock_logger:
            from src.services.email_service import EmailService

            EmailService()

            mock_logger.warning.assert_called_once()


class TestSendEmail:
    """Test send_email method."""

    @pytest.mark.asyncio
    async def test_send_email_success(self):
        """Test sending email successfully."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.MessageSchema"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            result = await service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test body</p>",
            )

            assert result is True
            mock_fm.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_with_reply_to(self):
        """Test sending email with reply-to addresses."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class, patch(
            "src.services.email_service.MessageSchema"
        ) as mock_message_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            await service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test body</p>",
                reply_to=["support@example.com"],
            )

            # Verify MessageSchema was called with reply_to
            call_kwargs = mock_message_class.call_args.kwargs
            assert call_kwargs["reply_to"] == ["support@example.com"]

    @pytest.mark.asyncio
    async def test_send_email_failure_returns_false(self):
        """Test send_email returns False on failure."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.MessageSchema"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock(side_effect=Exception("SMTP error"))
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            result = await service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test body</p>",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_logs_error_on_failure(self):
        """Test send_email logs error on failure."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.MessageSchema"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class, patch(
            "src.services.email_service.logger"
        ) as mock_logger:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock(side_effect=Exception("SMTP error"))
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            await service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Test body</p>",
            )

            mock_logger.error.assert_called_once()


class TestSendPasswordResetEmail:
    """Test send_password_reset_email method."""

    @pytest.mark.asyncio
    async def test_send_password_reset_email_success(self):
        """Test sending password reset email successfully."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            result = await service.send_password_reset_email(
                to_email="user@example.com",
                username="John Doe",
                reset_link="https://example.com/reset?token=abc123",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_password_reset_email_contains_username(self):
        """Test password reset email contains username."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class, patch(
            "src.services.email_service.MessageSchema"
        ) as mock_message_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            await service.send_password_reset_email(
                to_email="user@example.com",
                username="John Doe",
                reset_link="https://example.com/reset?token=abc123",
            )

            # Check body contains username
            call_kwargs = mock_message_class.call_args.kwargs
            assert "John Doe" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_send_password_reset_email_contains_reset_link(self):
        """Test password reset email contains reset link."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class, patch(
            "src.services.email_service.MessageSchema"
        ) as mock_message_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            await service.send_password_reset_email(
                to_email="user@example.com",
                username="John Doe",
                reset_link="https://example.com/reset?token=abc123",
            )

            # Check body contains reset link
            call_kwargs = mock_message_class.call_args.kwargs
            assert "https://example.com/reset?token=abc123" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_send_password_reset_email_has_support_reply_to(self):
        """Test password reset email has support reply-to."""
        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch(
            "src.services.email_service.ConnectionConfig"
        ), patch(
            "src.services.email_service.FastMail"
        ) as mock_fastmail_class, patch(
            "src.services.email_service.MessageSchema"
        ) as mock_message_class:
            mock_fm = AsyncMock()
            mock_fm.send_message = AsyncMock()
            mock_fastmail_class.return_value = mock_fm

            from src.services.email_service import EmailService

            service = EmailService()
            await service.send_password_reset_email(
                to_email="user@example.com",
                username="John Doe",
                reset_link="https://example.com/reset",
            )

            # Check reply_to contains support email
            call_kwargs = mock_message_class.call_args.kwargs
            assert "support@saptiva.com" in call_kwargs["reply_to"]


class TestGetEmailService:
    """Test get_email_service singleton."""

    def test_returns_email_service(self):
        """Test returns EmailService instance."""
        import src.services.email_service as module

        # Reset singleton
        module._email_service = None

        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch("src.services.email_service.ConnectionConfig"):
            from src.services.email_service import EmailService, get_email_service

            service = get_email_service()
            assert isinstance(service, EmailService)

    def test_returns_same_instance(self):
        """Test returns same singleton instance."""
        import src.services.email_service as module

        # Reset singleton
        module._email_service = None

        mock_settings = _create_mock_settings()

        with patch(
            "src.services.email_service.get_settings", return_value=mock_settings
        ), patch("src.services.email_service.ConnectionConfig"):
            from src.services.email_service import get_email_service

            service1 = get_email_service()
            service2 = get_email_service()
            assert service1 is service2
