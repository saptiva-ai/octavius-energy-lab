"""
File URL Presigning Service

Generates presigned URLs for file access with cache-busting via content hash.

Política de adjuntos: un mensaje guarda exactamente los adjuntos enviados en su payload.
No existe "herencia" de adjuntos desde turnos previos.
El adaptador al LLM serializa solo el content del último turno del usuario, con sus imágenes.
"""

import hashlib
from typing import Optional

import structlog

from ..core.config import get_settings
from ..models.document import Document

logger = structlog.get_logger(__name__)


async def presign_file_url(
    file_id: str, user_id: Optional[str] = None
) -> Optional[str]:
    """
    Generate presigned URL for file with content-based hash in path.

    Args:
        file_id: Document/file ID
        user_id: Optional user ID for ownership validation

    Returns:
        Presigned URL with content hash, or None if file not found/expired

    Example:
        /api/files/{file_id}/content?hash={sha256[:8]}
    """
    settings = get_settings()

    try:
        # Fetch document with ownership validation
        document = await Document.get(file_id)

        if not document:
            logger.warning("presign_file_not_found", file_id=file_id)
            return None

        # Validate ownership if user_id provided
        if user_id and document.user_id != user_id:
            logger.warning(
                "presign_ownership_mismatch",
                file_id=file_id,
                expected_user=user_id,
                actual_user=document.user_id,
            )
            return None

        # Check if document is ready
        if document.status != "READY":
            logger.warning(
                "presign_file_not_ready", file_id=file_id, status=document.status
            )
            return None

        # Generate content hash for cache-busting
        # Use file_id + filename as stable hash (actual content hash would require S3 fetch)
        content_seed = f"{file_id}:{document.filename}:{document.created_at}"
        content_hash = hashlib.sha256(content_seed.encode()).hexdigest()[:8]

        # Construct URL with hash parameter
        base_url = settings.api_base_url or "http://localhost:8000"
        presigned_url = f"{base_url}/api/files/{file_id}/content?hash={content_hash}"

        logger.debug(
            "presign_url_generated",
            file_id=file_id,
            filename=document.filename,
            hash=content_hash,
        )

        return presigned_url

    except Exception as exc:
        logger.error("presign_failed", file_id=file_id, error=str(exc), exc_info=True)
        return None


def url_fingerprint(url: str) -> str:
    """
    Generate short hash fingerprint of URL for logging.

    Args:
        url: Full URL

    Returns:
        8-character hex hash
    """
    return hashlib.sha1(url.encode()).hexdigest()[:8]
