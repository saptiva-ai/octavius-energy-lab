"""
Security utilities for password reset tokens.
"""

import hashlib
import hmac
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, status
from jwt.exceptions import ExpiredSignatureError
from jwt.exceptions import PyJWTError as JWTError

from .config import get_settings

# Token constants
RESET_TOKEN_TYPE = "reset"
RESET_TOKEN_EXPIRE_MINUTES = 30


def _huella_password(password_hash: str) -> str:
    """HMAC del hash vigente de la contraseña con el secreto del servidor: el
    token no lleva el hash y deja de coincidir en cuanto la contraseña cambia."""
    settings = get_settings()
    return hmac.new(
        settings.secret_key.encode(), (password_hash or "").encode(), hashlib.sha256
    ).hexdigest()


def create_password_reset_token(email: str, password_hash: str) -> str:
    """
    Generates a JWT containing the email and expiration for password reset.

    Args:
        email: User's email address
        password_hash: Current password hash; the token is only valid while
            it does not change, so the link works once (2026-10-20)

    Returns:
        Encoded JWT string
    """
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "sub": email,
        "type": RESET_TOKEN_TYPE,
        "pwh": _huella_password(password_hash),
    }

    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def verify_password_reset_token(token: str) -> str:
    """
    Decodes and validates the password reset token.

    Args:
        token: The JWT token string

    Returns:
        The email address from the token if valid

    Raises:
        HTTPException: If token is invalid, expired, or wrong type
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )

        token_type = payload.get("type")
        email = payload.get("sub")

        if token_type != RESET_TOKEN_TYPE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de token inválido"
            )

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token inválido: falta el correo electrónico",
            )

        return email

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace de recuperación ha expirado",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enlace de recuperación inválido",
        )


def verificar_huella_reset(token: str, password_hash: str) -> None:
    """El enlace sigue valiendo solo si la contraseña no ha cambiado desde que
    se pidió. Sin esto el mismo enlace la cambiaba varias veces durante sus 30
    minutos (verificación del 2026-10-20). Llamar después de
    `verify_password_reset_token`, con el hash vigente del usuario."""
    settings = get_settings()
    payload = jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
    huella = str(payload.get("pwh") or "")
    if not huella or not hmac.compare_digest(huella, _huella_password(password_hash)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este enlace ya se usó o ya no es válido. Pide uno nuevo.",
        )
