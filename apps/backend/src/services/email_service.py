"""
Email Service for sending transactional emails.

Uses fastapi-mail with Gmail SMTP for password reset and notifications.
"""

from typing import List, Optional

import structlog
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from ..core.config import get_settings

logger = structlog.get_logger(__name__)


class EmailService:
    """Service for sending emails via Gmail SMTP using fastapi-mail."""

    def __init__(self):
        self.settings = get_settings()

        # Validate configuration
        if not self.settings.smtp_user or not self.settings.smtp_password:
            logger.warning("SMTP credentials not configured. Emails will fail.")

        self.conf = ConnectionConfig(
            MAIL_USERNAME=self.settings.smtp_user,
            MAIL_PASSWORD=self.settings.smtp_password,
            MAIL_FROM=self.settings.smtp_from_email,
            MAIL_PORT=self.settings.smtp_port,
            MAIL_SERVER=self.settings.smtp_host,
            MAIL_FROM_NAME=self.settings.mail_from_name,
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
        )

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        reply_to: Optional[List[str]] = None,
    ) -> bool:
        """
        Send email via fastapi-mail.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            reply_to: List of reply-to email addresses

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_body,
                subtype=MessageType.html,
                reply_to=reply_to,
            )

            fm = FastMail(self.conf)
            await fm.send_message(message)

            logger.info("Email sent successfully", to=to_email, subject=subject)
            return True

        except Exception as e:
            logger.error(
                "Failed to send email",
                to=to_email,
                subject=subject,
                error=str(e),
                exc_type=type(e).__name__,
            )
            return False

    async def send_password_reset_email(
        self, to_email: str, username: str, reset_link: str
    ) -> bool:
        """
        Send password reset email with reply-to configured to support team.

        Args:
            to_email: User's email address
            username: User's name
            reset_link: Password reset link with token

        Returns:
            True if email sent successfully
        """
        subject = "Octavios: Restablecer Contraseña"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .container {{
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo {{
            font-size: 24px;
            font-weight: bold;
            color: #4F46E5;
        }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #4F46E5;
            color: #ffffff !important;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            margin: 20px 0;
        }}
        .button:hover {{
            background-color: #4338CA;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #E5E7EB;
            font-size: 14px;
            color: #6B7280;
        }}
        .warning {{
            background-color: #FEF3C7;
            border-left: 4px solid #F59E0B;
            padding: 12px;
            margin: 20px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🤖 Octavios</div>
            <h2 style="color: #1F2937; margin-top: 10px;">Recuperación de Contraseña</h2>
        </div>

        <p>Hola <strong>{username}</strong>,</p>

        <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta.</p>

        <p>Para crear una nueva contraseña, haz clic en el siguiente enlace:</p>

        <div style="text-align: center;">
            <a href="{reset_link}" class="button">Restablecer Contraseña</a>
        </div>

        <div class="warning">
            <strong>⚠️ Importante:</strong> Este enlace es válido solo por <strong>30 minutos</strong>.
        </div>

        <p>Si no solicitaste esto, ignora este correo.</p>

        <div class="footer">
            <p>Saludos,<br>El equipo de <strong>Octavios Support</strong></p>
        </div>
    </div>
</body>
</html>
"""
        # Reply-to configuration as requested
        reply_to = ["support@saptiva.com"]

        return await self.send_email(
            to_email=to_email, subject=subject, html_body=html_body, reply_to=reply_to
        )


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
