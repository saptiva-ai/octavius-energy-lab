"""
Unit tests for core/security module.

Tests:
- RESET_TOKEN_TYPE constant
- RESET_TOKEN_EXPIRE_MINUTES constant
- create_password_reset_token function
- verify_password_reset_token function
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
import jwt

from src.core.security import (
    RESET_TOKEN_EXPIRE_MINUTES,
    RESET_TOKEN_TYPE,
    create_password_reset_token,
    verify_password_reset_token,
)

pytestmark = [pytest.mark.unit]


class TestResetTokenConstants:
    """Test reset token constants."""

    def test_reset_token_type(self):
        """Test RESET_TOKEN_TYPE is 'reset'."""
        assert RESET_TOKEN_TYPE == "reset"

    def test_reset_token_expire_minutes(self):
        """Test RESET_TOKEN_EXPIRE_MINUTES is 30."""
        assert RESET_TOKEN_EXPIRE_MINUTES == 30

    def test_expire_minutes_is_positive(self):
        """Test expiration is positive."""
        assert RESET_TOKEN_EXPIRE_MINUTES > 0


class TestCreatePasswordResetToken:
    """Test create_password_reset_token function."""

    def test_creates_valid_token(self):
        """Test creates a valid JWT token."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        with patch("src.core.security.get_settings", return_value=mock_settings):
            token = create_password_reset_token("test@example.com", "hash-actual")

            assert isinstance(token, str)
            assert len(token) > 0

    def test_token_contains_email(self):
        """Test token contains email in 'sub' claim."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        with patch("src.core.security.get_settings", return_value=mock_settings):
            token = create_password_reset_token("user@example.com", "hash-actual")

            # Decode without verification to check payload
            payload = jwt.decode(
                token, mock_settings.secret_key, algorithms=["HS256"]
            )
            assert payload["sub"] == "user@example.com"

    def test_token_contains_reset_type(self):
        """Test token contains reset type."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        with patch("src.core.security.get_settings", return_value=mock_settings):
            token = create_password_reset_token("user@example.com", "hash-actual")

            payload = jwt.decode(
                token, mock_settings.secret_key, algorithms=["HS256"]
            )
            assert payload["type"] == RESET_TOKEN_TYPE

    def test_token_contains_expiration(self):
        """Test token contains expiration claim."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        with patch("src.core.security.get_settings", return_value=mock_settings):
            before = datetime.utcnow()
            token = create_password_reset_token("user@example.com", "hash-actual")
            after = datetime.utcnow()

            payload = jwt.decode(
                token, mock_settings.secret_key, algorithms=["HS256"]
            )
            # Use utcfromtimestamp to match utcnow()
            exp = datetime.utcfromtimestamp(payload["exp"])

            # Expiration should be ~30 minutes from now
            # Add 1 second buffer since JWT exp is in seconds (no microseconds)
            expected_min = before + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES) - timedelta(seconds=1)
            expected_max = after + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES + 1)

            assert exp >= expected_min
            assert exp <= expected_max


class TestVerifyPasswordResetToken:
    """Test verify_password_reset_token function."""

    def test_verifies_valid_token(self):
        """Test verifies valid token and returns email."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        with patch("src.core.security.get_settings", return_value=mock_settings):
            # Create a valid token
            token = create_password_reset_token("test@example.com", "hash-actual")

            # Verify it
            email = verify_password_reset_token(token)

            assert email == "test@example.com"

    def test_raises_on_expired_token(self):
        """Test raises HTTPException for expired token."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        # Create an expired token directly
        expired_payload = {
            "exp": datetime.utcnow() - timedelta(hours=1),
            "sub": "test@example.com",
            "type": RESET_TOKEN_TYPE,
        }
        expired_token = jwt.encode(
            expired_payload, mock_settings.secret_key, algorithm="HS256"
        )

        with patch("src.core.security.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_password_reset_token(expired_token)

            assert exc_info.value.status_code == 400
            assert "expirado" in exc_info.value.detail.lower()

    def test_raises_on_invalid_token(self):
        """Test raises HTTPException for invalid token."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        with patch("src.core.security.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_password_reset_token("invalid.token.here")

            assert exc_info.value.status_code == 400
            assert "inválido" in exc_info.value.detail.lower()

    def test_raises_on_wrong_secret(self):
        """Test raises HTTPException for token signed with different secret."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "original-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        # Create token with different secret
        payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "sub": "test@example.com",
            "type": RESET_TOKEN_TYPE,
        }
        wrong_token = jwt.encode(payload, "different-secret-key", algorithm="HS256")

        with patch("src.core.security.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_password_reset_token(wrong_token)

            assert exc_info.value.status_code == 400

    def test_raises_on_wrong_token_type(self):
        """Test raises HTTPException for wrong token type."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        # Create token with wrong type
        payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "sub": "test@example.com",
            "type": "access",  # Wrong type
        }
        wrong_type_token = jwt.encode(
            payload, mock_settings.secret_key, algorithm="HS256"
        )

        with patch("src.core.security.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_password_reset_token(wrong_type_token)

            assert exc_info.value.status_code == 400
            assert "inválido" in exc_info.value.detail.lower()

    def test_raises_on_missing_email(self):
        """Test raises HTTPException when email is missing."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"

        # Create token without email
        payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "type": RESET_TOKEN_TYPE,
            # No "sub" claim
        }
        no_email_token = jwt.encode(
            payload, mock_settings.secret_key, algorithm="HS256"
        )

        with patch("src.core.security.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                verify_password_reset_token(no_email_token)

            assert exc_info.value.status_code == 400
            assert "correo" in exc_info.value.detail.lower()


class TestHuellaDelResetToken:
    """El token de reseteo lleva una huella del hash vigente (2026-10-20): sin
    ella el mismo enlace servía varias veces durante 30 minutos."""

    @staticmethod
    def _settings():
        mock_settings = MagicMock()
        mock_settings.secret_key = "test-secret-key-12345"
        mock_settings.jwt_algorithm = "HS256"
        return mock_settings

    def test_la_huella_coincide_con_el_hash_vigente(self):
        from src.core.security import verificar_huella_reset

        with patch("src.core.security.get_settings", return_value=self._settings()):
            token = create_password_reset_token("u@example.com", "hash-1")
            verificar_huella_reset(token, "hash-1")  # no lanza

    def test_otro_hash_rechaza_el_enlace(self):
        from src.core.security import verificar_huella_reset

        with patch("src.core.security.get_settings", return_value=self._settings()):
            token = create_password_reset_token("u@example.com", "hash-1")
            with pytest.raises(HTTPException) as exc:
                verificar_huella_reset(token, "hash-2")
        assert exc.value.status_code == 400
        assert "ya se usó" in exc.value.detail

    def test_un_token_sin_huella_se_rechaza(self):
        from src.core.security import verificar_huella_reset

        ajustes = self._settings()
        viejo = jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(minutes=5),
                "sub": "u@example.com",
                "type": RESET_TOKEN_TYPE,
            },
            ajustes.secret_key,
            algorithm="HS256",
        )
        with patch("src.core.security.get_settings", return_value=ajustes):
            with pytest.raises(HTTPException):
                verificar_huella_reset(viejo, "hash-1")

    def test_el_token_no_lleva_el_hash(self):
        ajustes = self._settings()
        with patch("src.core.security.get_settings", return_value=ajustes):
            token = create_password_reset_token("u@example.com", "$argon2id$secreto")
        payload = jwt.decode(token, ajustes.secret_key, algorithms=["HS256"])
        assert "$argon2id$secreto" not in str(payload)
