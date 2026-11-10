"""
Unified history service for managing chat + research timeline
"""

import re  # FIX ISSUE-021: For escaping regex special characters
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from ..core.exceptions import HistoryServiceError
from ..core.redis_cache import get_redis_cache
from ..models.chat import ChatMessage
from ..models.history import (
    HistoryEvent,
    HistoryEventFactory,
    HistoryEventType,
    HistoryQuery,
)
from ..models.task import Task

logger = structlog.get_logger(__name__)


class HistoryService:
    """Service for managing unified chat + research history"""

    @staticmethod
    async def record_chat_message(
        chat_id: str, user_id: str, message: ChatMessage
    ) -> HistoryEvent:
        """Record a chat message in the unified history"""
        try:
            event = await HistoryEventFactory.create_chat_message_event(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message.id,
                role=message.role.value,
                content=message.content,
                model=message.model,
                tokens=message.tokens,
                latency_ms=message.latency_ms,
                # Additional metadata
                status=message.status.value,
                created_at=message.created_at,
                message_metadata=message.metadata,
                # NEW: Include typed file fields in metadata
                file_ids=getattr(message, "file_ids", []),
                files=[
                    f.model_dump() if hasattr(f, "model_dump") else f
                    for f in getattr(message, "files", [])
                ],
                schema_version=getattr(message, "schema_version", 1),
            )

            # Invalidate cache
            await HistoryService._invalidate_cache(chat_id)

            logger.info(
                "Recorded chat message in history",
                chat_id=chat_id,
                message_id=message.id,
                event_id=event.id,
            )

            return event

        except PyMongoError as db_err:
            logger.error(
                "Failed to record chat message in history",
                chat_id=chat_id,
                message_id=message.id,
                error=str(db_err),
            )
            raise HistoryServiceError(
                f"Failed to record chat message: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def record_research_started(
        chat_id: str,
        user_id: str,
        task: Task,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> HistoryEvent:
        """Record research task start"""
        try:
            event = await HistoryEventFactory.create_research_started_event(
                chat_id=chat_id,
                user_id=user_id,
                task_id=task.id,
                query=query,
                # Additional metadata
                task_type=task.task_type,
                params=params,
                created_at=task.created_at,
            )

            await HistoryService._invalidate_cache(chat_id)

            logger.info(
                "Recorded research start in history",
                chat_id=chat_id,
                task_id=task.id,
                event_id=event.id,
            )

            return event

        except PyMongoError as db_err:
            logger.error(
                "Failed to record research start in history",
                chat_id=chat_id,
                task_id=task.id,
                error=str(db_err),
            )
            raise HistoryServiceError(
                f"Failed to record research start: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def record_research_progress(
        chat_id: str,
        user_id: str,
        task_id: str,
        progress: float,
        current_step: str,
        sources_found: Optional[int] = None,
        iterations_completed: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryEvent:
        """Record research progress update"""
        try:
            normalized_progress = HistoryService._normalize_progress(progress)
            if normalized_progress is None:
                normalized_progress = 0.0
            event = await HistoryEventFactory.create_research_progress_event(
                chat_id=chat_id,
                user_id=user_id,
                task_id=task_id,
                progress=normalized_progress,
                current_step=current_step,
                sources_found=sources_found,
                iterations_completed=iterations_completed,
                **(metadata or {}),
            )

            # Only invalidate cache for significant progress updates (every 10%)
            if normalized_progress is not None and int(normalized_progress) % 10 == 0:
                await HistoryService._invalidate_cache(chat_id)

            logger.debug(
                "Recorded research progress in history",
                chat_id=chat_id,
                task_id=task_id,
                progress=normalized_progress,
                event_id=event.id,
            )

            return event

        except PyMongoError as db_err:
            logger.error(
                "Failed to record research progress in history",
                chat_id=chat_id,
                task_id=task_id,
                error=str(db_err),
            )
            # Don't fail progress updates if history fails
            return None

    @staticmethod
    async def record_research_completed(
        chat_id: str,
        user_id: str,
        task: Task,
        sources_found: int,
        iterations_completed: int,
        result_metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryEvent:
        """Record research completion"""
        try:
            event = await HistoryEventFactory.create_research_completed_event(
                chat_id=chat_id,
                user_id=user_id,
                task_id=task.id,
                sources_found=sources_found,
                iterations_completed=iterations_completed,
                # Additional metadata
                completed_at=task.completed_at,
                result_data=task.result_data,
                **(result_metadata or {}),
            )

            await HistoryService._invalidate_cache(chat_id)

            logger.info(
                "Recorded research completion in history",
                chat_id=chat_id,
                task_id=task.id,
                event_id=event.id,
            )

            return event

        except PyMongoError as db_err:
            logger.error(
                "Failed to record research completion in history",
                chat_id=chat_id,
                task_id=task.id,
                error=str(db_err),
            )
            raise HistoryServiceError(
                f"Failed to record research completion: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def record_research_failed(
        chat_id: str,
        user_id: str,
        task_id: str,
        error_message: str,
        progress: Optional[float] = None,
        current_step: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryEvent:
        """Record research failure"""
        try:
            normalized_progress = (
                HistoryService._normalize_progress(progress)
                if progress is not None
                else None
            )
            event = await HistoryEventFactory.create_research_failed_event(
                chat_id=chat_id,
                user_id=user_id,
                task_id=task_id,
                error_message=error_message,
                progress=normalized_progress,
                current_step=current_step,
                **(metadata or {}),
            )

            await HistoryService._invalidate_cache(chat_id)

            logger.error(
                "Recorded research failure in history",
                chat_id=chat_id,
                task_id=task_id,
                event_id=event.id,
                error=error_message,
            )

            return event

        except PyMongoError as db_err:
            logger.error(
                "Failed to record research failure in history",
                chat_id=chat_id,
                task_id=task_id,
                error=str(db_err),
            )
            raise HistoryServiceError(
                f"Failed to record research failure: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def record_source_discovery(
        chat_id: str,
        user_id: str,
        task_id: str,
        source_id: str,
        url: str,
        title: str,
        relevance_score: float,
        credibility_score: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryEvent:
        """Record source discovery during research"""
        try:
            event = await HistoryEventFactory.create_source_found_event(
                chat_id=chat_id,
                user_id=user_id,
                task_id=task_id,
                source_id=source_id,
                url=url,
                title=title,
                relevance_score=relevance_score,
                credibility_score=credibility_score,
                **(metadata or {}),
            )

            logger.debug(
                "Recorded source discovery in history",
                chat_id=chat_id,
                task_id=task_id,
                source_id=source_id,
                event_id=event.id,
            )

            return event

        except PyMongoError as db_err:
            logger.error(
                "Failed to record source discovery in history",
                chat_id=chat_id,
                task_id=task_id,
                source_id=source_id,
                error=str(db_err),
            )
            # Don't fail source discovery if history fails
            return None

    @staticmethod
    async def get_chat_timeline(
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
        event_types: Optional[List[HistoryEventType]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Get complete timeline for a chat"""

        cache_key = (
            f"chat_timeline:{chat_id}:{limit}:{offset}:{':'.join(event_types or [])}"
        )

        # Try cache first
        if use_cache:
            try:
                cache = await get_redis_cache()
                cached_result = await cache.get(cache_key)
                if cached_result:
                    logger.debug("Returning cached chat timeline", chat_id=chat_id)
                    return cached_result
            except RedisError as e:
                logger.warning("Cache retrieval failed", error=str(e))

        try:
            # Get events
            events = await HistoryQuery.get_chat_timeline(
                chat_id=chat_id, limit=limit, offset=offset, event_types=event_types
            )

            # Get total count
            total_count = await HistoryQuery.get_chat_timeline_count(
                chat_id=chat_id, event_types=event_types
            )

            result = {
                "chat_id": chat_id,
                "events": [event.model_dump(mode="json") for event in events],
                "total_count": total_count,
                "has_more": offset + len(events) < total_count,
                "limit": limit,
                "offset": offset,
            }

            # Cache result
            if use_cache:
                try:
                    cache = await get_redis_cache()
                    await cache.set(cache_key, result, expire=300)  # 5 minutes cache
                except RedisError as e:
                    logger.warning("Cache storage failed", error=str(e))

            logger.info(
                "Retrieved chat timeline",
                chat_id=chat_id,
                event_count=len(events),
                total_count=total_count,
            )

            return result

        except PyMongoError as db_err:
            logger.error(
                "Failed to get chat timeline", chat_id=chat_id, error=str(db_err)
            )
            raise HistoryServiceError(
                f"Failed to get chat timeline: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def get_research_timeline(chat_id: str, task_id: str) -> List[HistoryEvent]:
        """Get research-specific timeline for a task"""
        try:
            events = await HistoryQuery.get_research_events_for_task(task_id)

            logger.info(
                "Retrieved research timeline",
                chat_id=chat_id,
                task_id=task_id,
                event_count=len(events),
            )

            return events

        except PyMongoError as db_err:
            logger.error(
                "Failed to get research timeline",
                chat_id=chat_id,
                task_id=task_id,
                error=str(db_err),
            )
            raise HistoryServiceError(
                f"Failed to get research timeline: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def get_latest_research_status(
        chat_id: str, task_id: str
    ) -> Optional[HistoryEvent]:
        """Get the latest research status for a task"""
        try:
            return await HistoryQuery.get_latest_research_event(chat_id, task_id)
        except PyMongoError as db_err:
            logger.error(
                "Failed to get latest research status",
                chat_id=chat_id,
                task_id=task_id,
                error=str(db_err),
            )
            return None  # Graceful degradation for status checks

    @staticmethod
    async def cleanup_old_events(chat_id: str, keep_days: int = 30):
        """Clean up old history events for a chat"""
        try:
            cutoff_date = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=keep_days)

            result = await HistoryEvent.find(
                HistoryEvent.chat_id == chat_id, HistoryEvent.created_at < cutoff_date
            ).delete()

            if result.deleted_count > 0:
                await HistoryService._invalidate_cache(chat_id)

            logger.info(
                "Cleaned up old history events",
                chat_id=chat_id,
                deleted_count=result.deleted_count,
                cutoff_date=cutoff_date,
            )

            return result.deleted_count

        except PyMongoError as db_err:
            logger.error(
                "Failed to cleanup old events", chat_id=chat_id, error=str(db_err)
            )
            return 0  # Graceful degradation for cleanup operations

    @staticmethod
    async def _invalidate_cache(chat_id: str):
        """Invalidate all cache entries for a chat"""
        try:
            cache = await get_redis_cache()
            pattern = f"chat_timeline:{chat_id}:*"
            await cache.delete_pattern(pattern)
        except RedisError as redis_err:
            logger.warning(
                "Failed to invalidate cache", chat_id=chat_id, error=str(redis_err)
            )

    @staticmethod
    def _normalize_progress(progress: Optional[float]) -> Optional[float]:
        """Normalize progress values to percentage scale"""
        if progress is None:
            return None

        try:
            if progress <= 1:
                return round(progress * 100, 2)
            return round(progress, 2)
        except TypeError:
            return None

    # ======================================
    # EXTENDED METHODS FOR HISTORY ROUTER
    # ======================================

    @staticmethod
    async def get_session_with_permission_check(chat_id: str, user_id: str):
        """
        Get chat session and verify user has access.
        Reusable method to avoid duplicating access checks across endpoints.

        Args:
            chat_id: Chat session ID
            user_id: User ID

        Returns:
            ChatSessionModel

        Raises:
            HTTPException: If session not found or access denied
        """
        from fastapi import HTTPException, status

        from ..models.chat import ChatSession as ChatSessionModel

        chat_session = await ChatSessionModel.get(chat_id)
        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found"
            )

        if chat_session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to chat session",
            )

        return chat_session

    @staticmethod
    async def get_chat_sessions(
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get chat sessions for user with filtering and pagination.

        Args:
            user_id: User ID
            limit: Maximum sessions to return
            offset: Number of sessions to skip
            search: Search term for session titles
            date_from: Filter sessions from date
            date_to: Filter sessions to date

        Returns:
            Dict with sessions, total_count, has_more
        """
        from ..models.chat import ChatSession as ChatSessionModel
        from ..schemas.chat import ChatSession

        try:
            # Build query
            query = ChatSessionModel.find(ChatSessionModel.user_id == user_id)

            # Apply date filters
            if date_from:
                query = query.find(ChatSessionModel.created_at >= date_from)
            if date_to:
                query = query.find(ChatSessionModel.created_at <= date_to)

            # Apply search filter
            if search:
                # FIX ISSUE-021: Escape regex special characters to prevent ReDoS
                # Prevents catastrophic backtracking from malicious regex patterns like (a+)+b
                escaped_search = re.escape(search)
                # Case-insensitive search in title
                query = query.find(
                    {"title": {"$regex": escaped_search, "$options": "i"}}
                )

            # Get total count
            total_count = await query.count()

            # Get sessions with pagination, ordered by most recent
            sessions_docs = (
                await query.sort(-ChatSessionModel.updated_at)
                .skip(offset)
                .limit(limit)
                .to_list()
            )

            # Convert to response schema
            sessions = []
            for session in sessions_docs:
                sessions.append(
                    ChatSession(
                        id=session.id,
                        title=session.title,
                        user_id=session.user_id,
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                        message_count=session.message_count,
                        settings=(
                            session.settings.model_dump()
                            if hasattr(session.settings, "model_dump")
                            else session.settings
                        ),
                    )
                )

            has_more = offset + len(sessions) < total_count

            logger.info(
                "Retrieved chat sessions",
                user_id=user_id,
                session_count=len(sessions),
                total_count=total_count,
                search_term=search,
            )

            return {
                "sessions": sessions,
                "total_count": total_count,
                "has_more": has_more,
            }

        except PyMongoError as db_err:
            logger.error(
                "Error retrieving chat sessions", error=str(db_err), user_id=user_id
            )
            raise HistoryServiceError(
                f"Failed to retrieve chat sessions: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def get_chat_messages(
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
        include_system: bool = False,
        message_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get messages for a chat session with filtering and pagination.

        Args:
            chat_id: Chat session ID
            limit: Maximum messages to return
            offset: Number of messages to skip
            include_system: Include system messages
            message_type: Filter by message role

        Returns:
            Dict with messages, total_count, has_more
        """
        from ..models.chat import ChatMessage as ChatMessageModel
        from ..models.chat import MessageRole
        from ..schemas.chat import ChatMessage

        try:
            # Build message query
            query = ChatMessageModel.find(ChatMessageModel.chat_id == chat_id)

            # Apply filters
            if not include_system:
                query = query.find(ChatMessageModel.role != MessageRole.SYSTEM)

            if message_type:
                role = MessageRole(message_type)
                query = query.find(ChatMessageModel.role == role)

            # Get total count
            total_count = await query.count()

            # Get messages with pagination (reverse chronological order)
            messages_docs = (
                await query.sort(-ChatMessageModel.created_at)
                .skip(offset)
                .limit(limit)
                .to_list()
            )

            # Convert to response schema (reverse to get chronological order for display)
            messages = []
            for msg in reversed(messages_docs):
                # ISSUE-007: On-the-fly migration for legacy messages
                file_ids = getattr(msg, "file_ids", [])
                files = getattr(msg, "files", [])
                schema_version = getattr(msg, "schema_version", 1)

                # If schema < 2 and no explicit files but has legacy metadata, migrate
                if schema_version < 2 and not files and msg.metadata:
                    if "file_ids" in msg.metadata or "files" in msg.metadata:
                        from ..models.chat import FileMetadata

                        try:
                            legacy_file_ids = msg.metadata.get("file_ids", [])
                            legacy_files = msg.metadata.get("files", [])

                            # Migrate file_ids
                            if legacy_file_ids and not file_ids:
                                file_ids = legacy_file_ids

                            # Migrate and validate files
                            if legacy_files and not files:
                                files = [
                                    (
                                        FileMetadata.model_validate(f)
                                        if isinstance(f, dict)
                                        else f
                                    )
                                    for f in legacy_files
                                ]

                            logger.debug(
                                "Migrated legacy file metadata",
                                msg_id=msg.id,
                                file_count=len(files),
                            )
                        except (ValueError, TypeError) as migration_err:
                            logger.warning(
                                "Failed to migrate legacy file metadata",
                                error=str(migration_err),
                                msg_id=msg.id,
                            )

                messages.append(
                    ChatMessage(
                        id=msg.id,
                        chat_id=msg.chat_id,
                        role=msg.role,
                        content=msg.content,
                        status=msg.status,
                        created_at=msg.created_at,
                        updated_at=msg.updated_at,
                        # ISSUE-007: Use migrated fields
                        file_ids=file_ids,
                        files=files,
                        schema_version=schema_version,
                        # Legacy metadata for backwards compatibility
                        metadata=msg.metadata,
                        model=msg.model,
                        tokens=msg.tokens,
                        latency_ms=msg.latency_ms,
                        task_id=msg.task_id,
                    )
                )

            has_more = offset + len(messages) < total_count

            logger.info(
                "Retrieved chat messages",
                chat_id=chat_id,
                message_count=len(messages),
                total_count=total_count,
            )

            return {
                "messages": messages,
                "total_count": total_count,
                "has_more": has_more,
            }

        except PyMongoError as db_err:
            logger.error(
                "Error retrieving chat messages", error=str(db_err), chat_id=chat_id
            )
            raise HistoryServiceError(
                f"Failed to retrieve chat messages: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def export_chat_history(
        chat_id: str, format: str = "json", include_metadata: bool = False
    ) -> Dict[str, Any]:
        """
        Export chat history in various formats.

        Args:
            chat_id: Chat session ID
            format: Export format (json, csv, txt)
            include_metadata: Include message metadata

        Returns:
            Export data in requested format
        """
        from ..models.chat import ChatMessage as ChatMessageModel
        from ..models.chat import ChatSession as ChatSessionModel

        try:
            # Get chat session
            chat_session = await ChatSessionModel.get(chat_id)
            if not chat_session:
                from fastapi import HTTPException, status

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found",
                )

            # Get all messages
            messages = (
                await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id)
                .sort(ChatMessageModel.created_at)
                .to_list()
            )

            if format == "json":
                # Export as JSON
                export_data = {
                    "chat_session": {
                        "id": chat_session.id,
                        "title": chat_session.title,
                        "created_at": chat_session.created_at.isoformat(),
                        "message_count": len(messages),
                    },
                    "messages": [],
                }

                for msg in messages:
                    msg_data = {
                        "role": msg.role.value,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat(),
                    }

                    if include_metadata:
                        msg_data.update(
                            {
                                "id": msg.id,
                                "status": msg.status.value,
                                "model": msg.model,
                                "tokens": msg.tokens,
                                "latency_ms": msg.latency_ms,
                                "metadata": msg.metadata,
                            }
                        )

                    export_data["messages"].append(msg_data)

                return export_data

            elif format == "txt":
                # Export as plain text
                lines = [
                    f"Chat: {chat_session.title}",
                    f"Created: {chat_session.created_at}",
                    "=" * 50,
                    "",
                ]

                for msg in messages:
                    timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    lines.append(
                        f"[{timestamp}] {msg.role.value.upper()}: {msg.content}"
                    )
                    lines.append("")

                return {"content": "\n".join(lines)}

            else:
                # CSV format
                import csv
                import io

                output = io.StringIO()
                writer = csv.writer(output)

                # Headers
                headers = ["timestamp", "role", "content"]
                if include_metadata:
                    headers.extend(
                        ["message_id", "status", "model", "tokens", "latency_ms"]
                    )

                writer.writerow(headers)

                # Data rows
                for msg in messages:
                    row = [
                        msg.created_at.isoformat(),
                        msg.role.value,
                        msg.content.replace("\n", "\\n"),  # Escape newlines
                    ]

                    if include_metadata:
                        row.extend(
                            [
                                msg.id,
                                msg.status.value,
                                msg.model or "",
                                msg.tokens or 0,
                                msg.latency_ms or 0,
                            ]
                        )

                    writer.writerow(row)

                return {"content": output.getvalue()}

        except PyMongoError as db_err:
            logger.error(
                "Error exporting chat history", error=str(db_err), chat_id=chat_id
            )
            raise HistoryServiceError(
                f"Failed to export chat history: {db_err}", cause=db_err
            ) from db_err

    @staticmethod
    async def get_user_chat_statistics(user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get chat usage statistics for a user.

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            Dict with statistics
        """
        from ..models.chat import ChatMessage as ChatMessageModel
        from ..models.chat import ChatSession as ChatSessionModel
        from ..models.chat import MessageRole

        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Get session stats
            session_count = await ChatSessionModel.find(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.created_at >= start_date,
            ).count()

            # Get message stats
            total_messages = await ChatMessageModel.find(
                ChatMessageModel.chat_id.regex(".*"),  # All user's messages
                ChatMessageModel.created_at >= start_date,
            ).count()

            user_messages = await ChatMessageModel.find(
                ChatMessageModel.role == MessageRole.USER,
                ChatMessageModel.created_at >= start_date,
            ).count()

            ai_messages = await ChatMessageModel.find(
                ChatMessageModel.role == MessageRole.ASSISTANT,
                ChatMessageModel.created_at >= start_date,
            ).count()

            stats = {
                "period_days": days,
                "session_count": session_count,
                "total_messages": total_messages,
                "user_messages": user_messages,
                "ai_messages": ai_messages,
                "avg_messages_per_session": (
                    total_messages / session_count if session_count > 0 else 0
                ),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

            logger.info("Retrieved user chat stats", user_id=user_id, stats=stats)

            return stats

        except PyMongoError as db_err:
            logger.error(
                "Error retrieving chat stats", error=str(db_err), user_id=user_id
            )
            raise HistoryServiceError(
                f"Failed to retrieve chat stats: {db_err}", cause=db_err
            ) from db_err
