"""Services for managing runtime system settings such as the SAPTIVA API key."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

import httpx
import structlog

from ..core.config import get_settings
from ..core.crypto import decrypt_secret, encrypt_secret
from ..models.system_settings import SystemSettings

logger = structlog.get_logger(__name__)


async def _ensure_settings_document() -> SystemSettings:
    document = await SystemSettings.find_one(SystemSettings.id == "global")
    if document is None:
        document = SystemSettings()
        await document.insert()
    return document


async def load_saptiva_api_key() -> Optional[str]:
    """Return the configured SAPTIVA API key, preferring the database over env."""
    settings = get_settings()
    secret = settings.secret_key

    document = await SystemSettings.find_one(SystemSettings.id == "global")
    if document and document.saptiva_api_key_encrypted:
        decrypted = decrypt_secret(secret, document.saptiva_api_key_encrypted)
        if decrypted:
            return decrypted

    # Fallback to environment variable
    env_key = settings.saptiva_api_key
    return env_key or None


async def validate_saptiva_api_key(api_key: str) -> Tuple[bool, str]:
    """Validate the provided API key against SAPTIVA's API."""
    settings = get_settings()
    base_url = settings.saptiva_base_url.rstrip("/")
    url = f"{base_url}/v1/models"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            models = data.get("data", []) if isinstance(data, dict) else []
            message = f"Valid key. {len(models)} models available."
            return True, message

        if response.status_code == 401:
            return False, "SAPTIVA rejected the key (401 Unauthorized)."

        return False, f"SAPTIVA validation failed with status {response.status_code}."

    except httpx.RequestError as exc:
        logger.warning("Saptiva validation network error", error=str(exc))
        return False, "No fue posible contactar a SAPTIVA para validar la key."

    except Exception as exc:  # pragma: no cover - safeguard
        logger.error("Unexpected error validating SAPTIVA key", error=str(exc))
        return False, "Error inesperado al validar la key."


async def update_saptiva_api_key(
    api_key: str, user_id: Optional[str], validation_message: str
) -> SystemSettings:
    """Persist a validated API key and sync runtime clients."""
    settings = get_settings()
    secret = settings.secret_key

    document = await _ensure_settings_document()
    document.saptiva_api_key_encrypted = encrypt_secret(secret, api_key)
    document.saptiva_key_hint = _redact_key(api_key)
    document.saptiva_key_last_validated_at = datetime.utcnow()
    document.saptiva_key_last_status = validation_message
    document.saptiva_key_source = "database"
    document.saptiva_key_updated_at = datetime.utcnow()
    document.saptiva_key_updated_by = user_id
    await document.save()

    await _sync_saptiva_client(api_key)
    return document


async def clear_saptiva_api_key(user_id: Optional[str]) -> SystemSettings:
    """Remove the persisted API key and fall back to environment configuration."""
    document = await _ensure_settings_document()
    document.saptiva_api_key_encrypted = None
    document.saptiva_key_hint = None
    document.saptiva_key_last_status = (
        "Configured via environment"
        if get_settings().saptiva_api_key
        else "Key removed"
    )
    document.saptiva_key_source = (
        "environment" if get_settings().saptiva_api_key else "unset"
    )
    document.saptiva_key_updated_at = datetime.utcnow()
    document.saptiva_key_updated_by = user_id
    await document.save()

    await _sync_saptiva_client(await load_saptiva_api_key())
    return document


async def get_saptiva_key_status() -> dict:
    """Build a status payload for API consumers."""
    settings = get_settings()
    document = await SystemSettings.find_one(SystemSettings.id == "global")

    env_key = settings.saptiva_api_key
    env_configured = bool(env_key)

    status_source = "unset"
    configured = False
    hint = None
    last_validated: Optional[datetime] = None
    last_status: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    if document and document.saptiva_api_key_encrypted:
        status_source = "database"
        configured = True
        hint = document.saptiva_key_hint
        last_validated = document.saptiva_key_last_validated_at
        last_status = document.saptiva_key_last_status
        updated_at = document.saptiva_key_updated_at
        updated_by = document.saptiva_key_updated_by
    elif env_configured:
        status_source = "environment"
        configured = True
        hint = _redact_key(env_key)
        last_status = "Configured via environment variable"
    else:
        status_source = "unset"
        configured = False
        last_status = "SAPTIVA_API_KEY not configured"

    return {
        "configured": configured,
        "mode": "live" if configured else "demo",
        "source": status_source,
        "hint": hint,
        "last_validated_at": last_validated,
        "status_message": last_status,
        "updated_at": updated_at,
        "updated_by": updated_by,
    }


async def _sync_saptiva_client(api_key: Optional[str]) -> None:
    """Update the shared SAPTIVA client with the latest key."""
    try:
        from .saptiva_client import get_saptiva_client

        client = await get_saptiva_client()
        client.set_api_key(api_key)
    except Exception as exc:  # pragma: no cover - safeguard
        logger.error("Failed to sync SAPTIVA client with new API key", error=str(exc))


def _redact_key(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    return f"••••{api_key[-4:]}" if len(api_key) >= 4 else "••••"
