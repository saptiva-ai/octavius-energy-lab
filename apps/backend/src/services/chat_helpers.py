"""
Chat Helper Functions - Utilities for chat message processing.

This module contains helper functions extracted from chat.py router
following Single Responsibility Principle.

Functions:
    - is_document_ready_and_cached: Check if document is ready and cached
    - wait_for_documents_ready: Best-effort wait for document processing
    - build_chat_context: Build ChatContext from request
"""

import asyncio
from datetime import datetime
from typing import List
from uuid import uuid4

import structlog

from ..core.config import Settings, default_chat_model
from ..domain import ChatContext
from ..models.document import Document, DocumentStatus
from ..schemas.chat import ChatRequest
from ..services.tools import normalize_tools_state

logger = structlog.get_logger(__name__)


async def is_document_ready_and_cached(
    file_id: str, user_id: str, redis_client
) -> bool:
    """
    Check if a document belongs to the user, is READY, and has cached text.

    Args:
        file_id: Document ID to check
        user_id: User ID for ownership validation
        redis_client: Redis client instance

    Returns:
        True if document is ready and cached, False otherwise
    """
    if not file_id:
        return False

    try:
        document = await Document.get(file_id)
    except Exception as exc:
        logger.warning("Document lookup failed", file_id=file_id, error=str(exc))
        return False

    # Validate ownership and status
    if not document or document.user_id != user_id:
        return False

    if document.status != DocumentStatus.READY:
        return False

    # Check cache
    redis_key = f"doc:text:{file_id}"

    try:
        cached_value = await redis_client.get(redis_key)
    except Exception as exc:
        logger.warning("Redis cache lookup failed", file_id=file_id, error=str(exc))
        return False

    return bool(cached_value)


async def wait_for_documents_ready(
    file_ids: List[str],
    user_id: str,
    redis_client,
    max_wait_ms: int = 1200,
    step_ms: int = 150,
) -> None:
    """
    Best-effort wait for documents to reach READY status and have cached text.

    This function polls documents until they are ready or timeout is reached.
    It does not raise exceptions on timeout.

    Args:
        file_ids: List of document IDs to wait for
        user_id: User ID for ownership validation
        redis_client: Redis client instance
        max_wait_ms: Maximum wait time in milliseconds (default: 1200ms)
        step_ms: Poll interval in milliseconds (default: 150ms)
    """
    if not file_ids:
        return

    # Remove duplicates while preserving order
    unique_ids = list(dict.fromkeys(file_ids))
    if not unique_ids:
        return

    waited_ms = 0
    missing: List[str] = unique_ids

    while waited_ms <= max_wait_ms:
        current_missing: List[str] = []

        for fid in unique_ids:
            ready = await is_document_ready_and_cached(fid, user_id, redis_client)
            if not ready:
                current_missing.append(fid)

        # All documents ready
        if not current_missing:
            if waited_ms > 0:
                logger.info(
                    "Documents ready after waiting",
                    file_ids=unique_ids,
                    waited_ms=waited_ms,
                )
            return

        # Wait before next poll
        await asyncio.sleep(step_ms / 1000)
        waited_ms += step_ms
        missing = current_missing

    # Timeout reached with missing documents
    if missing:
        logger.info(
            "Document wait timeout",
            missing_file_ids=missing,
            waited_ms=waited_ms,
            total_ids=len(unique_ids),
        )


def build_chat_context(
    request: ChatRequest, user_id: str, settings: Settings
) -> ChatContext:
    """
    Build ChatContext from ChatRequest.

    Encapsulates all request data into immutable dataclass with defaults.

    Args:
        request: ChatRequest from endpoint
        user_id: Authenticated user ID
        settings: Application settings

    Returns:
        ChatContext with all request data

    Notes:
        - Model defaults to "Saptiva Turbo" (case-sensitive)
        - Stream flag defaults to False
        - Kill switch is DISABLED when attachments are present (forces tool usage)
        - Kill switch applies from settings only for non-document queries
    """
    # Compute document IDs early
    document_ids_list = (
        (request.file_ids or []) + (request.document_ids or [])
        if (request.file_ids or request.document_ids)
        else []
    )
    has_attachments = len(document_ids_list) > 0

    # 🔧 FIX: Disable kill switch when attachments are present
    # This ensures the LLM has access to document context via tools
    kill_switch = settings.deep_research_kill_switch and not has_attachments

    if has_attachments and settings.deep_research_kill_switch:
        logger.info(
            "Kill switch DISABLED due to attachments",
            user_id=user_id,
            attachment_count=len(document_ids_list),
            reason="documents_require_tool_access",
        )

    return ChatContext(
        user_id=user_id,
        request_id=str(uuid4()),
        timestamp=datetime.utcnow(),
        chat_id=request.chat_id,
        session_id=None,  # Will be resolved during processing
        message=request.message,
        context=request.context,
        document_ids=document_ids_list if has_attachments else None,
        # Default configurable (CHAT_DEFAULT_MODEL): estaba hardcodeado y al
        # cambiar de gateway toda petición sin modelo explícito fallaba con
        # `model_not_found`.
        model=request.model
        or getattr(settings, "chat_default_model", None)
        or default_chat_model(),
        tools_enabled=normalize_tools_state(request.tools_enabled),
        stream=getattr(request, "stream", False),  # Streaming disabled by default
        temperature=getattr(request, "temperature", None),
        max_tokens=getattr(request, "max_tokens", None),
        kill_switch_active=kill_switch,  # 🔧 FIX: Conditional kill switch
    )
