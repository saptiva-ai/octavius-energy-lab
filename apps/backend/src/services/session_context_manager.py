"""
Session Context Manager - Manages file context persistence for chat sessions.

This module handles the logic for maintaining file attachments across messages
in a chat session, following the "keep only latest message's attachments" strategy.

Responsibilities:
    - Normalize file IDs (remove duplicates, preserve order)
    - Determine current file context (request vs session)
    - Update session with new file attachments
    - Wait for documents to be ready before processing
"""

from datetime import datetime
from typing import List

import structlog
from beanie.operators import Set
from bson import ObjectId

from ..core.redis_cache import RedisCache
from ..models.chat import ChatSession as ChatSessionModel
from .chat_helpers import wait_for_documents_ready

logger = structlog.get_logger(__name__)


class SessionContextManager:
    """
    Manages file context for chat sessions.

    This class encapsulates the complex logic of file context persistence,
    following Single Responsibility Principle.
    """

    @staticmethod
    def normalize_file_ids(file_ids: List[str]) -> List[str]:
        """
        Normalize file IDs by removing duplicates while preserving order.

        Args:
            file_ids: List of file IDs (may contain duplicates)

        Returns:
            List of unique file IDs in original order
        """
        if not file_ids:
            return []
        return list(dict.fromkeys(file_ids))

    @staticmethod
    def determine_current_files(
        request_file_ids: List[str], session_file_ids: List[str]
    ) -> List[str]:
        """
        Determine which files should be used for this message.

        Strategy: Use request files if provided, otherwise reuse session files.

        Args:
            request_file_ids: Files provided in current request
            session_file_ids: Files attached to session from previous message

        Returns:
            List of file IDs to use for current message
        """
        if request_file_ids:
            # New message provides files → use them
            return request_file_ids
        else:
            # No files in request → reuse context from previous message
            return session_file_ids

    @staticmethod
    async def wait_for_files_ready(
        file_ids: List[str], user_id: str, redis_cache: RedisCache
    ) -> None:
        """
        Wait for documents to be processed and cached.

        Args:
            file_ids: List of document IDs
            user_id: User ID for ownership validation
            redis_cache: Redis cache instance
        """
        if not file_ids:
            return

        await wait_for_documents_ready(
            file_ids=file_ids, user_id=user_id, redis_client=redis_cache.client
        )

    @staticmethod
    async def adopt_orphaned_files(
        file_ids: List[str], session_id: str, user_id: str
    ) -> int:
        """
        Adopt orphaned files by linking them to the new session (AGGRESSIVE UPDATE).

        This handles the case where files were uploaded before the session
        was created (e.g., in a "phantom chat" with temporary UUID or draft mode).

        CRITICAL: This method uses AGGRESSIVE ADOPTION strategy:
        - Files are adopted based ONLY on file_id + user_id match
        - Ignores existing conversation_id (could be phantom UUID, None, or other)
        - This is safe because we validate ownership before update

        Args:
            file_ids: List of file IDs to adopt
            session_id: New session ID to link files to
            user_id: User ID for ownership validation

        Returns:
            Number of files successfully adopted
        """
        if not file_ids:
            return 0

        from ..models.document import Document

        # Normalize IDs for paranoid matching (ObjectId + string IDs)
        object_ids: List[ObjectId] = []
        str_ids: List[str] = []
        for fid in file_ids:
            fid_str = str(fid)
            str_ids.append(fid_str)
            if ObjectId.is_valid(fid_str):
                object_ids.append(ObjectId(fid_str))

        or_clauses = []
        if object_ids:
            or_clauses.append({"_id": {"$in": object_ids}})
        if str_ids:
            or_clauses.append({"file_id": {"$in": str_ids}})
            or_clauses.append({"id": {"$in": str_ids}})

        if not or_clauses:
            logger.warning(
                "No valid file IDs to adopt", session_id=session_id, file_ids=file_ids
            )
            return 0

        filter_query = {"$or": or_clauses, "user_id": user_id}

        try:
            update_result = await Document.find_many(filter_query).update(
                Set(
                    {
                        Document.conversation_id: session_id,
                        Document.updated_at: datetime.utcnow(),
                    }
                )
            )

            modified = getattr(update_result, "modified_count", 0)
            matched = getattr(update_result, "matched_count", None)

            logger.info(
                "🔒 [AGGRESSIVE ADOPTION] Files adopted with Beanie bulk update",
                session_id=session_id,
                matched_count=matched,
                modified_count=modified,
                total_requested=len(file_ids),
                file_ids=file_ids,
            )

            if matched is not None and matched < len(file_ids):
                logger.warning(
                    "⚠️ Some files not found or ownership mismatch",
                    requested=len(file_ids),
                    matched=matched,
                    missing_count=len(file_ids) - matched,
                )

            return modified

        except Exception as e:
            logger.error(
                "Bulk file adoption failed",
                session_id=session_id,
                file_ids=file_ids,
                error=str(e),
                exc_type=type(e).__name__,
                exc_info=True,
            )
            return 0

    @staticmethod
    async def update_session_files(
        chat_session: ChatSessionModel,
        new_file_ids: List[str],
        previous_file_ids: List[str],
    ) -> bool:
        """
        Update session's attached_file_ids if files changed.

        Args:
            chat_session: ChatSession model instance
            new_file_ids: New file IDs from current request
            previous_file_ids: Previous file IDs from session

        Returns:
            True if session was updated, False otherwise
        """
        # Only update if files changed
        if not new_file_ids or new_file_ids == previous_file_ids:
            return False

        await chat_session.update(
            {
                "$set": {
                    "attached_file_ids": new_file_ids,
                    "updated_at": datetime.utcnow(),
                }
            }
        )

        chat_session.attached_file_ids = new_file_ids

        logger.info(
            "Updated session attached_file_ids",
            chat_id=chat_session.id,
            file_count=len(new_file_ids),
            replaced_previous=bool(previous_file_ids),
        )

        return True

    @staticmethod
    async def prepare_session_context(
        chat_session: ChatSessionModel,
        request_file_ids: List[str],
        user_id: str,
        redis_cache: RedisCache,
        request_id: str,
    ) -> List[str]:
        """
        Prepare session context with files (high-level orchestration).

        This method:
        1. Normalizes request file IDs
        2. **IMMEDIATELY adopts orphaned files** (CRITICAL for race condition prevention)
        3. Determines current files (request vs session)
        4. Waits for documents to be ready
        5. Updates session if files changed
        6. Logs context for observability

        Args:
            chat_session: ChatSession model instance
            request_file_ids: File IDs from current request
            user_id: User ID
            redis_cache: Redis cache instance
            request_id: Request ID for logging

        Returns:
            List of file IDs to use for this message
        """
        # 1. Normalize request files
        normalized_request_files = SessionContextManager.normalize_file_ids(
            request_file_ids
        )

        # 2. 🚨 CRITICAL: Adopt orphaned files IMMEDIATELY
        # This MUST happen BEFORE any tool invocation to prevent race condition
        # Files uploaded before session creation need conversation_id set NOW
        if normalized_request_files and chat_session.id:
            logger.info(
                "🔒 [RACE CONDITION FIX] Adopting orphaned files IMMEDIATELY",
                session_id=str(chat_session.id),
                file_count=len(normalized_request_files),
                nonce=request_id[:8],
            )
            adopted_count = await SessionContextManager.adopt_orphaned_files(
                file_ids=normalized_request_files,
                session_id=str(chat_session.id),
                user_id=user_id,
            )
            logger.info(
                "🔒 [RACE CONDITION FIX] File adoption completed",
                session_id=str(chat_session.id),
                adopted_count=adopted_count,
                total_files=len(normalized_request_files),
                nonce=request_id[:8],
            )

        # 3. Get session files
        session_file_ids = list(getattr(chat_session, "attached_file_ids", []) or [])

        # 4. Determine current files
        current_file_ids = SessionContextManager.determine_current_files(
            normalized_request_files, session_file_ids
        )

        # 5. Log for observability
        logger.info(
            "Session context prepared",
            request_file_ids_count=len(normalized_request_files),
            session_file_ids_count=len(session_file_ids),
            current_file_ids_count=len(current_file_ids),
            current_file_ids=current_file_ids,
            nonce=request_id[:8],
        )

        # 6. Wait for documents to be ready
        await SessionContextManager.wait_for_files_ready(
            current_file_ids, user_id, redis_cache
        )

        # 7. Update session if files changed
        await SessionContextManager.update_session_files(
            chat_session, normalized_request_files, session_file_ids
        )

        return current_file_ids
