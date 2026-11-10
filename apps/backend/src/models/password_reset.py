"""
Password Reset Token Model.

Stores temporary tokens for password reset functionality.
"""

import secrets
from datetime import datetime, timedelta

from beanie import Document
from pydantic import Field


class PasswordResetToken(Document):
    """Password reset token for user authentication."""

    user_id: str = Field(..., description="User ID associated with this token")
    email: str = Field(..., description="User email")
    token: str = Field(..., description="Reset token (hashed)")
    expires_at: datetime = Field(..., description="Token expiration timestamp")
    used: bool = Field(default=False, description="Whether token has been used")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "password_reset_tokens"
        indexes = [
            "token",
            "user_id",
            "email",
            [("expires_at", 1)],  # TTL index for auto-deletion
        ]

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_expiration(hours: int = 1) -> datetime:
        """Create expiration timestamp."""
        return datetime.utcnow() + timedelta(hours=hours)

    def is_valid(self) -> bool:
        """Check if token is still valid."""
        return not self.used and self.expires_at > datetime.utcnow()

    async def mark_as_used(self) -> None:
        """Mark token as used."""
        self.used = True
        await self.save()
