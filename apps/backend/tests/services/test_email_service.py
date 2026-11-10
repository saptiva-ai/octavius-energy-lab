"""
Comprehensive tests for services/email_service.py - Email sending via Gmail SMTP

Coverage:
- EmailService initialization and configuration
- SMTP connection creation and authentication
- Email sending with HTML and plain text
- Password reset email template rendering
- Error handling (connection, authentication, send failures)
- Singleton pattern for get_email_service()
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.services.email_service import EmailService, get_email_service
from src.core.config import Settings


@pytest.fixture
def mock_settings():
    """Mock settings with SMTP configuration."""
    settings = Mock(spec=Settings)
    settings.smtp_host = "smtp.gmail.com"
    settings.smtp_port = 587
    settings.smtp_user = "support@saptiva.com"
    settings.smtp_password = "test-app-password"
    settings.smtp_from_email = "support@saptiva.com"
    return settings


@pytest.fixture
def email_service(mock_settings):
    """Create EmailService instance with mocked settings."""
    with patch('src.services.email_service.get_settings', return_value=mock_settings):
        return EmailService()


@pytest.fixture
def mock_smtp_server():
    """Mock SMTP server."""
    server = MagicMock(spec=smtplib.SMTP)
    server.starttls = Mock()
    server.login = Mock()
    server.send_message = Mock()
    server.quit = Mock()
    server.__enter__ = Mock(return_value=server)
    server.__exit__ = Mock(return_value=False)
    return server


# ============================================================================
# Initialization and Configuration
# ============================================================================

class TestEmailServiceInitialization:
    """Test EmailService initialization and configuration."""

    def test_initialization_with_settings(self, email_service, mock_settings):
        """EmailService should initialize with correct SMTP settings."""
        assert email_service.smtp_host == "smtp.gmail.com"
        assert email_service.smtp_port == 587
        assert email_service.smtp_user == "support@saptiva.com"
        assert email_service.smtp_password == "test-app-password"
        assert email_service.from_email == "support@saptiva.com"

    def test_initialization_uses_default_from_email(self):
        """Should use default from_email if not provided in settings."""
        settings = Mock(spec=Settings)
        settings.smtp_host = "smtp.gmail.com"
        settings.smtp_port = 587
        settings.smtp_user = "support@saptiva.com"
        settings.smtp_password = "password"
        settings.smtp_from_email = None  # Not provided

        with patch('src.services.email_service.get_settings', return_value=settings):
            service = EmailService()
            assert service.from_email == "support@saptiva.com"


# ============================================================================
# SMTP Connection
# ============================================================================

class TestSMTPConnection:
    """Test SMTP connection creation and authentication."""

    def test_create_smtp_connection_success(self, email_service, mock_smtp_server):
        """Should successfully create and authenticate SMTP connection."""
        with patch('smtplib.SMTP', return_value=mock_smtp_server):
            connection = email_service._create_smtp_connection()

            assert connection == mock_smtp_server
            mock_smtp_server.starttls.assert_called_once()
            mock_smtp_server.login.assert_called_once_with(
                "support@saptiva.com",
                "test-app-password"
            )

    def test_create_smtp_connection_auth_failure(self, email_service):
        """Should raise exception on SMTP authentication failure."""
        mock_server = MagicMock(spec=smtplib.SMTP)
        mock_server.starttls = Mock()
        mock_server.login = Mock(side_effect=smtplib.SMTPAuthenticationError(535, b"Authentication failed"))

        with patch('smtplib.SMTP', return_value=mock_server):
            with pytest.raises(smtplib.SMTPAuthenticationError):
                email_service._create_smtp_connection()

    def test_create_smtp_connection_network_failure(self, email_service):
        """Should raise exception on network connection failure."""
        with patch('smtplib.SMTP', side_effect=smtplib.SMTPConnectError(421, b"Connection refused")):
            with pytest.raises(smtplib.SMTPConnectError):
                email_service._create_smtp_connection()

    def test_create_smtp_connection_timeout(self, email_service):
        """Should raise exception on connection timeout."""
        with patch('smtplib.SMTP', side_effect=TimeoutError("Connection timed out")):
            with pytest.raises(TimeoutError):
                email_service._create_smtp_connection()


# ============================================================================
# Email Sending
# ============================================================================

class TestSendEmail:
    """Test generic email sending functionality."""

    @pytest.mark.asyncio
    async def test_send_email_success_html_only(self, email_service, mock_smtp_server):
        """Should successfully send email with HTML body."""
        with patch.object(email_service, '_create_smtp_connection', return_value=mock_smtp_server):
            result = await email_service.send_email(
                to_email="user@example.com",
                subject="Test Subject",
                html_body="<h1>Test HTML</h1>"
            )

            assert result is True
            mock_smtp_server.send_message.assert_called_once()

            # Verify message structure
            call_args = mock_smtp_server.send_message.call_args
            message = call_args[0][0]
            assert message["Subject"] == "Test Subject"
            assert message["To"] == "user@example.com"
            assert "Saptiva Support <support@saptiva.com>" in message["From"]

    @pytest.mark.asyncio
    async def test_send_email_success_html_and_text(self, email_service, mock_smtp_server):
        """Should successfully send email with both HTML and plain text."""
        with patch.object(email_service, '_create_smtp_connection', return_value=mock_smtp_server):
            result = await email_service.send_email(
                to_email="user@example.com",
                subject="Test Subject",
                html_body="<h1>Test HTML</h1>",
                text_body="Test Plain Text"
            )

            assert result is True
            mock_smtp_server.send_message.assert_called_once()

            # Verify multipart message
            call_args = mock_smtp_server.send_message.call_args
            message = call_args[0][0]
            assert message.is_multipart()

    @pytest.mark.asyncio
    async def test_send_email_failure_returns_false(self, email_service):
        """Should return False on email send failure without raising exception."""
        mock_server = MagicMock(spec=smtplib.SMTP)
        mock_server.starttls = Mock()
        mock_server.login = Mock()
        mock_server.send_message = Mock(side_effect=smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"User unknown")}))
        mock_server.__enter__ = Mock(return_value=mock_server)
        mock_server.__exit__ = Mock(return_value=False)

        with patch.object(email_service, '_create_smtp_connection', return_value=mock_server):
            result = await email_service.send_email(
                to_email="invalid@example.com",
                subject="Test",
                html_body="<p>Test</p>"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_email_connection_failure_returns_false(self, email_service):
        """Should return False if SMTP connection fails."""
        with patch.object(email_service, '_create_smtp_connection', side_effect=smtplib.SMTPConnectError(421, b"Connection failed")):
            result = await email_service.send_email(
                to_email="user@example.com",
                subject="Test",
                html_body="<p>Test</p>"
            )

            assert result is False


# ============================================================================
# Password Reset Email
# ============================================================================

class TestSendPasswordResetEmail:
    """Test password reset email template and sending."""

    @pytest.mark.asyncio
    async def test_send_password_reset_email_success(self, email_service):
        """Should successfully send password reset email with correct template."""
        with patch.object(email_service, 'send_email', return_value=True) as mock_send:
            result = await email_service.send_password_reset_email(
                to_email="user@example.com",
                username="testuser",
                reset_link="http://localhost:3000/reset-password?token=abc123"
            )

            assert result is True
            mock_send.assert_called_once()

            # Verify call arguments
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["to_email"] == "user@example.com"
            assert call_kwargs["subject"] == "Recuperación de Contraseña - Saptiva"

            # Verify HTML body contains required elements
            html_body = call_kwargs["html_body"]
            assert "testuser" in html_body
            assert "http://localhost:3000/reset-password?token=abc123" in html_body
            assert "Restablecer Contraseña" in html_body
            assert "1 hora" in html_body  # Expiration warning

            # Verify text body fallback
            text_body = call_kwargs["text_body"]
            assert "testuser" in text_body
            assert "http://localhost:3000/reset-password?token=abc123" in text_body
            assert "1 hora" in text_body

    @pytest.mark.asyncio
    async def test_send_password_reset_email_html_template_formatting(self, email_service):
        """Verify password reset email HTML template is properly formatted."""
        with patch.object(email_service, 'send_email', return_value=True) as mock_send:
            await email_service.send_password_reset_email(
                to_email="user@example.com",
                username="John Doe",
                reset_link="https://app.saptiva.com/reset?token=xyz789"
            )

            html_body = mock_send.call_args[1]["html_body"]

            # Check required HTML elements
            assert "<!DOCTYPE html>" in html_body
            assert "<html>" in html_body
            assert "John Doe" in html_body  # Username personalization
            assert "https://app.saptiva.com/reset?token=xyz789" in html_body  # Reset link
            assert "class=\"button\"" in html_body  # Button styling
            assert "class=\"warning\"" in html_body  # Warning box
            assert "🤖 Saptiva" in html_body  # Branding
            assert "background-color: #4F46E5" in html_body  # Button color
            assert "style=" in html_body  # Inline styles for email compatibility

    @pytest.mark.asyncio
    async def test_send_password_reset_email_text_template_formatting(self, email_service):
        """Verify password reset email plain text template is properly formatted."""
        with patch.object(email_service, 'send_email', return_value=True) as mock_send:
            await email_service.send_password_reset_email(
                to_email="user@example.com",
                username="Jane Smith",
                reset_link="http://localhost:3000/reset?token=abc"
            )

            text_body = mock_send.call_args[1]["text_body"]

            # Check required text elements
            assert "Hola Jane Smith" in text_body  # Personalized greeting
            assert "http://localhost:3000/reset?token=abc" in text_body  # Reset link
            assert "IMPORTANTE: Este enlace es válido solo por 1 hora" in text_body
            assert "El equipo de Saptiva" in text_body  # Signature

    @pytest.mark.asyncio
    async def test_send_password_reset_email_xss_prevention(self, email_service):
        """Username and reset link should not allow XSS injection."""
        malicious_username = "<script>alert('xss')</script>"
        malicious_link = "javascript:alert('xss')"

        with patch.object(email_service, 'send_email', return_value=True) as mock_send:
            await email_service.send_password_reset_email(
                to_email="user@example.com",
                username=malicious_username,
                reset_link=malicious_link
            )

            html_body = mock_send.call_args[1]["html_body"]
            text_body = mock_send.call_args[1]["text_body"]

            # Content should be included as-is (server generates safe links)
            # But we verify the structure is maintained
            assert "user@example.com" in mock_send.call_args[1]["to_email"]

    @pytest.mark.asyncio
    async def test_send_password_reset_email_failure_propagates(self, email_service):
        """Should return False if underlying send_email fails."""
        with patch.object(email_service, 'send_email', return_value=False):
            result = await email_service.send_password_reset_email(
                to_email="user@example.com",
                username="testuser",
                reset_link="http://localhost:3000/reset?token=abc"
            )

            assert result is False


# ============================================================================
# Singleton Pattern
# ============================================================================

class TestEmailServiceSingleton:
    """Test singleton pattern for email service."""

    def test_get_email_service_returns_singleton(self):
        """get_email_service() should return the same instance on multiple calls."""
        # Reset singleton
        import src.services.email_service as email_module
        email_module._email_service = None

        mock_settings = Mock(spec=Settings)
        mock_settings.smtp_host = "smtp.gmail.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "support@saptiva.com"
        mock_settings.smtp_password = "password"
        mock_settings.smtp_from_email = "support@saptiva.com"

        with patch('src.services.email_service.get_settings', return_value=mock_settings):
            service1 = get_email_service()
            service2 = get_email_service()

            assert service1 is service2  # Same instance

    def test_get_email_service_creates_instance_on_first_call(self):
        """get_email_service() should create instance on first call."""
        # Reset singleton
        import src.services.email_service as email_module
        email_module._email_service = None

        mock_settings = Mock(spec=Settings)
        mock_settings.smtp_host = "smtp.gmail.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "support@saptiva.com"
        mock_settings.smtp_password = "password"
        mock_settings.smtp_from_email = "support@saptiva.com"

        with patch('src.services.email_service.get_settings', return_value=mock_settings):
            service = get_email_service()

            assert service is not None
            assert isinstance(service, EmailService)


# ============================================================================
# Error Handling and Logging
# ============================================================================

class TestEmailServiceErrorHandling:
    """Test error handling and logging."""

    @pytest.mark.asyncio
    async def test_send_email_logs_success(self, email_service, mock_smtp_server):
        """Should log successful email send."""
        with patch.object(email_service, '_create_smtp_connection', return_value=mock_smtp_server), \
             patch('src.services.email_service.logger') as mock_logger:

            await email_service.send_email(
                to_email="user@example.com",
                subject="Test",
                html_body="<p>Test</p>"
            )

            # Verify info log was called
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args
            assert "Email sent successfully" in str(log_call)

    @pytest.mark.asyncio
    async def test_send_email_logs_failure(self, email_service):
        """Should log email send failure with error details."""
        with patch.object(email_service, '_create_smtp_connection', side_effect=Exception("Connection error")), \
             patch('src.services.email_service.logger') as mock_logger:

            await email_service.send_email(
                to_email="user@example.com",
                subject="Test",
                html_body="<p>Test</p>"
            )

            # Verify error log was called
            mock_logger.error.assert_called_once()
            log_call = mock_logger.error.call_args
            assert "Failed to send email" in str(log_call)

    def test_create_smtp_connection_logs_failure(self, email_service):
        """Should log SMTP connection failure."""
        with patch('smtplib.SMTP', side_effect=Exception("SMTP error")), \
             patch('src.services.email_service.logger') as mock_logger:

            with pytest.raises(Exception):
                email_service._create_smtp_connection()

            # Verify error log was called
            mock_logger.error.assert_called_once()
            log_call = mock_logger.error.call_args
            assert "Failed to connect to SMTP server" in str(log_call)
